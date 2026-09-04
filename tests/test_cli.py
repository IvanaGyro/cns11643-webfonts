"""Unit tests for cns-webfont CLI."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cns_webfont.cli import main
from cns_webfont.models import UpstreamInfo
from tests.fixtures.synthetic_fonts import create_synthetic_cns_zip, create_synthetic_ttf


def test_cli_help():
    """Verify CLI help text and available subcommands."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "check-upstream" in result.output
    assert "download" in result.output
    assert "inspect" in result.output
    assert "validate" in result.output
    assert "build-all" in result.output


def test_cli_inspect(tmp_path: Path):
    """Verify inspect command on TrueType font."""
    ttf_path = tmp_path / "test.ttf"
    create_synthetic_ttf({0x4E00, 0x4E01}, output_path=ttf_path)

    runner = CliRunner()
    result = runner.invoke(main, ["inspect", str(ttf_path), "--role", "core"])
    assert result.exit_code == 0
    assert "Role: core" in result.output
    assert "Codepoint count: 2" in result.output


def test_cli_check_upstream():
    """Verify check-upstream command output."""
    mock_info = UpstreamInfo(
        version="20260805",
        release_date="2026-08-05",
        sung_url="http://example.com/sung.zip",
        kai_url="http://example.com/kai.zip",
        csv_url="http://example.com/list.csv",
        release_url="http://example.com/rel.txt",
    )
    with patch("cns_webfont.cli.check_upstream", return_value=mock_info):
        with patch("cns_webfont.cli.is_package_published", return_value=False):
            runner = CliRunner()
            result = runner.invoke(main, ["check-upstream"])
            assert result.exit_code == 0
            assert "Upstream version: 20260805" in result.output
            assert "UPDATE AVAILABLE" in result.output


def test_cli_build_all_offline(tmp_path: Path):
    """Verify build-all command with --offline flag."""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    sung_zip = sources_dir / "Fonts_Sung.zip"
    kai_zip = sources_dir / "Fonts_Kai.zip"

    create_synthetic_cns_zip(sung_zip, {0x4E00}, {0x20000}, {0xF0000}, prefix="TW-Sung")
    create_synthetic_cns_zip(kai_zip, {0x4E00}, {0x20000}, {0xF0000}, prefix="TW-Kai")

    output_dir = tmp_path / "packages"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "build-all",
            "--sources-dir",
            str(sources_dir),
            "--output-dir",
            str(output_dir),
            "--upstream-version",
            "20260805",
            "--offline",
        ],
    )
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "All packages built and validated successfully!" in result.output

    # Test validate command on output package
    val_res = runner.invoke(main, ["validate", str(output_dir / "tw-sung")])
    assert val_res.exit_code == 0
    assert "is valid!" in val_res.output
