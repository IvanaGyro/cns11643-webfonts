"""Data models for CNS11643 webfont builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceFont:
    """Represents a physical TrueType font source file."""

    role: str  # "core", "extb", or "plus"
    filename: str
    path: Path
    sha256: str
    glyph_count: int
    codepoints: set[int] = field(default_factory=set)


@dataclass
class LogicalSlice:
    """A logical character subset slice."""

    index: int
    slice_type: str  # "google" or "tail"
    codepoints: list[int]


@dataclass
class PhysicalShard:
    """A physical WOFF2 shard generated from a logical slice and source font."""

    filename: str
    logical_index: int
    slice_type: str
    source_role: str
    codepoints: list[int]
    unicode_ranges: str
    byte_size: int = 0
    sha256: str = ""


@dataclass
class UpstreamInfo:
    """Upstream version and download metadata."""

    version: str
    release_date: str
    sung_url: str
    kai_url: str
    csv_url: str
    release_url: str
