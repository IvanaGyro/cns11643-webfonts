"""Logical slicing and physical sharding engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from cns_webfont.models import LogicalSlice

TAIL_BIN_SIZE = 135
ROLE_PRIORITY = ["core", "extb", "plus"]


@dataclass
class PhysicalShardPlan:
    """Specification of a physical WOFF2 shard to generate."""

    filename: str
    logical_index: int
    slice_type: str  # "google" or "tail"
    source_role: str  # "core", "extb", "plus"
    codepoints: list[int]
    unicode_ranges: str = ""


def format_unicode_ranges(codepoints: list[int] | set[int]) -> str:
    """Format codepoints into compact CSS unicode-range syntax.

    Merges contiguous codepoint sequences into U+XXXX-YYYY ranges.

    Args:
        codepoints: Iterable of integer codepoints.

    Returns:
        Comma-separated string of ranges, e.g., 'U+4E00-4E05, U+4E08, U+20000-20002'.
    """
    if not codepoints:
        return ""

    sorted_cps = sorted(set(codepoints))
    ranges: list[str] = []

    start = sorted_cps[0]
    prev = sorted_cps[0]

    for cp in sorted_cps[1:]:
        if cp == prev + 1:
            prev = cp
        else:
            if start == prev:
                ranges.append(f"U+{start:X}")
            else:
                ranges.append(f"U+{start:X}-{prev:X}")
            start = cp
            prev = cp

    if start == prev:
        ranges.append(f"U+{start:X}")
    else:
        ranges.append(f"U+{start:X}-{prev:X}")

    return ", ".join(ranges)


def plan_shards(
    owned_by_role: Mapping[str, set[int]],
    google_slices: list[LogicalSlice],
    tail_bin_size: int = TAIL_BIN_SIZE,
) -> list[PhysicalShardPlan]:
    """Generate physical shard plans combining Google TC slices and CNS tail bins.

    1. Preserves Google TC subset ordering (reverse priority order).
    2. Common slices: intersect each Google slice with owned source codepoints.
    3. Tail bins: sort remaining CNS codepoints and partition into bins of
       tail_bin_size actual existing codepoints.
    4. Physical split: partition each logical slice by source font role (core, extb, plus).
       Only non-empty physical shards are created.

    Args:
        owned_by_role: Mapping of role -> set of owned codepoints.
        google_slices: Ordered list of Google TC logical slices.
        tail_bin_size: Number of actual codepoints per tail bin (default 135).

    Returns:
        Ordered list of PhysicalShardPlan objects.
    """
    cns_all = set().union(*owned_by_role.values())
    google_codepoints = {cp for s in google_slices for cp in s.codepoints}

    plans: list[PhysicalShardPlan] = []

    # 1. Common Google Fonts TC Slices (preserved in upstream order)
    for g_slice in google_slices:
        slice_cps = set(g_slice.codepoints) & cns_all
        if not slice_cps:
            continue

        for role in ROLE_PRIORITY:
            role_cps = sorted(slice_cps & owned_by_role.get(role, set()))
            if not role_cps:
                continue

            filename = f"gf-{g_slice.index:03d}-{role}.woff2"
            plans.append(
                PhysicalShardPlan(
                    filename=filename,
                    logical_index=g_slice.index,
                    slice_type="google",
                    source_role=role,
                    codepoints=role_cps,
                    unicode_ranges=format_unicode_ranges(role_cps),
                )
            )

    # 2. CNS Rare-Character Tail (sorted by codepoint, 135 actual codepoints per bin)
    tail_cps = sorted(cns_all - google_codepoints)
    tail_bins = [tail_cps[i : i + tail_bin_size] for i in range(0, len(tail_cps), tail_bin_size)]

    for bin_idx, bin_cps in enumerate(tail_bins, start=1):
        bin_set = set(bin_cps)
        for role in ROLE_PRIORITY:
            role_cps = sorted(bin_set & owned_by_role.get(role, set()))
            if not role_cps:
                continue

            filename = f"tail-{bin_idx:04d}-{role}.woff2"
            plans.append(
                PhysicalShardPlan(
                    filename=filename,
                    logical_index=bin_idx,
                    slice_type="tail",
                    source_role=role,
                    codepoints=role_cps,
                    unicode_ranges=format_unicode_ranges(role_cps),
                )
            )

    # Invariant Validations
    all_plan_cps: list[int] = []
    for plan in plans:
        all_plan_cps.extend(plan.codepoints)

    # Invariant 1: Total shard codepoints must equal CNS codepoints
    assert set(all_plan_cps) == cns_all, "Slicing invariant violated: lost or extra codepoints"

    # Invariant 2: All physical shards must be mutually disjoint
    assert len(all_plan_cps) == len(set(all_plan_cps)), (
        "Slicing invariant violated: overlapping shards"
    )

    return plans
