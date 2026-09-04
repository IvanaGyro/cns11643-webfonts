"""Unit tests for CSS generation and invariant validation."""

import pytest

from cns_webfont.css import (
    CSSInvariantError,
    generate_css,
    generate_font_face_rule,
    parse_unicode_range_to_codepoints,
    verify_css_invariants,
)
from cns_webfont.slicing import PhysicalShardPlan


def test_generate_font_face_rule():
    """Verify single @font-face rule formatting."""
    rule = generate_font_face_rule(
        family_name="TW-Sung",
        woff2_filename="gf-001-core.woff2",
        unicode_range="U+4E00-4E05",
        rel_woff2_dir="./woff2",
    )
    assert "@font-face {" in rule
    assert 'font-family: "TW-Sung";' in rule
    assert 'src: url("./woff2/gf-001-core.woff2") format("woff2");' in rule
    assert "unicode-range: U+4E00-4E05;" in rule


def test_parse_unicode_range_to_codepoints():
    """Verify parsing unicode-range tokens into codepoint set."""
    assert parse_unicode_range_to_codepoints("U+4E00") == {0x4E00}
    assert parse_unicode_range_to_codepoints("U+4E00-4E02") == {0x4E00, 0x4E01, 0x4E02}
    assert parse_unicode_range_to_codepoints("U+4E00-4E01, U+4E05") == {0x4E00, 0x4E01, 0x4E05}

    # Invalid cases
    with pytest.raises(CSSInvariantError, match="Invalid unicode-range token"):
        parse_unicode_range_to_codepoints("4E00")

    with pytest.raises(CSSInvariantError, match="start > end"):
        parse_unicode_range_to_codepoints("U+4E05-4E00")


def test_verify_css_invariants_success():
    """Verify valid CSS satisfies coverage and disjointness checks."""
    shards = [
        PhysicalShardPlan(
            filename="gf-001-core.woff2",
            logical_index=1,
            slice_type="google",
            source_role="core",
            codepoints=[0x4E00, 0x4E01],
            unicode_ranges="U+4E00-4E01",
        ),
        PhysicalShardPlan(
            filename="tail-0001-core.woff2",
            logical_index=1,
            slice_type="tail",
            source_role="core",
            codepoints=[0x4E05],
            unicode_ranges="U+4E05",
        ),
    ]
    css = generate_css("TW-Sung", shards)
    expected_cps = {0x4E00, 0x4E01, 0x4E05}
    verify_css_invariants(css, expected_cps)


def test_verify_css_invariants_overlap():
    """Verify error when two shards overlap on codepoints."""
    shards = [
        PhysicalShardPlan(
            filename="shard1.woff2",
            logical_index=1,
            slice_type="google",
            source_role="core",
            codepoints=[0x4E00, 0x4E01],
            unicode_ranges="U+4E00-4E01",
        ),
        PhysicalShardPlan(
            filename="shard2.woff2",
            logical_index=2,
            slice_type="google",
            source_role="core",
            codepoints=[0x4E01, 0x4E02],
            unicode_ranges="U+4E01-4E02",
        ),
    ]
    css = generate_css("TW-Sung", shards)
    with pytest.raises(CSSInvariantError, match="overlaps with prior shards"):
        verify_css_invariants(css, {0x4E00, 0x4E01, 0x4E02})


def test_verify_css_invariants_missing():
    """Verify error when CSS misses expected codepoints."""
    shards = [
        PhysicalShardPlan(
            filename="shard1.woff2",
            logical_index=1,
            slice_type="google",
            source_role="core",
            codepoints=[0x4E00],
            unicode_ranges="U+4E00",
        ),
    ]
    css = generate_css("TW-Sung", shards)
    with pytest.raises(CSSInvariantError, match="missing from CSS"):
        verify_css_invariants(css, {0x4E00, 0x4E01})
