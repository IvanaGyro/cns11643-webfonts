"""TrueType font subsetting and deterministic WOFF2 generation."""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Set
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

logger = logging.getLogger(__name__)

DEFAULT_DETERMINISTIC_TIMESTAMP = 1700000000  # Fixed timestamp for reproducible builds


class SubsettingError(Exception):
    """Raised when subsetting font fails."""


def subset_font_to_woff2(
    source_ttf_path: Path,
    codepoints: Set[int],
    output_woff2_path: Path,
    deterministic_timestamp: int = DEFAULT_DETERMINISTIC_TIMESTAMP,
) -> tuple[int, str]:
    """Subset a TrueType font to WOFF2 for the given set of codepoints.

    Ensures deterministic output across builds by normalizing timestamp fields.

    Args:
        source_ttf_path: Path to the input TrueType font.
        codepoints: Set of Unicode codepoints to retain.
        output_woff2_path: Destination path for the .woff2 file.
        deterministic_timestamp: Seconds since 1970-01-01 for head table timestamps.

    Returns:
        Tuple of (file_size_bytes, sha256_hex_digest).

    Raises:
        SubsettingError: If subsetting or WOFF2 compression fails.
    """
    if not source_ttf_path.is_file():
        raise SubsettingError(f"Source font not found: {source_ttf_path}")

    if not codepoints:
        raise SubsettingError(
            f"Cannot subset font with empty codepoints set for {output_woff2_path.name}"
        )

    try:
        font = TTFont(source_ttf_path)
    except Exception as err:
        raise SubsettingError(f"Failed to open source font {source_ttf_path}: {err}") from err

    options = subset.Options()
    options.flavor = "woff2"
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.layout_features = ["*"]

    try:
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=codepoints)
        subsetter.subset(font)
    except Exception as err:
        raise SubsettingError(f"Subsetter failed for {output_woff2_path.name}: {err}") from err

    # Prune cmap to strictly retain only the requested codepoints for this shard.
    # In fonts with shared glyphs or composite dependencies, fontTools.subset may retain
    # secondary cmap entries for retained glyphs. Enforce exact matching for CSS alignment.
    if "cmap" in font:
        for subtable in font["cmap"].tables:
            if subtable.isUnicode():
                subtable.cmap = {cp: name for cp, name in subtable.cmap.items() if cp in codepoints}

    # Normalize head table timestamps for byte-level build reproducibility
    if "head" in font:
        font["head"].created = deterministic_timestamp
        font["head"].modified = deterministic_timestamp

    font.flavor = "woff2"

    buf = io.BytesIO()
    try:
        font.save(buf)
    except Exception as err:
        raise SubsettingError(f"Failed to save WOFF2 font {output_woff2_path.name}: {err}") from err

    data = buf.getvalue()

    output_woff2_path.parent.mkdir(parents=True, exist_ok=True)
    output_woff2_path.write_bytes(data)

    file_size = len(data)
    sha256_hex = hashlib.sha256(data).hexdigest()

    return file_size, sha256_hex
