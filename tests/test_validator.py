"""Unit tests for package validation and regression guards."""

from pathlib import Path

import pytest

from cns_webfont.subset import subset_font_to_woff2
from cns_webfont.validator import (
    ValidationError,
    check_coverage_regression,
    check_package_unpacked_size,
    validate_shard_woff2,
)
from tests.fixtures.synthetic_fonts import create_synthetic_ttf


def test_validate_shard_woff2(tmp_path: Path):
    """Verify WOFF2 shard cmap validation."""
    source_ttf = tmp_path / "source.ttf"
    create_synthetic_ttf({0x4E00, 0x4E01}, output_path=source_ttf)

    woff2_path = tmp_path / "shard.woff2"
    subset_font_to_woff2(source_ttf, {0x4E00}, woff2_path)

    # Success case
    validate_shard_woff2(woff2_path, {0x4E00})

    # Mismatch case
    with pytest.raises(ValidationError, match="cmap mismatch"):
        validate_shard_woff2(woff2_path, {0x4E01})


def test_check_coverage_regression():
    """Verify coverage regression gate fails when retention drops below 98%."""
    # Retaining 99% coverage -> OK
    check_coverage_regression(current_codepoint_count=990, previous_codepoint_count=1000)

    # Retaining 97% coverage -> FAIL
    with pytest.raises(ValidationError, match="Coverage regression detected"):
        check_coverage_regression(current_codepoint_count=970, previous_codepoint_count=1000)


def test_check_package_unpacked_size_guard(tmp_path: Path):
    """Verify 90 MiB size guard enforcement."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()

    # Small package passes
    (pkg_dir / "package.json").write_text('{"files": ["test.txt"]}', encoding="utf-8")
    (pkg_dir / "test.txt").write_bytes(b"hello")

    total = check_package_unpacked_size(pkg_dir, max_unpacked_bytes=1000)
    assert total > 0

    # Oversized package triggers guard
    with pytest.raises(ValidationError, match="Package size guard triggered"):
        check_package_unpacked_size(pkg_dir, max_unpacked_bytes=10)
