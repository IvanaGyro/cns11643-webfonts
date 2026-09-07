"""Unit tests for upstream module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cns_webfont.upstream import (
    UpstreamError,
    check_upstream,
    download_file,
    get_published_revisions,
    is_package_published,
    make_package_version,
    parse_csv_file_list,
    parse_release_txt,
    resolve_target_release,
)

SAMPLE_RELEASE_TXT = """============================================================
@檔案說明：

1.檔案名稱：release.txt
  版本：20260805
  下載路徑：https://www.cns11643.gov.tw/opendata/release.txt

2.檔案名稱：Fonts_Kai.zip
  版本：20260805
  下載路徑：https://www.cns11643.gov.tw/opendata/Fonts_Kai.zip

3.檔案名稱：Fonts_Sung.zip
  版本：20260805
  下載路徑：https://www.cns11643.gov.tw/opendata/Fonts_Sung.zip
================================================================================
"""

SAMPLE_CSV_CP950 = "名稱,所屬,類別,說明\r\nFonts_Sung.zip,-,檔案,全字庫正宋體字型\r\n".encode(
    "cp950"
)


def test_parse_release_txt():
    """Verify release.txt parsing extracts file versions."""
    versions = parse_release_txt(SAMPLE_RELEASE_TXT)
    assert versions["Fonts_Sung.zip"] == "20260805"
    assert versions["Fonts_Kai.zip"] == "20260805"
    assert versions["release.txt"] == "20260805"


def test_parse_release_txt_empty():
    """Verify empty release.txt raises UpstreamError."""
    with pytest.raises(UpstreamError, match="No file versions"):
        parse_release_txt("Invalid text without version markers")


def test_parse_csv_file_list_cp950():
    """Verify parsing cp950-encoded CSV."""
    rows = parse_csv_file_list(SAMPLE_CSV_CP950)
    assert len(rows) == 1
    assert rows[0]["名稱"] == "Fonts_Sung.zip"


def test_check_upstream_success():
    """Verify check_upstream succeeds with matching versions."""
    with patch("cns_webfont.upstream._get_with_ssl_fallback") as mock_get:
        # Mock release.txt and OpenDataFilesList.csv responses
        rel_resp = MagicMock()
        rel_resp.content = SAMPLE_RELEASE_TXT.encode("utf-8")

        csv_resp = MagicMock()
        csv_resp.content = SAMPLE_CSV_CP950

        mock_get.side_effect = [rel_resp, csv_resp]

        info = check_upstream()
        assert info.version == "20260805"
        assert info.release_date == "2026-08-05"
        assert info.sung_url.endswith("Fonts_Sung.zip")
        assert info.kai_url.endswith("Fonts_Kai.zip")


def test_check_upstream_version_mismatch():
    """Verify failure when Sung and Kai versions differ in release.txt."""
    mismatched_release = """
檔案名稱：Fonts_Kai.zip
版本：20260805

檔案名稱：Fonts_Sung.zip
版本：20260901
"""
    with patch("cns_webfont.upstream._get_with_ssl_fallback") as mock_get:
        rel_resp = MagicMock()
        rel_resp.content = mismatched_release.encode("utf-8")
        mock_get.return_value = rel_resp

        with pytest.raises(UpstreamError, match="Sung version .* != Kai version"):
            check_upstream()


def test_check_upstream_csv_mismatch():
    """Verify failure when CSV version disagrees with release.txt."""
    csv_with_version = (
        "名稱,版本,類別,說明\r\nFonts_Sung.zip,20260101,檔案,全字庫正宋體字型\r\n".encode("cp950")
    )

    with patch("cns_webfont.upstream._get_with_ssl_fallback") as mock_get:
        rel_resp = MagicMock()
        rel_resp.content = SAMPLE_RELEASE_TXT.encode("utf-8")

        csv_resp = MagicMock()
        csv_resp.content = csv_with_version

        mock_get.side_effect = [rel_resp, csv_resp]

        with pytest.raises(UpstreamError, match="CSV Sung version .* != release.txt version"):
            check_upstream()


def test_download_file(tmp_path: Path):
    """Verify download_file streams content and checks SHA-256."""
    test_content = b"CNS11643 font file test content"
    expected_hash = "7aa8440c067fc2a92e8e9abc67db89d799112ab29fe855e99b64b6a72765bb2d"

    dest = tmp_path / "test.bin"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [test_content[:10], test_content[10:]]
        mock_resp.__enter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        # Valid hash
        actual_hash = download_file(
            "http://example.com/test.bin", dest, expected_sha256=expected_hash
        )
        assert actual_hash == expected_hash
        assert dest.read_bytes() == test_content

        # Invalid hash should raise error
        with pytest.raises(UpstreamError, match="SHA256 mismatch"):
            download_file("http://example.com/test.bin", dest, expected_sha256="wrong_hash")


def test_make_package_version():
    """Verify version scheme <YYYYMMDD>.<recipe_revision>.0."""
    assert make_package_version("20260805", 0) == "20260805.0.0"
    assert make_package_version("20260805", 2) == "20260805.2.0"


def test_is_package_published():
    """Verify checking npm registry published state."""
    pkg_name = "@test-scope/tw-sung"

    with patch("requests.get") as mock_get:
        # 404 not published
        mock_get.return_value.status_code = 404
        assert not is_package_published(pkg_name, "20260805", 0)

        # Published package
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "versions": {
                "20260805.0.0": {
                    "version": "20260805.0.0",
                    "cns11643": {
                        "upstreamVersion": "20260805",
                        "builderRevision": 0,
                    },
                }
            }
        }
        mock_get.return_value = mock_resp
        assert is_package_published(pkg_name, "20260805", 0)
        assert not is_package_published(pkg_name, "20260805", 1)
        assert not is_package_published(pkg_name, "20261110", 0)


def test_get_published_revisions():
    """Verify extracting published revisions from npm versions map."""
    pkg_name = "@test-scope/tw-sung"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "versions": {
                "20260805.0.0": {},
                "20260805.1.0": {},
                "20260805.3.0": {},
                "20251201.0.0": {},
            }
        }
        mock_get.return_value = mock_resp

        assert get_published_revisions(pkg_name, "20260805") == [0, 1, 3]
        assert get_published_revisions(pkg_name, "20251201") == [0]
        assert get_published_revisions(pkg_name, "20260101") == []


def test_resolve_target_release_auto_unreleased():
    """When version is not published on npm, auto targets rev 0 with needs_build=True."""
    with patch("cns_webfont.upstream.get_published_revisions", return_value=[]):
        target_rev, needs_build = resolve_target_release("@test", "20260805", "auto")
        assert target_rev == 0
        assert needs_build is True


def test_resolve_target_release_auto_already_published():
    """When version is already published, auto-release skips build."""
    with patch("cns_webfont.upstream.get_published_revisions", return_value=[0, 1]):
        target_rev, needs_build = resolve_target_release(
            "@test", "20260805", "auto", force_build=False
        )
        assert target_rev == 1
        assert needs_build is False


def test_resolve_target_release_auto_force_build():
    """When force_build is True and versions are published, auto increments revision."""
    with patch("cns_webfont.upstream.get_published_revisions", return_value=[0, 1]):
        target_rev, needs_build = resolve_target_release(
            "@test", "20260805", "auto", force_build=True
        )
        assert target_rev == 2
        assert needs_build is True


def test_resolve_target_release_explicit_revision():
    """Explicit revision respects published state unless force_build is True."""
    with patch("cns_webfont.upstream.get_published_revisions", return_value=[0, 1]):
        # Revision 1 is published -> skip build
        target_rev, needs_build = resolve_target_release(
            "@test", "20260805", "1", force_build=False
        )
        assert target_rev == 1
        assert needs_build is False

        # Revision 1 is published, but force_build=True -> build anyway
        target_rev, needs_build = resolve_target_release("@test", "20260805", "1", force_build=True)
        assert target_rev == 1
        assert needs_build is True

        # Revision 2 is unreleased -> build
        target_rev, needs_build = resolve_target_release(
            "@test", "20260805", "2", force_build=False
        )
        assert target_rev == 2
        assert needs_build is True
