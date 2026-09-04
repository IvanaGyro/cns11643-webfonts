"""Upstream version detection, validation, and file downloading."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import warnings
from pathlib import Path
from typing import Any

import requests
import urllib3

from cns_webfont.models import UpstreamInfo

logger = logging.getLogger(__name__)

DATA_GOV_TW_DATASET_URL = "https://data.gov.tw/dataset/5961"
DATA_GOV_TW_API_URL = "https://data.gov.tw/api/v2/rest/dataset/5961"
CNS_BASE_URL = "https://www.cns11643.gov.tw/opendata"


class UpstreamError(Exception):
    """Raised when upstream version check or download fails."""


def _get_with_ssl_fallback(url: str, timeout: int = 30) -> requests.Response:
    """Fetch URL with SSL fallback for Taiwan government eCA certificate compatibility."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.SSLError as ssl_err:
        logger.warning(
            "SSL verification failed for %s (%s). Falling back to unverified request.",
            url,
            ssl_err,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, verify=False, timeout=timeout)
            response.raise_for_status()
            return response


def parse_release_txt(content: str) -> dict[str, str]:
    """Parse release.txt and extract file versions.

    Expected format:
    1.檔案名稱：release.txt
      版本：20260805
      下載路徑：https://www.cns11643.gov.tw/opendata/release.txt
    2.檔案名稱：Fonts_Kai.zip
      版本：20260805
    3.檔案名稱：Fonts_Sung.zip
      版本：20260805

    Returns:
        Mapping of filename -> version string.
    """
    versions: dict[str, str] = {}
    pattern = re.compile(
        r"檔案名稱：\s*([^\r\n]+)[\r\n]+\s*版本：\s*([0-9]{8})",
        re.MULTILINE,
    )
    for match in pattern.finditer(content):
        filename = match.group(1).strip()
        version = match.group(2).strip()
        versions[filename] = version

    if not versions:
        raise UpstreamError("No file versions found in release.txt")
    return versions


def parse_csv_file_list(raw_bytes: bytes) -> list[dict[str, str]]:
    """Parse OpenDataFilesList.csv supporting cp950 or utf-8 encodings.

    Returns:
        List of row dicts from the CSV.
    """
    decoded = ""
    for enc in ["cp950", "utf-8-sig", "utf-8", "big5"]:
        try:
            decoded = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not decoded:
        raise UpstreamError("Failed to decode OpenDataFilesList.csv with supported encodings")

    reader = csv.DictReader(io.StringIO(decoded))
    return list(reader)


def check_upstream(
    cns_base: str = CNS_BASE_URL,
    dataset_api_url: str = DATA_GOV_TW_API_URL,
) -> UpstreamInfo:
    """Check official upstream for dataset versions and validate consistency.

    Validates:
    1. Fonts_Sung.zip and Fonts_Kai.zip versions exist in release.txt.
    2. Fonts_Sung.zip version == Fonts_Kai.zip version.
    3. If CSV specifies versions, ensure CSV version == release.txt version.
       If mismatch occurs, raise UpstreamError (FAIL, DO NOT PUBLISH).

    Returns:
        UpstreamInfo metadata.
    """
    csv_url = f"{cns_base}/OpenDataFilesList.csv"
    release_url = f"{cns_base}/release.txt"
    sung_url = f"{cns_base}/Fonts_Sung.zip"
    kai_url = f"{cns_base}/Fonts_Kai.zip"

    # Secondary validation source: release.txt
    rel_resp = _get_with_ssl_fallback(release_url)
    rel_text = rel_resp.content.decode("utf-8-sig", errors="replace")
    release_versions = parse_release_txt(rel_text)

    sung_ver = release_versions.get("Fonts_Sung.zip")
    kai_ver = release_versions.get("Fonts_Kai.zip")

    if not sung_ver or not kai_ver:
        raise UpstreamError(f"Missing Sung or Kai version in release.txt: {release_versions}")

    if sung_ver != kai_ver:
        raise UpstreamError(f"Sung version ({sung_ver}) != Kai version ({kai_ver}) in release.txt")

    # Primary source: OpenDataFilesList.csv
    csv_resp = _get_with_ssl_fallback(csv_url)
    csv_rows = parse_csv_file_list(csv_resp.content)

    # If CSV schema includes version columns (e.g. 'version' or '版本'), validate consistency
    for row in csv_rows:
        filename = row.get("名稱") or row.get("filename") or ""
        csv_v = row.get("版本") or row.get("version")
        if csv_v:
            if filename == "Fonts_Sung.zip" and csv_v != sung_ver:
                raise UpstreamError(
                    f"CSV Sung version ({csv_v}) != release.txt version ({sung_ver})"
                )
            if filename == "Fonts_Kai.zip" and csv_v != kai_ver:
                raise UpstreamError(f"CSV Kai version ({csv_v}) != release.txt version ({kai_ver})")

    # Release date from version string YYYYMMDD
    release_date = f"{sung_ver[:4]}-{sung_ver[4:6]}-{sung_ver[6:]}"

    return UpstreamInfo(
        version=sung_ver,
        release_date=release_date,
        sung_url=sung_url,
        kai_url=kai_url,
        csv_url=csv_url,
        release_url=release_url,
    )


def download_file(
    url: str,
    dest_path: Path,
    expected_sha256: str | None = None,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Download a file with streaming SHA-256 calculation.

    Returns:
        Hex-encoded SHA-256 digest of the downloaded file.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    hasher = hashlib.sha256()

    with requests.get(url, stream=True, timeout=60, verify=False) as response:
        response.raise_for_status()
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    hasher.update(chunk)
                    f.write(chunk)

    actual_sha256 = hasher.hexdigest()
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        temp_path.unlink(missing_ok=True)
        raise UpstreamError(
            f"SHA256 mismatch for {url}: expected {expected_sha256}, got {actual_sha256}"
        )

    temp_path.replace(dest_path)
    return actual_sha256


def make_package_version(upstream_version: str, recipe_revision: int = 0) -> str:
    """Format package version following <YYYYMMDD>.<recipe_revision>.0 scheme."""
    return f"{upstream_version}.{recipe_revision}.0"


def check_npm_package_metadata(
    package_name: str,
    registry_url: str = "https://registry.npmjs.org",
) -> dict[str, Any] | None:
    """Fetch published package metadata from npm registry."""
    url = f"{registry_url.rstrip('/')}/{package_name}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return res.json()
    except Exception as err:
        logger.warning("Failed to check npm registry for %s: %s", package_name, err)
        return None


def is_package_published(
    package_name: str,
    upstream_version: str,
    recipe_revision: int = 0,
    registry_url: str = "https://registry.npmjs.org",
) -> bool:
    """Check if the specific upstream version and recipe revision is already on npm."""
    metadata = check_npm_package_metadata(package_name, registry_url=registry_url)
    if not metadata:
        return False

    target_version = make_package_version(upstream_version, recipe_revision)
    versions = metadata.get("versions", {})
    if target_version not in versions:
        return False

    # Check cns11643 metadata if present
    pkg_doc = versions[target_version]
    cns_meta = pkg_doc.get("cns11643", {})
    if cns_meta.get("upstreamVersion") == upstream_version and (
        cns_meta.get("builderRevision") == recipe_revision
    ):
        return True

    return True
