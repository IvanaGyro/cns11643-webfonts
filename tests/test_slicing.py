"""Unit tests for logical slicing and physical sharding engine."""

from cns_webfont.models import LogicalSlice
from cns_webfont.slicing import format_unicode_ranges, plan_shards


def test_format_unicode_ranges():
    """Verify contiguous codepoint compression into CSS unicode-range strings."""
    assert format_unicode_ranges([]) == ""
    assert format_unicode_ranges([0x4E00]) == "U+4E00"
    assert format_unicode_ranges([0x4E00, 0x4E01, 0x4E02]) == "U+4E00-4E02"
    assert (
        format_unicode_ranges([0x4E00, 0x4E01, 0x4E02, 0x4E05, 0x20000, 0x20001])
        == "U+4E00-4E02, U+4E05, U+20000-20001"
    )


def test_plan_shards_google_and_tail():
    """Verify physical shard planning with Google slices and 135-character tail bins."""
    # Google slices: slice 1 has cps 100..109, slice 2 has cps 200..209
    google_slices = [
        LogicalSlice(index=1, slice_type="google", codepoints=list(range(100, 110))),
        LogicalSlice(index=2, slice_type="google", codepoints=list(range(200, 210))),
    ]

    # Owned codepoints:
    # core: has cps 100..104 (in GF 1), plus 300 rare cps (1000..1299)
    # extb: has cps 105..109 (in GF 1), and 200..204 (in GF 2), plus 10 rare cps (2000..2009)
    # plus: has cps 205..209 (in GF 2), plus 5 rare cps (3000..3004)
    owned = {
        "core": set(range(100, 105)) | set(range(1000, 1300)),
        "extb": set(range(105, 110)) | set(range(200, 205)) | set(range(2000, 2010)),
        "plus": set(range(205, 210)) | set(range(3000, 3005)),
    }

    tail_bin_size = 135
    plans = plan_shards(owned, google_slices, tail_bin_size=tail_bin_size)

    # Check Google slices:
    # Slice 1 should have both core (100..104) and extb (105..109)
    gf1_core = [p for p in plans if p.filename == "gf-001-core.woff2"]
    gf1_extb = [p for p in plans if p.filename == "gf-001-extb.woff2"]
    assert len(gf1_core) == 1
    assert gf1_core[0].codepoints == list(range(100, 105))
    assert len(gf1_extb) == 1
    assert gf1_extb[0].codepoints == list(range(105, 110))

    # Slice 2 should have extb (200..204) and plus (205..209)
    gf2_extb = [p for p in plans if p.filename == "gf-002-extb.woff2"]
    gf2_plus = [p for p in plans if p.filename == "gf-002-plus.woff2"]
    assert len(gf2_extb) == 1
    assert len(gf2_plus) == 1

    # Check Tail bins:
    # Total tail codepoints = 300 (core) + 10 (extb) + 5 (plus) = 315 cps
    # 315 / 135 -> bin 1 (135), bin 2 (135), bin 3 (45)
    tail_plans = [p for p in plans if p.slice_type == "tail"]
    assert len(tail_plans) > 0

    tail_logical_indices = sorted(set(p.logical_index for p in tail_plans))
    assert tail_logical_indices == [1, 2, 3]

    # Codepoints per logical bin must not exceed 135
    for b_idx in [1, 2]:
        bin_cps = sum(len(p.codepoints) for p in tail_plans if p.logical_index == b_idx)
        assert bin_cps == 135

    bin_3_cps = sum(len(p.codepoints) for p in tail_plans if p.logical_index == 3)
    assert bin_3_cps == 45

    # Full repertoire coverage and disjointness
    all_plan_cps = [cp for p in plans for cp in p.codepoints]
    all_owned_cps = set().union(*owned.values())
    assert set(all_plan_cps) == all_owned_cps
    assert len(all_plan_cps) == len(all_owned_cps)
