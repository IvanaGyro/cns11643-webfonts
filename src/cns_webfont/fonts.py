"""Font inspection, table verification, and archive classification."""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont

from cns_webfont.models import SourceFont

logger = logging.getLogger(__name__)

REQUIRED_TABLES = {"head", "maxp", "cmap", "name", "OS/2", "post"}


class FontInspectionError(Exception):
    """Raised when font inspection or classification fails."""


def inspect_font_file(font_path: Path, role: str) -> SourceFont:
    """Inspect a TrueType font file and collect metadata.

    Validates:
    1. The file is a valid TrueType/OpenType font loadable by fontTools.
    2. Essential font tables are present.
    3. Cmap table contains mapped codepoints.

    Args:
        font_path: Path to the font file.
        role: Identified role ('core', 'extb', 'plus').

    Returns:
        SourceFont with extracted metadata.
    """
    if not font_path.is_file():
        raise FontInspectionError(f"Font file does not exist: {font_path}")

    # Compute SHA-256
    hasher = hashlib.sha256()
    with open(font_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    sha256_hex = hasher.hexdigest()

    try:
        font = TTFont(font_path, lazy=True)
    except Exception as err:
        raise FontInspectionError(f"Failed to open font {font_path.name}: {err}") from err

    present_tables = set(font.keys())
    missing_tables = REQUIRED_TABLES - present_tables
    if missing_tables:
        raise FontInspectionError(
            f"Font {font_path.name} is missing essential tables: {missing_tables}"
        )

    # Validate glyph table (glyf for TTF or CFF/CFF2 for OTF)
    if (
        "glyf" not in present_tables
        and "CFF " not in present_tables
        and "CFF2" not in present_tables
    ):
        raise FontInspectionError(f"Font {font_path.name} has no glyph outline table (glyf or CFF)")

    num_glyphs = font["maxp"].numGlyphs
    if num_glyphs <= 0:
        raise FontInspectionError(f"Font {font_path.name} has invalid glyph count: {num_glyphs}")

    best_cmap = font.getBestCmap()
    if not best_cmap:
        raise FontInspectionError(f"Font {font_path.name} contains no valid cmap table")

    codepoints = set(best_cmap.keys())
    logger.info(
        "Inspected %s (%s): %d glyphs, %d codepoints, sha256=%s",
        font_path.name,
        role,
        num_glyphs,
        len(codepoints),
        sha256_hex[:12],
    )

    return SourceFont(
        role=role,
        filename=font_path.name,
        path=font_path,
        sha256=sha256_hex,
        glyph_count=num_glyphs,
        codepoints=codepoints,
    )


def classify_font_role(filename: str) -> str | None:
    """Determine font role based on filename convention."""
    lower_name = filename.lower()
    if not (lower_name.endswith(".ttf") or lower_name.endswith(".otf")):
        return None

    if "ext-b" in lower_name or "ext_b" in lower_name or "extb" in lower_name:
        return "extb"
    if "plus" in lower_name:
        return "plus"
    if "98_1" in lower_name or "tw-" in lower_name:
        return "core"

    return None


def extract_and_classify_fonts(zip_path: Path, extract_to: Path) -> dict[str, SourceFont]:
    """Extract font archive and classify core, extb, and plus source fonts.

    Args:
        zip_path: Path to Fonts_Sung.zip or Fonts_Kai.zip.
        extract_to: Directory to extract font files.

    Returns:
        Mapping of role ('core', 'extb', 'plus') -> SourceFont.

    Raises:
        FontInspectionError: If archive is corrupt or any expected source role is missing.
    """
    if not zip_path.is_file():
        raise FontInspectionError(f"Font zip file not found: {zip_path}")

    extract_to.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
    except Exception as err:
        raise FontInspectionError(f"Failed to extract zip file {zip_path}: {err}") from err

    fonts_by_role: dict[str, SourceFont] = {}

    for file_path in extract_to.iterdir():
        if not file_path.is_file():
            continue
        role = classify_font_role(file_path.name)
        if role:
            if role in fonts_by_role:
                raise FontInspectionError(
                    f"Ambiguous font role '{role}': both {fonts_by_role[role].filename} "
                    f"and {file_path.name} match"
                )
            fonts_by_role[role] = inspect_font_file(file_path, role)

    expected_roles = {"core", "extb", "plus"}
    missing_roles = expected_roles - set(fonts_by_role.keys())
    if missing_roles:
        raise FontInspectionError(
            f"Archive {zip_path.name} is missing required source fonts for roles: {missing_roles}. "
            f"Found: {list(fonts_by_role.keys())}"
        )

    return fonts_by_role
