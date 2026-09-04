"""Unit tests for TrueType subsetting and WOFF2 generation."""

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from cns_webfont.subset import SubsettingError, subset_font_to_woff2
from tests.fixtures.synthetic_fonts import create_synthetic_ttf


def test_subset_font_to_woff2(tmp_path: Path):
    """Verify font subsetting creates valid WOFF2 with correct cmap and tables."""
    source_ttf = tmp_path / "source.ttf"
    all_cps = {0x4E00, 0x4E01, 0x4E02, 0x4E03, 0x4E04}
    create_synthetic_ttf(all_cps, output_path=source_ttf)

    target_cps = {0x4E01, 0x4E03}
    out_woff2 = tmp_path / "subset.woff2"

    size, sha256_hex = subset_font_to_woff2(
        source_ttf,
        target_cps,
        out_woff2,
        deterministic_timestamp=1700000000,
    )

    assert out_woff2.is_file()
    assert size == len(out_woff2.read_bytes())
    assert len(sha256_hex) == 64

    # Check WOFF2 header signature
    header = out_woff2.read_bytes()[:4]
    assert header == b"wOF2"

    # Open WOFF2 with fontTools
    font = TTFont(out_woff2, flavor="woff2")
    assert font.flavor == "woff2"

    # Verify cmap matches target codepoints exactly
    best_cmap = font.getBestCmap()
    assert set(best_cmap.keys()) == target_cps

    # Verify required tables are preserved
    for table_tag in [
        "head",
        "hhea",
        "maxp",
        "OS/2",
        "hmtx",
        "cmap",
        "loca",
        "glyf",
        "name",
        "post",
    ]:
        assert table_tag in font


def test_subset_reproducibility(tmp_path: Path):
    """Verify consecutive subset runs produce byte-for-byte identical output."""
    source_ttf = tmp_path / "source.ttf"
    create_synthetic_ttf({0x4E00, 0x4E01, 0x4E02}, output_path=source_ttf)

    out1 = tmp_path / "out1.woff2"
    out2 = tmp_path / "out2.woff2"

    size1, sha1 = subset_font_to_woff2(
        source_ttf, {0x4E01}, out1, deterministic_timestamp=1700000000
    )
    size2, sha2 = subset_font_to_woff2(
        source_ttf, {0x4E01}, out2, deterministic_timestamp=1700000000
    )

    assert size1 == size2
    assert sha1 == sha2
    assert out1.read_bytes() == out2.read_bytes()


def test_subset_empty_codepoints(tmp_path: Path):
    """Verify error when attempting to subset empty codepoint set."""
    source_ttf = tmp_path / "source.ttf"
    create_synthetic_ttf({0x4E00}, output_path=source_ttf)

    with pytest.raises(SubsettingError, match="empty codepoints set"):
        subset_font_to_woff2(source_ttf, set(), tmp_path / "fail.woff2")


def test_subset_shared_glyph_cmap_isolation(tmp_path: Path):
    """Verify that if multiple codepoints share a glyph in the source font,

    only the requested codepoints are retained in the subset cmap.
    """
    source_ttf = tmp_path / "source_dup.ttf"
    create_synthetic_ttf({0x4E00, 0x4E01}, output_path=source_ttf)

    # In source font, map 0x2F00 to the same glyph as 0x4E00
    font = TTFont(source_ttf)
    glyph_name = font.getBestCmap()[0x4E00]
    for subtable in font["cmap"].tables:
        if subtable.isUnicode():
            subtable.cmap[0x2F00] = glyph_name
    font.save(source_ttf)

    # Subset ONLY for 0x2F00
    out_woff2 = tmp_path / "shard_2f00.woff2"
    subset_font_to_woff2(source_ttf, {0x2F00}, out_woff2)

    # Verify WOFF2 cmap strictly contains only 0x2F00 (0x4E00 must not leak in)
    res_font = TTFont(out_woff2, flavor="woff2")
    assert set(res_font.getBestCmap().keys()) == {0x2F00}
