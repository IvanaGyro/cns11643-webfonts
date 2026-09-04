"""End-to-end full package build test for TW-Sung and TW-Kai."""

import json
from pathlib import Path

from cns_webfont.builder import build_font_package
from tests.fixtures.synthetic_fonts import create_synthetic_cns_zip


def test_full_build_sung_and_kai(tmp_path: Path):
    """Verify building complete tw-sung and tw-kai packages with all required artifacts."""
    sung_zip = tmp_path / "Fonts_Sung.zip"
    kai_zip = tmp_path / "Fonts_Kai.zip"

    # Core, Ext-B, and Plus codepoints
    core_cps = {0x4E00, 0x4E01, 0x4E02}
    extb_cps = {0x20000, 0x20001}
    plus_cps = {0xF0000}

    create_synthetic_cns_zip(sung_zip, core_cps, extb_cps, plus_cps, prefix="TW-Sung")
    create_synthetic_cns_zip(kai_zip, core_cps, extb_cps, plus_cps, prefix="TW-Kai")

    google_strategy = Path("data/google-fonts/traditional-chinese_default.txt")
    google_meta = Path("data/google-fonts/metadata.json")

    sung_pkg_dir = tmp_path / "packages" / "tw-sung"
    kai_pkg_dir = tmp_path / "packages" / "tw-kai"

    # 1. Build TW-Sung
    res_sung = build_font_package(
        family="TW-Sung",
        zip_path=sung_zip,
        google_slices_path=google_strategy,
        google_metadata_path=google_meta,
        upstream_version="20260805",
        output_package_dir=sung_pkg_dir,
        package_scope="@cns11643",
    )

    assert res_sung.family == "TW-Sung"
    assert (sung_pkg_dir / "package.json").is_file()
    assert (sung_pkg_dir / "tw-sung.css").is_file()
    assert (sung_pkg_dir / "manifest.json").is_file()
    assert (sung_pkg_dir / "build-report.json").is_file()
    assert (sung_pkg_dir / "LICENSE-OFL.txt").is_file()
    assert (sung_pkg_dir / "NOTICE.md").is_file()
    assert (sung_pkg_dir / "README.md").is_file()
    assert (sung_pkg_dir / "woff2").is_dir()

    # Verify package.json metadata
    pkg_json = json.loads((sung_pkg_dir / "package.json").read_text(encoding="utf-8"))
    assert pkg_json["name"] == "@cns11643/tw-sung"
    assert pkg_json["version"] == "20260805.0.0"
    assert pkg_json["cns11643"]["upstreamVersion"] == "20260805"
    assert pkg_json["style"] == "./tw-sung.css"
    assert pkg_json["repository"]["url"] == "https://github.com/IvanaGyro/cns11643-webfonts"

    # 2. Build TW-Kai
    res_kai = build_font_package(
        family="TW-Kai",
        zip_path=kai_zip,
        google_slices_path=google_strategy,
        google_metadata_path=google_meta,
        upstream_version="20260805",
        output_package_dir=kai_pkg_dir,
        package_scope="@cns11643",
    )

    assert res_kai.family == "TW-Kai"
    assert (kai_pkg_dir / "package.json").is_file()
    assert (kai_pkg_dir / "tw-kai.css").is_file()
    assert (kai_pkg_dir / "manifest.json").is_file()
    assert (kai_pkg_dir / "woff2").is_dir()
