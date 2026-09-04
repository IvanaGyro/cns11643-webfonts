"""Integration test for byte-level build reproducibility."""

from pathlib import Path

from cns_webfont.builder import build_font_package
from tests.fixtures.synthetic_fonts import create_synthetic_cns_zip


def test_build_reproducibility(tmp_path: Path):
    """Verify building font package twice yields 100% byte-for-byte identical output."""
    zip_path = tmp_path / "Fonts_Sung.zip"
    core_cps = {0x4E00, 0x4E01, 0x4E02}
    extb_cps = {0x20000, 0x20001}
    plus_cps = {0xF0000}
    create_synthetic_cns_zip(zip_path, core_cps, extb_cps, plus_cps, prefix="TW-Sung")

    google_strategy = Path("data/google-fonts/traditional-chinese_default.txt")
    google_meta = Path("data/google-fonts/metadata.json")

    build1_dir = tmp_path / "build1"
    build2_dir = tmp_path / "build2"

    fixed_timestamp = 1700000000

    res1 = build_font_package(
        family="TW-Sung",
        zip_path=zip_path,
        google_slices_path=google_strategy,
        google_metadata_path=google_meta,
        upstream_version="20260805",
        output_package_dir=build1_dir,
        package_scope="@cns11643",
        recipe_revision=0,
        deterministic_timestamp=fixed_timestamp,
    )

    res2 = build_font_package(
        family="TW-Sung",
        zip_path=zip_path,
        google_slices_path=google_strategy,
        google_metadata_path=google_meta,
        upstream_version="20260805",
        output_package_dir=build2_dir,
        package_scope="@cns11643",
        recipe_revision=0,
        deterministic_timestamp=fixed_timestamp,
    )

    assert res1.manifest["statistics"] == res2.manifest["statistics"]

    # Compare every generated file in build1 vs build2
    files1 = sorted([p.relative_to(build1_dir) for p in build1_dir.rglob("*") if p.is_file()])
    files2 = sorted([p.relative_to(build2_dir) for p in build2_dir.rglob("*") if p.is_file()])

    assert files1 == files2
    assert len(files1) > 0

    for rel_p in files1:
        bytes1 = (build1_dir / rel_p).read_bytes()
        bytes2 = (build2_dir / rel_p).read_bytes()
        assert bytes1 == bytes2, f"Reproducibility failure for file: {rel_p}"
