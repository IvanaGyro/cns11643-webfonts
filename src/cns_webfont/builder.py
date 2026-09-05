"""Font package build orchestrator."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from cns_webfont.cmap import resolve_cmap_ownership
from cns_webfont.css import generate_css
from cns_webfont.fonts import extract_and_classify_fonts
from cns_webfont.google_slices import parse_google_slices
from cns_webfont.manifest import generate_build_report, generate_manifest
from cns_webfont.models import PhysicalShard
from cns_webfont.slicing import plan_shards
from cns_webfont.subset import subset_font_to_woff2
from cns_webfont.upstream import make_package_version
from cns_webfont.validator import (
    check_coverage_regression,
    validate_package,
)

logger = logging.getLogger(__name__)

BUILDER_VERSION = "0.1.0"

OFL_LICENSE_TEXT = """Copyright (c) 2026 Ministry of Digital Affairs, Republic of China (Taiwan)

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
https://openfontlibrary.org/open-font-license

-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Source or Binary forms, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless prominent written permission is granted by the
corresponding Copyright Holder. This restriction only applies to the
primary font name as presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
"""


def _generate_notice(
    family: str,
    upstream_version: str,
    filenames: list[str],
) -> str:
    """Generate NOTICE.md with attribution and RFN inspection details."""
    files_list = "\n".join(f"- `{fn}`" for fn in filenames)
    return (
        f"# CNS11643 {family} Web Font — Notice & Attribution\n\n"
        f"## Source Information\n\n"
        f"- **Authoritative Source**: 數位發展部 (Ministry of Digital Affairs), Taiwan\n"
        f"- **Project**: CNS11643 中文標準交換碼全字庫 (Chinese Standard Interchange Code)\n"
        f"- **Open Data Portal**: https://data.gov.tw/dataset/5961\n"
        f"- **Official Website**: https://www.cns11643.gov.tw\n"
        f"- **Upstream Version**: `{upstream_version}`\n\n"
        f"## Original Font Binaries\n\n"
        f"{files_list}\n\n"
        f"## Reserved Font Name (RFN) Assessment\n\n"
        f"Inspection of upstream font files and metadata shows that no Reserved Font Name (RFN) "
        f"is declared. The original names `{family}` and its derivatives are redistributed "
        f"under the terms of the SIL Open Font License 1.1.\n"
    )


def _generate_package_readme(
    family: str,
    package_name: str,
    package_version: str,
) -> str:
    """Generate package-specific README.md."""
    css_name = f"{family.lower()}.css"
    return (
        f"# {package_name}\n\n"
        f"Production-quality Web Font distribution of CNS11643 {family} "
        f"sliced with Google Fonts Traditional Chinese strategy and CNS rare tail bins.\n\n"
        f"## Usage\n\n"
        f"### via npm\n\n"
        f"```bash\n"
        f"npm install {package_name}\n"
        f"```\n\n"
        f"Import in your CSS:\n\n"
        f"```css\n"
        f'@import "{package_name}/{css_name}";\n\n'
        f"body {{\n"
        f'  font-family: "{family}", serif;\n'
        f"}}\n"
        f"```\n\n"
        f"### via jsDelivr CDN (Production Pinned)\n\n"
        f"```html\n"
        f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/{package_name}@{package_version}/{css_name}">\n'
        f"```\n\n"
        f"## License\n\n"
        f"Font software is licensed under the SIL Open Font License 1.1 (see LICENSE-OFL.txt).\n"
    )


def resolve_package_scope(scope: str | None = None) -> str:
    """Resolve npm package scope from argument or environment variables.

    Priority:
    1. Explicit scope argument (if provided and non-empty)
    2. Environment variable NPM_SCPOE (supports spelling variants)
    3. Environment variable NPM_SCOPE
    4. Default fallback: '@cns11643'

    Ensures the returned scope starts with '@' and has trailing slashes removed.
    """
    raw = scope or os.environ.get("NPM_SCPOE") or os.environ.get("NPM_SCOPE") or "@cns11643"
    cleaned = raw.strip().rstrip("/")
    if not cleaned.startswith("@"):
        cleaned = f"@{cleaned}"
    return cleaned


@dataclass
class BuildResult:
    """Summary of a successful package build."""

    family: str
    package_name: str
    package_version: str
    package_dir: Path
    manifest: dict
    build_report: dict


def build_font_package(
    family: str,
    zip_path: Path,
    google_slices_path: Path,
    google_metadata_path: Path,
    upstream_version: str,
    output_package_dir: Path,
    package_scope: str | None = None,
    recipe_revision: int = 0,
    deterministic_timestamp: int = 1700000000,
    previous_manifest_path: Path | None = None,
    work_dir: Path | None = None,
) -> BuildResult:
    """Build a complete production-ready webfont package for TW-Sung or TW-Kai.

    Pipeline:
    1. Extract and inspect source TrueType fonts.
    2. Resolve deterministic cmap ownership across core, extb, plus.
    3. Plan physical shards using Google TC slices and CNS tail bins.
    4. Subset to WOFF2 with timestamp normalization.
    5. Generate CSS stylesheet with unicode-range compression.
    6. Generate manifest.json and build-report.json.
    7. Generate package.json, README.md, LICENSE-OFL.txt, NOTICE.md.
    8. Validate structure, cmap alignment, coverage regression, and package size limit.

    Args:
        family: Font family name ('TW-Sung' or 'TW-Kai').
        zip_path: Path to source zip archive (Fonts_Sung.zip or Fonts_Kai.zip).
        google_slices_path: Path to pinned traditional-chinese_default.txt.
        google_metadata_path: Path to pinned google-fonts metadata.json.
        upstream_version: Upstream version string (e.g. '20260805').
        output_package_dir: Target output package directory.
        package_scope: npm package scope (defaults to env NPM_SCPOE / NPM_SCOPE or '@cns11643').
        recipe_revision: Recipe revision integer.
        deterministic_timestamp: Timestamp for byte reproducibility.
        previous_manifest_path: Optional path to previous release manifest for regression checks.
        work_dir: Optional scratch directory for extraction.

    Returns:
        BuildResult instance.
    """
    resolved_scope = resolve_package_scope(package_scope)
    pkg_slug = family.lower()
    pkg_name = f"{resolved_scope}/{pkg_slug}"
    pkg_version = make_package_version(upstream_version, recipe_revision)

    if work_dir is None:
        extract_dir = output_package_dir.parent / f"_extract_{pkg_slug}"
    else:
        extract_dir = work_dir / f"_extract_{pkg_slug}"

    logger.info("Building %s (%s) from %s", family, pkg_name, zip_path.name)

    # 1. Extract and inspect source fonts
    fonts_by_role = extract_and_classify_fonts(zip_path, extract_dir)
    source_fonts = [fonts_by_role[r] for r in ["core", "extb", "plus"] if r in fonts_by_role]

    # 2. Ownership resolution and duplicate detection
    dup_report_path = output_package_dir / "build" / "duplicates.json"
    owned_by_role, duplicates = resolve_cmap_ownership(
        fonts_by_role, duplicates_output_path=dup_report_path
    )

    # 3. Google slicing strategy
    google_slices = parse_google_slices(google_slices_path)
    google_meta = json.loads(google_metadata_path.read_text(encoding="utf-8"))
    google_commit = google_meta.get("commit", "unknown")

    # 4. Plan physical shards
    shard_plans = plan_shards(owned_by_role, google_slices, tail_bin_size=135)

    # 5. Subset each shard to WOFF2
    woff2_out_dir = output_package_dir / "woff2"
    woff2_out_dir.mkdir(parents=True, exist_ok=True)

    physical_shards: list[PhysicalShard] = []

    for plan in shard_plans:
        role_font = fonts_by_role[plan.source_role]
        out_file = woff2_out_dir / plan.filename

        size_bytes, sha256_hex = subset_font_to_woff2(
            source_ttf_path=role_font.path,
            codepoints=set(plan.codepoints),
            output_woff2_path=out_file,
            deterministic_timestamp=deterministic_timestamp,
        )

        physical_shards.append(
            PhysicalShard(
                filename=plan.filename,
                logical_index=plan.logical_index,
                slice_type=plan.slice_type,
                source_role=plan.source_role,
                codepoints=plan.codepoints,
                unicode_ranges=plan.unicode_ranges,
                byte_size=size_bytes,
                sha256=sha256_hex,
            )
        )

    # 6. Generate CSS
    css_content = generate_css(family, shard_plans, rel_woff2_dir="./woff2")
    css_path = output_package_dir / f"{pkg_slug}.css"
    css_path.write_text(css_content, encoding="utf-8")

    # 7. Generate Manifest and Build Report
    manifest_data = generate_manifest(
        family=family,
        upstream_version=upstream_version,
        package_version=pkg_version,
        builder_version=BUILDER_VERSION,
        sources=source_fonts,
        shards=physical_shards,
        google_commit=google_commit,
        tail_bin_size=135,
    )
    manifest_path = output_package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    build_report = generate_build_report(family, source_fonts, physical_shards)
    report_path = output_package_dir / "build-report.json"
    report_path.write_text(json.dumps(build_report, indent=2), encoding="utf-8")

    # 8. Package distribution files (LICENSE, NOTICE, README, package.json)
    (output_package_dir / "LICENSE-OFL.txt").write_text(OFL_LICENSE_TEXT, encoding="utf-8")
    notice_text = _generate_notice(family, upstream_version, [f.filename for f in source_fonts])
    (output_package_dir / "NOTICE.md").write_text(notice_text, encoding="utf-8")
    readme_text = _generate_package_readme(family, pkg_name, pkg_version)
    (output_package_dir / "README.md").write_text(readme_text, encoding="utf-8")

    repo_slug = os.environ.get("GITHUB_REPOSITORY", "IvanaGyro/cns11643-webfonts")
    package_json_data = {
        "name": pkg_name,
        "version": pkg_version,
        "description": f"CNS11643 {family} Web Font package",
        "license": "OFL-1.1",
        "repository": {
            "type": "git",
            "url": f"https://github.com/{repo_slug}",
        },
        "homepage": f"https://github.com/{repo_slug}#readme",
        "bugs": {
            "url": f"https://github.com/{repo_slug}/issues",
        },
        "publishConfig": {
            "access": "public",
        },
        "style": f"./{pkg_slug}.css",
        "files": [
            f"{pkg_slug}.css",
            "woff2",
            "manifest.json",
            "README.md",
            "LICENSE-OFL.txt",
            "NOTICE.md",
        ],
        "cns11643": {
            "family": family,
            "upstreamVersion": upstream_version,
            "builderRevision": recipe_revision,
            "sourceSha256": {s.role: s.sha256 for s in source_fonts},
            "slicingStrategy": manifest_data["slicingStrategy"],
        },
    }
    (output_package_dir / "package.json").write_text(
        json.dumps(package_json_data, indent=2), encoding="utf-8"
    )

    # 9. Validate entire package
    validate_package(output_package_dir)

    # Check regression if previous manifest provided
    if previous_manifest_path and previous_manifest_path.is_file():
        prev_data = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
        prev_cps = prev_data.get("statistics", {}).get("uniqueCodepoints", 0)
        curr_cps = manifest_data["statistics"]["uniqueCodepoints"]
        check_coverage_regression(curr_cps, prev_cps)

    # Clean up extraction directory
    shutil.rmtree(extract_dir, ignore_errors=True)

    logger.info("Package %s built successfully at %s", pkg_name, output_package_dir)
    return BuildResult(
        family=family,
        package_name=pkg_name,
        package_version=pkg_version,
        package_dir=output_package_dir,
        manifest=manifest_data,
        build_report=build_report,
    )
