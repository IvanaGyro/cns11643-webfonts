"""Command Line Interface for CNS11643 Web Font CDN Builder."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from cns_webfont import __version__
from cns_webfont.builder import (
    build_font_package,
    resolve_package_scope,
)
from cns_webfont.fonts import inspect_font_file
from cns_webfont.upstream import (
    check_upstream,
    download_file,
    is_package_published,
)
from cns_webfont.validator import validate_package

logger = logging.getLogger("cns_webfont")


def setup_logging(verbose: bool) -> None:
    """Configure logging format and verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__, prog_name="cns-webfont")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug logging.")
def main(verbose: bool) -> None:
    """CNS11643 Web Font CDN toolchain."""
    setup_logging(verbose)


@main.command("check-upstream")
@click.option(
    "--scope",
    default=None,
    help="npm scope to check against (defaults to env NPM_SCPOE / NPM_SCOPE or @cns11643).",
)
def check_upstream_cmd(scope: str | None) -> None:
    """Check official upstream for updates and compare with published npm versions."""
    resolved_scope = resolve_package_scope(scope)
    click.echo(f"Checking official CNS11643 upstream (npm scope: {resolved_scope})...")
    try:
        info = check_upstream()
    except Exception as err:
        click.secho(f"Failed to check upstream: {err}", fg="red")
        sys.exit(1)

    click.echo(f"Upstream version: {info.version} ({info.release_date})")

    sung_pkg = f"{resolved_scope}/tw-sung"
    kai_pkg = f"{resolved_scope}/tw-kai"

    sung_pub = is_package_published(sung_pkg, info.version, recipe_revision=0)
    kai_pub = is_package_published(kai_pkg, info.version, recipe_revision=0)

    click.echo(f"  {sung_pkg}: {'PUBLISHED' if sung_pub else 'UPDATE AVAILABLE'}")
    click.echo(f"  {kai_pkg}:  {'PUBLISHED' if kai_pub else 'UPDATE AVAILABLE'}")

    if not sung_pub or not kai_pub:
        click.secho("\nNew upstream release available for build and publish.", fg="green")
    else:
        click.secho("\nPackages are already up-to-date with upstream.", fg="blue")


@main.command("download")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("sources"),
    help="Target directory for downloaded archives.",
)
def download_cmd(output_dir: Path) -> None:
    """Download official Fonts_Sung.zip and Fonts_Kai.zip archives."""
    click.echo("Checking official upstream release info...")
    info = check_upstream()

    output_dir.mkdir(parents=True, exist_ok=True)
    sung_dest = output_dir / "Fonts_Sung.zip"
    kai_dest = output_dir / "Fonts_Kai.zip"

    click.echo(f"Downloading Fonts_Sung.zip to {sung_dest}...")
    sha_sung = download_file(info.sung_url, sung_dest)
    click.echo(f"  Downloaded (SHA-256: {sha_sung})")

    click.echo(f"Downloading Fonts_Kai.zip to {kai_dest}...")
    sha_kai = download_file(info.kai_url, kai_dest)
    click.echo(f"  Downloaded (SHA-256: {sha_kai})")


@main.command("inspect")
@click.argument("font_path", type=click.Path(exists=True, path_type=Path))
@click.option("--role", default="core", help="Font role (core, extb, plus).")
def inspect_cmd(font_path: Path, role: str) -> None:
    """Inspect a font file and display table metadata and cmap count."""
    try:
        source = inspect_font_file(font_path, role=role)
    except Exception as err:
        click.secho(f"Inspection failed: {err}", fg="red")
        sys.exit(1)

    click.echo(f"File: {source.filename}")
    click.echo(f"Role: {source.role}")
    click.echo(f"Glyph count: {source.glyph_count}")
    click.echo(f"Codepoint count: {len(source.codepoints)}")
    click.echo(f"SHA-256: {source.sha256}")


@main.command("validate")
@click.argument("package_dir", type=click.Path(exists=True, path_type=Path))
def validate_cmd(package_dir: Path) -> None:
    """Validate a built webfont package directory."""
    try:
        manifest = validate_package(package_dir)
        click.secho(
            f"Package {manifest['family']} ({package_dir.name}) is valid! "
            f"({manifest['statistics']['woff2Files']} shards, "
            f"{manifest['statistics']['uniqueCodepoints']} codepoints)",
            fg="green",
        )
    except Exception as err:
        click.secho(f"Validation failed: {err}", fg="red")
        sys.exit(1)


@main.command("build-all")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("packages"),
    help="Target directory for output packages.",
)
@click.option(
    "--sources-dir",
    type=click.Path(path_type=Path),
    default=Path("sources"),
    help="Directory containing or receiving Fonts_*.zip.",
)
@click.option("--upstream-version", help="Override upstream version string (e.g. 20260805).")
@click.option("--recipe-revision", default=0, type=int, help="Recipe revision integer.")
@click.option(
    "--scope",
    default=None,
    help="npm scope (defaults to env NPM_SCPOE / NPM_SCOPE or @cns11643).",
)
@click.option("--offline", is_flag=True, help="Operate offline with existing local archives.")
def build_all_cmd(
    output_dir: Path,
    sources_dir: Path,
    upstream_version: str | None,
    recipe_revision: int,
    scope: str | None,
    offline: bool,
) -> None:
    """Full end-to-end build for TW-Sung and TW-Kai webfont packages."""
    resolved_scope = resolve_package_scope(scope)
    google_strategy = Path("data/google-fonts/traditional-chinese_default.txt")
    google_metadata = Path("data/google-fonts/metadata.json")

    if not google_strategy.is_file() or not google_metadata.is_file():
        click.secho("Missing pinned Google slicing strategy in data/google-fonts/", fg="red")
        sys.exit(1)

    sung_zip = sources_dir / "Fonts_Sung.zip"
    kai_zip = sources_dir / "Fonts_Kai.zip"

    if offline:
        if not sung_zip.is_file() or not kai_zip.is_file():
            click.secho(f"Offline mode requires {sung_zip} and {kai_zip} to exist.", fg="red")
            sys.exit(1)
        if not upstream_version:
            click.secho("Offline mode requires --upstream-version to be specified.", fg="red")
            sys.exit(1)
        version = upstream_version
    else:
        info = check_upstream()
        version = upstream_version or info.version
        sources_dir.mkdir(parents=True, exist_ok=True)
        if not sung_zip.is_file():
            click.echo(f"Downloading {info.sung_url}...")
            download_file(info.sung_url, sung_zip)
        if not kai_zip.is_file():
            click.echo(f"Downloading {info.kai_url}...")
            download_file(info.kai_url, kai_zip)

    click.echo(f"Building CNS11643 packages for version {version}.{recipe_revision}.0...")

    sung_out = output_dir / "tw-sung"
    kai_out = output_dir / "tw-kai"

    # Build TW-Sung
    click.echo("\n--- Building TW-Sung ---")
    res_sung = build_font_package(
        family="TW-Sung",
        zip_path=sung_zip,
        google_slices_path=google_strategy,
        google_metadata_path=google_metadata,
        upstream_version=version,
        output_package_dir=sung_out,
        package_scope=resolved_scope,
        recipe_revision=recipe_revision,
    )
    click.secho(
        f"TW-Sung built successfully! "
        f"Shards: {res_sung.manifest['statistics']['woff2Files']}, "
        f"Codepoints: {res_sung.manifest['statistics']['uniqueCodepoints']}",
        fg="green",
    )

    # Build TW-Kai
    click.echo("\n--- Building TW-Kai ---")
    res_kai = build_font_package(
        family="TW-Kai",
        zip_path=kai_zip,
        google_slices_path=google_strategy,
        google_metadata_path=google_metadata,
        upstream_version=version,
        output_package_dir=kai_out,
        package_scope=resolved_scope,
        recipe_revision=recipe_revision,
    )
    click.secho(
        f"TW-Kai built successfully! "
        f"Shards: {res_kai.manifest['statistics']['woff2Files']}, "
        f"Codepoints: {res_kai.manifest['statistics']['uniqueCodepoints']}",
        fg="green",
    )

    click.secho("\nAll packages built and validated successfully!", fg="green", bold=True)


if __name__ == "__main__":
    main()
