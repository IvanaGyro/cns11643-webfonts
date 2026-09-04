"""Package validation, WOFF2 table checks, and regression guards."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from fontTools.ttLib import TTFont

from cns_webfont.css import parse_unicode_range_to_codepoints, verify_css_invariants

logger = logging.getLogger(__name__)

MAX_UNPACKED_PACKAGE_BYTES = 90 * 1024 * 1024  # 90 MiB jsDelivr hard guard


class ValidationError(Exception):
    """Raised when font, CSS, manifest, or regression validation fails."""


def validate_shard_woff2(woff2_path: Path, expected_codepoints: set[int]) -> None:
    """Validate that a WOFF2 file is structurally valid and matches expected cmap."""
    if not woff2_path.is_file():
        raise ValidationError(f"WOFF2 shard missing: {woff2_path}")

    try:
        font = TTFont(woff2_path, flavor="woff2")
    except Exception as err:
        raise ValidationError(f"Failed to open WOFF2 shard {woff2_path.name}: {err}") from err

    best_cmap = font.getBestCmap()
    if best_cmap is None:
        raise ValidationError(f"WOFF2 shard {woff2_path.name} has no valid cmap")

    actual_cps = set(best_cmap.keys())
    if actual_cps != expected_codepoints:
        missing = expected_codepoints - actual_cps
        extra = actual_cps - expected_codepoints
        raise ValidationError(
            f"WOFF2 cmap mismatch in {woff2_path.name}: "
            f"{len(missing)} missing, {len(extra)} extra codepoints"
        )


def validate_package(package_dir: Path) -> dict:
    """Perform complete structural and invariant validation on a built package.

    Validates:
    1. manifest.json exists and is valid JSON.
    2. Primary CSS file exists and satisfies coverage and disjointness invariants.
    3. Every shard WOFF2 exists, matches manifest SHA-256 and byte size.
    4. actual WOFF2 cmap == manifest shard cmap == CSS unicode-range for that shard.
    5. Unpacked package size is strictly under 90 MiB.

    Args:
        package_dir: Directory containing package.json, CSS, manifest.json, and woff2/.

    Returns:
        Loaded manifest dictionary.
    """
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValidationError(f"manifest.json missing in {package_dir}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as err:
        raise ValidationError(f"Invalid manifest.json in {package_dir}: {err}") from err

    family = manifest.get("family", "")
    css_name = f"{family.lower()}.css"
    css_path = package_dir / css_name
    if not css_path.is_file():
        raise ValidationError(f"CSS file missing: {css_path}")

    css_content = css_path.read_text(encoding="utf-8")

    # Collect expected codepoints from all shards in manifest
    all_manifest_cps: set[int] = set()
    shards_meta = manifest.get("shards", [])
    if not shards_meta:
        raise ValidationError(f"Manifest contains zero shards for family {family}")

    for shard_meta in shards_meta:
        fn = shard_meta["filename"]
        woff2_file = package_dir / "woff2" / fn
        if not woff2_file.is_file():
            raise ValidationError(f"Shard file does not exist: {woff2_file}")

        # Check byte size and SHA-256
        data = woff2_file.read_bytes()
        if len(data) != shard_meta["bytes"]:
            raise ValidationError(
                f"Byte size mismatch for {fn}: manifest={shard_meta['bytes']}, actual={len(data)}"
            )

        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash.lower() != shard_meta["sha256"].lower():
            raise ValidationError(
                f"SHA256 mismatch for {fn}: manifest={shard_meta['sha256']}, actual={actual_hash}"
            )

        # Parse range from manifest
        range_cps = parse_unicode_range_to_codepoints(shard_meta["unicodeRanges"])
        if len(range_cps) != shard_meta["codepointCount"]:
            raise ValidationError(
                f"Range codepoint count mismatch for {fn}: "
                f"ranges={len(range_cps)}, manifest={shard_meta['codepointCount']}"
            )

        # Validate actual font cmap
        validate_shard_woff2(woff2_file, range_cps)

        all_manifest_cps.update(range_cps)

    # Validate CSS coverage invariant
    verify_css_invariants(css_content, all_manifest_cps)

    # Size guard check
    check_package_unpacked_size(package_dir)

    logger.info("Package validation succeeded for %s (%d shards)", family, len(shards_meta))
    return manifest


def check_coverage_regression(
    current_codepoint_count: int,
    previous_codepoint_count: int | None,
    min_retention_ratio: float = 0.98,
) -> None:
    """Verify that font coverage has not dropped abnormally compared to previous release.

    Args:
        current_codepoint_count: Number of unique codepoints in new build.
        previous_codepoint_count: Number of unique codepoints in previous release.
        min_retention_ratio: Minimum acceptable ratio (default 0.98 = 98%).

    Raises:
        ValidationError: If coverage dropped below threshold.
    """
    if previous_codepoint_count is None or previous_codepoint_count <= 0:
        return

    ratio = current_codepoint_count / previous_codepoint_count
    if ratio < min_retention_ratio:
        raise ValidationError(
            f"Coverage regression detected: current count ({current_codepoint_count}) is "
            f"{ratio * 100:.1f}% of previous count ({previous_codepoint_count}), "
            f"which is below the {min_retention_ratio * 100:.1f}% safety threshold. "
            f"DO NOT PUBLISH."
        )


def check_package_unpacked_size(
    package_dir: Path,
    max_unpacked_bytes: int = MAX_UNPACKED_PACKAGE_BYTES,
) -> int:
    """Calculate unpacked package size and enforce the 90 MiB hard limit."""
    pkg_json_path = package_dir / "package.json"
    if not pkg_json_path.is_file():
        raise ValidationError(f"package.json missing in {package_dir}")

    try:
        pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
    except Exception as err:
        raise ValidationError(f"Failed to parse package.json: {err}") from err

    included_patterns = pkg_data.get("files", [])
    total_unpacked_bytes = 0

    # Sum size of all files that npm pack would include
    for file_or_dir in included_patterns:
        target = package_dir / file_or_dir
        if target.is_file():
            total_unpacked_bytes += target.stat().st_size
        elif target.is_dir():
            for sub_file in target.rglob("*"):
                if sub_file.is_file():
                    total_unpacked_bytes += sub_file.stat().st_size

    # Also include package.json itself
    total_unpacked_bytes += pkg_json_path.stat().st_size

    unpacked_mib = total_unpacked_bytes / (1024 * 1024)
    max_mib = max_unpacked_bytes / (1024 * 1024)

    logger.info("Unpacked package size for %s: %.2f MiB", package_dir.name, unpacked_mib)

    if total_unpacked_bytes >= max_unpacked_bytes:
        raise ValidationError(
            f"Package size guard triggered: unpacked size is {unpacked_mib:.2f} MiB "
            f"exceeding the hard limit of {max_mib:.2f} MiB. "
            f"DO NOT PUBLISH. Consider splitting into plane/source packages."
        )

    return total_unpacked_bytes
