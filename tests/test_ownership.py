"""Unit tests for font inspection and cmap ownership resolution."""

import json
from pathlib import Path

import pytest

from cns_webfont.cmap import (
    DuplicateRegressionError,
    check_duplicate_regression,
    resolve_cmap_ownership,
)
from cns_webfont.fonts import (
    FontInspectionError,
    classify_font_role,
    extract_and_classify_fonts,
    inspect_font_file,
)
from tests.fixtures.synthetic_fonts import create_synthetic_cns_zip, create_synthetic_ttf


def test_classify_font_role():
    """Verify font filename classification into core, extb, plus."""
    assert classify_font_role("TW-Sung-98_1.ttf") == "core"
    assert classify_font_role("TW-Sung-Ext-B-98_1.ttf") == "extb"
    assert classify_font_role("TW-Sung-Plus-98_1.ttf") == "plus"
    assert classify_font_role("TW-Kai-98_1.ttf") == "core"
    assert classify_font_role("TW-Kai-Ext-B-98_1.ttf") == "extb"
    assert classify_font_role("TW-Kai-Plus-98_1.ttf") == "plus"
    assert classify_font_role("readme.txt") is None


def test_inspect_font_file(tmp_path: Path):
    """Verify font inspection collects required metadata."""
    ttf_path = tmp_path / "test.ttf"
    codepoints = {0x4E00, 0x4E01, 0x4E02}
    create_synthetic_ttf(codepoints, output_path=ttf_path)

    source = inspect_font_file(ttf_path, "core")
    assert source.role == "core"
    assert source.filename == "test.ttf"
    assert source.glyph_count == 4  # .notdef + 3 cps
    assert source.codepoints == codepoints
    assert len(source.sha256) == 64


def test_inspect_invalid_font(tmp_path: Path):
    """Verify error on corrupted font."""
    bad_font = tmp_path / "bad.ttf"
    bad_font.write_bytes(b"not a true font")
    with pytest.raises(FontInspectionError, match="Failed to open font"):
        inspect_font_file(bad_font, "core")


def test_extract_and_classify_fonts(tmp_path: Path):
    """Verify extracting zip archive and classifying fonts."""
    zip_path = tmp_path / "Fonts_Sung.zip"
    extract_dir = tmp_path / "extracted"

    core_cps = {0x4E00, 0x4E01}
    extb_cps = {0x20000, 0x20001}
    plus_cps = {0xF0000, 0xF0001}

    create_synthetic_cns_zip(zip_path, core_cps, extb_cps, plus_cps, prefix="TW-Sung")
    fonts = extract_and_classify_fonts(zip_path, extract_dir)

    assert set(fonts.keys()) == {"core", "extb", "plus"}
    assert fonts["core"].codepoints == core_cps
    assert fonts["extb"].codepoints == extb_cps
    assert fonts["plus"].codepoints == plus_cps


def test_resolve_cmap_ownership_with_duplicates(tmp_path: Path):
    """Verify deterministic ownership (core > extb > plus) and duplicate reporting."""
    zip_path = tmp_path / "Fonts_Sung.zip"
    extract_dir = tmp_path / "extracted"
    dup_json = tmp_path / "duplicates.json"

    # Intentional duplicates:
    # 0x4E00 in core AND extb -> core should win
    # 0x20000 in extb AND plus -> extb should win
    core_cps = {0x4E00, 0x4E01}
    extb_cps = {0x4E00, 0x20000}
    plus_cps = {0x20000, 0xF0000}

    create_synthetic_cns_zip(zip_path, core_cps, extb_cps, plus_cps)
    fonts = extract_and_classify_fonts(zip_path, extract_dir)

    owned, duplicates = resolve_cmap_ownership(fonts, duplicates_output_path=dup_json)

    # Invariants
    assert owned["core"] == {0x4E00, 0x4E01}
    assert owned["extb"] == {0x20000}
    assert owned["plus"] == {0xF0000}

    # All owned sets must be mutually exclusive
    assert not (owned["core"] & owned["extb"])
    assert not (owned["core"] & owned["plus"])
    assert not (owned["extb"] & owned["plus"])

    # Duplicates record
    assert len(duplicates) == 2
    assert duplicates[0]["codepoint"] == "U+4E00"
    assert duplicates[0]["selected"] == "core"
    assert duplicates[1]["codepoint"] == "U+20000"
    assert duplicates[1]["selected"] == "extb"

    assert dup_json.is_file()
    saved = json.loads(dup_json.read_text(encoding="utf-8"))
    assert len(saved) == 2


def test_duplicate_regression_check():
    """Verify duplicate regression error triggers on abnormal duplicate spike."""
    # Normal minor increase should pass
    check_duplicate_regression(current_duplicates_count=10, previous_duplicates_count=8)

    # Abnormal spike should fail
    with pytest.raises(DuplicateRegressionError, match="abnormal regression"):
        check_duplicate_regression(
            current_duplicates_count=200,
            previous_duplicates_count=50,
            max_increase_ratio=1.2,
            max_absolute_increase=50,
        )
