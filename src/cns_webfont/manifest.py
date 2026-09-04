"""Manifest and build performance report generator."""

from __future__ import annotations

import statistics
from typing import Any, Sequence

from cns_webfont.models import PhysicalShard, SourceFont


def generate_manifest(
    family: str,
    upstream_version: str,
    package_version: str,
    builder_version: str,
    sources: Sequence[SourceFont],
    shards: Sequence[PhysicalShard],
    google_commit: str,
    tail_bin_size: int = 135,
) -> dict[str, Any]:
    """Generate manifest dictionary matching the specification schema."""
    unique_codepoints = sum(len(s.codepoints) for s in shards)
    google_covered = sum(len(s.codepoints) for s in shards if s.slice_type == "google")
    tail_codepoints = sum(len(s.codepoints) for s in shards if s.slice_type == "tail")
    total_woff2_bytes = sum(s.byte_size for s in shards)

    sources_meta = [
        {
            "role": src.role,
            "filename": src.filename,
            "sha256": src.sha256,
            "codepoints": len(src.codepoints),
            "glyphs": src.glyph_count,
        }
        for src in sources
    ]

    shards_meta = [
        {
            "filename": shard.filename,
            "logicalSlice": shard.logical_index,
            "sliceType": shard.slice_type,
            "source": shard.source_role,
            "codepointCount": len(shard.codepoints),
            "unicodeRanges": shard.unicode_ranges,
            "bytes": shard.byte_size,
            "sha256": shard.sha256,
        }
        for shard in shards
    ]

    return {
        "family": family,
        "upstreamVersion": upstream_version,
        "packageVersion": package_version,
        "builderVersion": builder_version,
        "sources": sources_meta,
        "slicingStrategy": {
            "type": "google-tc-plus-cns-tail",
            "googleRepository": "googlefonts/nam-files",
            "googleCommit": google_commit,
            "googleStrategy": "traditional-chinese_default.txt",
            "tailBinSize": tail_bin_size,
        },
        "statistics": {
            "uniqueCodepoints": unique_codepoints,
            "googleCoveredCodepoints": google_covered,
            "tailCodepoints": tail_codepoints,
            "woff2Files": len(shards),
            "totalWoff2Bytes": total_woff2_bytes,
        },
        "shards": shards_meta,
    }


def generate_build_report(
    family: str,
    sources: Sequence[SourceFont],
    shards: Sequence[PhysicalShard],
) -> dict[str, Any]:
    """Generate build performance report with size and distribution metrics."""
    total_source_bytes = sum(src.path.stat().st_size for src in sources if src.path.is_file())
    shard_sizes = [s.byte_size for s in shards] if shards else [0]
    total_woff2_bytes = sum(shard_sizes)

    sorted_sizes = sorted(shard_sizes)
    avg_size = round(statistics.mean(shard_sizes), 1) if shard_sizes else 0
    median_size = round(statistics.median(shard_sizes), 1) if shard_sizes else 0

    # 95th percentile size
    if len(sorted_sizes) > 1:
        p95_idx = int(0.95 * len(sorted_sizes))
        p95_size = sorted_sizes[min(p95_idx, len(sorted_sizes) - 1)]
    else:
        p95_size = sorted_sizes[0]

    largest_shard = max(shards, key=lambda s: s.byte_size) if shards else None
    largest_meta = (
        {
            "filename": largest_shard.filename,
            "bytes": largest_shard.byte_size,
            "codepointCount": len(largest_shard.codepoints),
        }
        if largest_shard
        else {}
    )

    google_bytes = sum(s.byte_size for s in shards if s.slice_type == "google")
    tail_bytes = sum(s.byte_size for s in shards if s.slice_type == "tail")

    return {
        "family": family,
        "totalSourceBytes": total_source_bytes,
        "totalWoff2Bytes": total_woff2_bytes,
        "numberOfShards": len(shards),
        "averageShardSizeBytes": avg_size,
        "medianShardSizeBytes": median_size,
        "p95ShardSizeBytes": p95_size,
        "largestShard": largest_meta,
        "googleCoveredBytes": google_bytes,
        "tailBytes": tail_bytes,
    }
