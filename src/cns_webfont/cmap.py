"""Deterministic cmap ownership resolution and duplicate mapping detection."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cns_webfont.models import SourceFont

logger = logging.getLogger(__name__)

ROLE_PRIORITY = ["core", "extb", "plus"]


class DuplicateRegressionError(Exception):
    """Raised when duplicate cmap mappings exceed expected regression thresholds."""


def resolve_cmap_ownership(
    fonts_by_role: Mapping[str, SourceFont],
    duplicates_output_path: Path | None = None,
) -> tuple[dict[str, set[int]], list[dict[str, Any]]]:
    """Resolve deterministic codepoint ownership across core, extb, and plus source fonts.

    Precedence rule: core > extb > plus (first-owner wins).

    Args:
        fonts_by_role: Mapping of role -> SourceFont.
        duplicates_output_path: Optional path to write duplicates.json report.

    Returns:
        Tuple of:
        - dict mapping role -> set of mutually exclusive owned codepoints.
        - list of duplicate mapping record dicts.
    """
    # Track which sources contain each codepoint
    cp_to_sources: dict[int, list[str]] = {}
    for role in ROLE_PRIORITY:
        if role not in fonts_by_role:
            continue
        for cp in fonts_by_role[role].codepoints:
            cp_to_sources.setdefault(cp, []).append(role)

    duplicates: list[dict[str, Any]] = []
    owned_by_role: dict[str, set[int]] = {role: set() for role in ROLE_PRIORITY}

    for cp, sources in cp_to_sources.items():
        # First owner wins based on ROLE_PRIORITY
        selected_role = sources[0]
        owned_by_role[selected_role].add(cp)

        if len(sources) > 1:
            duplicates.append(
                {
                    "codepoint": f"U+{cp:04X}",
                    "decimal": cp,
                    "sources": sources,
                    "selected": selected_role,
                }
            )

    # Sort duplicates by codepoint
    duplicates.sort(key=lambda d: d["decimal"])

    # Invariant checks:
    # 1. Owned sets must be mutually exclusive
    roles_present = [r for r in ROLE_PRIORITY if r in owned_by_role]
    for i, r1 in enumerate(roles_present):
        for r2 in roles_present[i + 1 :]:
            overlap = owned_by_role[r1] & owned_by_role[r2]
            assert not overlap, f"Ownership violation: {r1} and {r2} overlap by {len(overlap)} cps"

    # 2. Total owned codepoints must equal union of all sources
    all_source_cps = set().union(*(f.codepoints for f in fonts_by_role.values()))
    all_owned_cps = set().union(*(owned_by_role.values()))
    assert all_owned_cps == all_source_cps, "Ownership violation: lost codepoints during resolution"

    logger.info(
        "Resolved ownership: %d unique codepoints across %d sources (%d duplicates detected)",
        len(all_owned_cps),
        len(fonts_by_role),
        len(duplicates),
    )

    if duplicates_output_path:
        duplicates_output_path.parent.mkdir(parents=True, exist_ok=True)
        duplicates_output_path.write_text(
            json.dumps(duplicates, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Wrote duplicate mappings to %s", duplicates_output_path)

    return owned_by_role, duplicates


def check_duplicate_regression(
    current_duplicates_count: int,
    previous_duplicates_count: int | None,
    max_increase_ratio: float = 1.20,
    max_absolute_increase: int = 50,
) -> None:
    """Check for abnormal regression in duplicate cmap mappings.

    Args:
        current_duplicates_count: Number of duplicates in current build.
        previous_duplicates_count: Number of duplicates in previous release (if any).
        max_increase_ratio: Maximum allowable relative increase (default 20%).
        max_absolute_increase: Maximum allowable absolute increase.

    Raises:
        DuplicateRegressionError: If duplicates increase beyond allowable bounds.
    """
    if previous_duplicates_count is None:
        return

    increase = current_duplicates_count - previous_duplicates_count
    if increase <= 0:
        return

    ratio = current_duplicates_count / max(1, previous_duplicates_count)
    if increase > max_absolute_increase and ratio > max_increase_ratio:
        raise DuplicateRegressionError(
            f"Duplicate cmap mappings experienced abnormal regression: "
            f"increased from {previous_duplicates_count} to {current_duplicates_count} "
            f"(+{increase}, ratio {ratio:.2f} > {max_increase_ratio:.2f})"
        )
