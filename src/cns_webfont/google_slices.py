"""Parser and validator for Google Fonts slicing strategy."""

from __future__ import annotations

import re
from pathlib import Path

from cns_webfont.models import LogicalSlice


class GoogleSlicesParsingError(Exception):
    """Raised when the Google Fonts slicing strategy file is invalid or corrupted."""


def parse_google_slices(file_path: Path) -> list[LogicalSlice]:
    """Parse and validate Google Fonts slicing strategy file.

    The subsets are listed in reverse order in the upstream file to match
    CSS unicode-range prioritization. This ordering is preserved exactly.

    Args:
        file_path: Path to the traditional-chinese_default.txt file.

    Returns:
        List of LogicalSlice objects in exact file order.

    Raises:
        GoogleSlicesParsingError: If formatting, uniqueness, or scalar validation fails.
    """
    if not file_path.is_file():
        raise GoogleSlicesParsingError(f"Slicing strategy file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    slices: list[LogicalSlice] = []
    seen_global_codepoints: set[int] = set()

    in_subset = False
    current_codepoints: list[int] = []
    current_seen_in_subset: set[int] = set()
    current_subset_index = 0

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Strip inline comments before checking syntax tokens
        clean_line = line.split("#", 1)[0].strip() if "#" in line else line

        if not in_subset:
            if "subsets" in clean_line and "{" in clean_line:
                in_subset = True
                current_subset_index += 1
                current_codepoints = []
                current_seen_in_subset = set()
            continue

        # Inside subset block
        if "}" in clean_line:
            if not current_codepoints:
                raise GoogleSlicesParsingError(
                    f"Line {line_no}: Subset {current_subset_index} contains zero codepoints"
                )
            slices.append(
                LogicalSlice(
                    index=current_subset_index,
                    slice_type="google",
                    codepoints=current_codepoints,
                )
            )
            in_subset = False
            current_codepoints = []
            current_seen_in_subset = set()
            continue

        # Codepoint entry
        cp_match = re.match(r"^codepoints:\s*(\d+)$", clean_line)
        if not cp_match:
            continue

        try:
            cp = int(cp_match.group(1))
        except ValueError as err:
            raise GoogleSlicesParsingError(
                f"Line {line_no}: invalid integer codepoint in subset {current_subset_index}"
            ) from err

        # Validate Unicode scalar value
        if cp < 0 or cp > 0x10FFFF or (0xD800 <= cp <= 0xDFFF):
            raise GoogleSlicesParsingError(
                f"Line {line_no}: codepoint {cp} (0x{cp:X}) is not a valid Unicode scalar value"
            )

        # Validate intra-subset uniqueness
        if cp in current_seen_in_subset:
            raise GoogleSlicesParsingError(
                f"Line {line_no}: duplicate codepoint {cp} (0x{cp:X}) "
                f"in subset {current_subset_index}"
            )
        current_seen_in_subset.add(cp)

        # Validate global uniqueness across subsets
        if cp in seen_global_codepoints:
            raise GoogleSlicesParsingError(
                f"Line {line_no}: codepoint {cp} (0x{cp:X}) appeared in a previous subset"
            )
        seen_global_codepoints.add(cp)

        current_codepoints.append(cp)

    if in_subset:
        raise GoogleSlicesParsingError(
            f"Unterminated subset block {current_subset_index} at end of file"
        )

    if not slices:
        raise GoogleSlicesParsingError(f"No subsets found in {file_path}")

    return slices
