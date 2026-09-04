"""Synthetic minimal TrueType font generator for fast, offline testing."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib.tables._g_l_y_f import Glyph


def create_synthetic_ttf(
    codepoints: Iterable[int],
    family_name: str = "TestFont",
    style_name: str = "Regular",
    output_path: Path | None = None,
) -> bytes:
    """Create a minimal valid TrueType font with specified codepoints."""
    fb = FontBuilder(1000, isTTF=True)

    sorted_cps = sorted(set(codepoints))
    glyph_names = [".notdef"] + [f"uni{cp:04X}" for cp in sorted_cps]
    cmap = {cp: f"uni{cp:04X}" for cp in sorted_cps}

    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap)

    empty_glyph = Glyph()
    glyf_dict = {name: empty_glyph for name in glyph_names}
    fb.setupGlyf(glyf_dict)

    fb.setupHead(unitsPerEm=1000)
    fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": family_name,
            "styleName": style_name,
            "copyright": "Ministry of Digital Affairs, CNS11643 Open Data",
        }
    )
    fb.setupOS2()
    fb.setupPost()

    buf = io.BytesIO()
    fb.save(buf)
    data = buf.getvalue()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)

    return data


def create_synthetic_cns_zip(
    output_zip_path: Path,
    core_cps: Iterable[int],
    extb_cps: Iterable[int],
    plus_cps: Iterable[int],
    prefix: str = "TW-Sung",
) -> None:
    """Create a synthetic Fonts_*.zip matching official CNS11643 archive layout."""
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    core_data = create_synthetic_ttf(core_cps, family_name=f"{prefix}-Core")
    extb_data = create_synthetic_ttf(extb_cps, family_name=f"{prefix}-Ext-B")
    plus_data = create_synthetic_ttf(plus_cps, family_name=f"{prefix}-Plus")
    doc_text = f"{prefix}-98_1.ttf BMP\r\n{prefix}-Ext-B-98_1.ttf Plane 2\r\n".encode("utf-8-sig")

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{prefix}-98_1.ttf", core_data)
        zf.writestr(f"{prefix}-Ext-B-98_1.ttf", extb_data)
        zf.writestr(f"{prefix}-Plus-98_1.ttf", plus_data)
        zf.writestr("全字庫字型說明文件.txt", doc_text)
