"""Unit tests for manifest and build report generation."""

from pathlib import Path

from cns_webfont.manifest import generate_build_report, generate_manifest
from cns_webfont.models import PhysicalShard, SourceFont


def test_generate_manifest():
    """Verify manifest dictionary matches expected schema and counts."""
    sources = [
        SourceFont(
            role="core",
            filename="TW-Sung-98_1.ttf",
            path=Path("TW-Sung-98_1.ttf"),
            sha256="aabbcc",
            glyph_count=100,
            codepoints={0x4E00, 0x4E01},
        )
    ]
    shards = [
        PhysicalShard(
            filename="gf-001-core.woff2",
            logical_index=1,
            slice_type="google",
            source_role="core",
            codepoints=[0x4E00, 0x4E01],
            unicode_ranges="U+4E00-4E01",
            byte_size=1200,
            sha256="112233",
        )
    ]

    manifest = generate_manifest(
        family="TW-Sung",
        upstream_version="20260805",
        package_version="20260805.0.0",
        builder_version="0.1.0",
        sources=sources,
        shards=shards,
        google_commit="1d38a7d",
    )

    assert manifest["family"] == "TW-Sung"
    assert manifest["upstreamVersion"] == "20260805"
    assert manifest["packageVersion"] == "20260805.0.0"
    assert manifest["statistics"]["uniqueCodepoints"] == 2
    assert manifest["statistics"]["googleCoveredCodepoints"] == 2
    assert manifest["statistics"]["tailCodepoints"] == 0
    assert manifest["statistics"]["woff2Files"] == 1
    assert manifest["statistics"]["totalWoff2Bytes"] == 1200
    assert len(manifest["shards"]) == 1


def test_generate_build_report(tmp_path: Path):
    """Verify build report metrics calculations."""
    fake_src = tmp_path / "src.ttf"
    fake_src.write_bytes(b"x" * 5000)

    sources = [
        SourceFont(
            role="core",
            filename="src.ttf",
            path=fake_src,
            sha256="abc",
            glyph_count=10,
            codepoints={1, 2},
        )
    ]
    shards = [
        PhysicalShard(
            filename="s1.woff2",
            logical_index=1,
            slice_type="google",
            source_role="core",
            codepoints=[1],
            unicode_ranges="U+1",
            byte_size=100,
            sha256="a",
        ),
        PhysicalShard(
            filename="s2.woff2",
            logical_index=2,
            slice_type="tail",
            source_role="core",
            codepoints=[2],
            unicode_ranges="U+2",
            byte_size=200,
            sha256="b",
        ),
    ]

    report = generate_build_report("TW-Sung", sources, shards)
    assert report["family"] == "TW-Sung"
    assert report["totalSourceBytes"] == 5000
    assert report["totalWoff2Bytes"] == 300
    assert report["numberOfShards"] == 2
    assert report["averageShardSizeBytes"] == 150.0
    assert report["medianShardSizeBytes"] == 150.0
    assert report["largestShard"]["filename"] == "s2.woff2"
    assert report["googleCoveredBytes"] == 100
    assert report["tailBytes"] == 200
