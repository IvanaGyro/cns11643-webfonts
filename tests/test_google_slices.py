"""Unit tests for Google slicing parser."""

from pathlib import Path

import pytest

from cns_webfont.google_slices import GoogleSlicesParsingError, parse_google_slices


def test_parse_pinned_google_slices():
    """Verify pinned TC slicing strategy parses 120 subsets and 17,704 codepoints."""
    strategy_path = Path("data/google-fonts/traditional-chinese_default.txt")
    slices = parse_google_slices(strategy_path)

    assert len(slices) == 120
    total_codepoints = sum(len(s.codepoints) for s in slices)
    assert total_codepoints == 17704

    # Verify subset indices start at 1 and remain sequential
    assert [s.index for s in slices] == list(range(1, 121))

    # Verify all codepoints across all subsets are globally unique
    all_cps = [cp for s in slices for cp in s.codepoints]
    assert len(all_cps) == len(set(all_cps))

    # Verify order is preserved: subset 1 is high codepoints (plane 1 / high BMP)
    # not re-ordered or sorted by minimum codepoint
    assert slices[0].codepoints[0] == 129313
    assert slices[-1].codepoints[0] == 32


def test_missing_file():
    """Test error on missing file."""
    with pytest.raises(GoogleSlicesParsingError, match="not found"):
        parse_google_slices(Path("non_existent_file.txt"))


def test_invalid_codepoint(tmp_path):
    """Test error on out-of-range codepoints."""
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("subsets {\n  codepoints: 1114112\n}\n", encoding="utf-8")
    with pytest.raises(GoogleSlicesParsingError, match="not a valid Unicode scalar"):
        parse_google_slices(bad_file)


def test_surrogate_codepoint(tmp_path):
    """Test error on surrogate codepoints."""
    bad_file = tmp_path / "surrogate.txt"
    bad_file.write_text("subsets {\n  codepoints: 55296\n}\n", encoding="utf-8")
    with pytest.raises(GoogleSlicesParsingError, match="not a valid Unicode scalar"):
        parse_google_slices(bad_file)


def test_duplicate_in_subset(tmp_path):
    """Test error on duplicate within single subset."""
    bad_file = tmp_path / "dup.txt"
    bad_file.write_text("subsets {\n  codepoints: 65\n  codepoints: 65\n}\n", encoding="utf-8")
    with pytest.raises(GoogleSlicesParsingError, match="duplicate codepoint"):
        parse_google_slices(bad_file)


def test_duplicate_across_subsets(tmp_path):
    """Test error on duplicate across multiple subsets."""
    bad_file = tmp_path / "dup_cross.txt"
    bad_file.write_text(
        "subsets {\n  codepoints: 65\n}\nsubsets {\n  codepoints: 65\n}\n", encoding="utf-8"
    )
    with pytest.raises(GoogleSlicesParsingError, match="appeared in a previous subset"):
        parse_google_slices(bad_file)


def test_empty_subset(tmp_path):
    """Test error on empty subset."""
    bad_file = tmp_path / "empty.txt"
    bad_file.write_text("subsets {\n  # just comments\n}\n", encoding="utf-8")
    with pytest.raises(GoogleSlicesParsingError, match="contains zero codepoints"):
        parse_google_slices(bad_file)
