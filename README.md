# CNS11643 Web Font CDN

> **Unofficial webfont distribution generated from the official CNS11643 open font data.**  
> This project is not officially maintained by the Ministry of Digital Affairs.

Production-grade, automatically updated Web Font CDN and npm distribution packages for **TW-Sung (全字庫正宋體)** and **TW-Kai (全字庫正楷體)** supporting the full **CNS11643** character repertoire.

Browsers download only the small WOFF2 shards actually used on a webpage, combining the full breadth of Taiwan's government standard character set with the low-latency network performance of Google Fonts Traditional Chinese slicing.

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. Upstream Source & Versioning](#2-upstream-source--versioning)
- [3. Slicing Architecture](#3-slicing-architecture)
  - [Google Fonts Traditional Chinese Common Slices](#google-fonts-traditional-chinese-common-slices)
  - [CNS Rare Character Tail Slices](#cns-rare-character-tail-slices)
  - [Physical Shard Ownership](#physical-shard-ownership)
- [4. Quick Start](#4-quick-start)
  - [via jsDelivr CDN (Production Recommended)](#via-jsdelivr-cdn-production-recommended)
  - [via npm Packages](#via-npm-packages)
  - [CSS Usage](#css-usage)
- [5. Best Practices: Web Printing & Document Generation](#5-best-practices-web-printing--document-generation)
- [6. Browser Support](#6-browser-support)
- [7. Verification & Manifest](#7-verification--manifest)
- [8. Automation & Supply-Chain Security](#8-automation--supply-chain-security)
  - [Automated Upstream Monitoring](#automated-upstream-monitoring)
  - [npm Trusted Publishing (OIDC)](#npm-trusted-publishing-oidc)
  - [Google Slicing Update Policy](#google-slicing-update-policy)
- [9. Local Development & Toolchain](#9-local-development--toolchain)
- [10. Licensing & Attribution](#10-licensing--attribution)

---

## 1. Overview

Official CNS11643 fonts contain more than 110,000 characters across multiple Unicode planes. OpenType fonts are constrained by a 16-bit glyph index limit (65,535 glyphs), which is why official sources supply separate TrueType fonts:
- **Core (BMP)**: Unicode Basic Multilingual Plane (Plane 0)
- **Ext-B**: CJK Unified Ideographs Extension B (Plane 2)
- **Plus**: Supplementary Rare & Administrative Name Characters (Plane 15 / PUA)

This project **does not merge them into an invalid monolithic TTF**. Instead, it generates optimized WOFF2 shards and unifies them cleanly at the CSS `@font-face` level under a single font family:
```css
font-family: "TW-Sung", serif;
/* or */
font-family: "TW-Kai", serif;
```

---

## 2. Upstream Source & Versioning

- **Authoritative Source**: 數位發展部 (Ministry of Digital Affairs, Taiwan)
- **Open Data Resource**: [CNS11643 Open Data (Dataset 5961)](https://data.gov.tw/dataset/5961) / [Official Portal](https://www.cns11643.gov.tw)
- **Release Files**: `OpenDataFilesList.csv`, `release.txt`, `Fonts_Sung.zip`, `Fonts_Kai.zip`

### Version Scheme
Versions follow `<YYYYMMDD>.<recipe_revision>.0`:
- `20260805.0.0`: Upstream release dated August 5, 2026, recipe revision 0.
- `20260805.1.0`: Same upstream data, but with builder improvements or slicing refinements.

---

## 3. Slicing Architecture

### Google Fonts Traditional Chinese Common Slices
Rather than using arbitrary 256-codepoint blocks, common characters utilize Google Fonts' production-tested Traditional Chinese slicing strategy (`slices/traditional-chinese_default.txt` from `googlefonts/nam-files`):
- **120 logical subsets** covering 17,704 high-frequency and general CJK characters.
- High-frequency characters (subsets 1–20) are prioritized based on real-world Taiwanese web corpus frequency.
- The upstream subset ordering is strictly preserved to honor CSS `unicode-range` matching priority.

### CNS Rare Character Tail Slices
Characters present in the official CNS repertoire but outside Google Fonts TC coverage are partitioned into sequential tail bins:
- Characters sorted deterministically by codepoint: `sorted(CNS - GoogleFonts)`.
- Fixed logical bin size: **135 actual existing codepoints** per bin (`TAIL_BIN_SIZE = 135`).
- The final bin contains $\le 135$ codepoints.

### Physical Shard Ownership
Each logical slice is partitioned by physical source font (`core`, `extb`, `plus`):
- **Priority**: `core > extb > plus` (deterministic first-owner wins).
- Duplicate cmap mappings across sources are logged to `duplicates.json` and guarded by regression thresholds.
- Each physical shard is saved as a discrete WOFF2 file (e.g., `gf-001-core.woff2`, `tail-0042-extb.woff2`).
- Shard `unicode-range` definitions are completely disjoint, satisfying:
  $$\bigcup \text{CSS unicode-ranges} \equiv \bigcup \text{Owned Source Codepoints}$$

---

## 4. Quick Start

### via jsDelivr CDN (Production Recommended)

> [!IMPORTANT]
> **Production & School Printing Websites**: Always pin an **exact package version** in production. Do not use unpinned `@latest` for official documents or printable forms, ensuring that future upstream glyph or metric adjustments will not alter page layouts or line breaks.

#### TW-Sung (全字庫正宋體)
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@cns11643/tw-sung@20260805.0.0/tw-sung.css">
```

#### TW-Kai (全字庫正楷體)
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@cns11643/tw-kai@20260805.0.0/tw-kai.css">
```

### via npm Packages

```bash
npm install @cns11643/tw-sung
npm install @cns11643/tw-kai
```

### CSS Usage

```css
/* Import in CSS */
@import "@cns11643/tw-sung/tw-sung.css";
@import "@cns11643/tw-kai/tw-kai.css";

/* Apply font family */
.document-heading {
  font-family: "TW-Sung", serif;
}

.official-signature {
  font-family: "TW-Kai", serif;
}
```

---

## 5. Best Practices: Web Printing & Document Generation

When generating printable forms, diplomas, or certificates using Web Fonts:
**Never trigger `window.print()` before web font shards finish downloading.**

Use the standard `document.fonts.ready` promise:
```javascript
// Wait for required font shards to finish downloading and rendering
await document.fonts.ready;

// Safely trigger print or PDF generation
window.print();
```

---

## 6. Browser Support

The web font package generates standard WOFF2 files compatible with all modern browsers:
- **Google Chrome** $\ge 36$
- **Mozilla Firefox** $\ge 39$
- **Apple Safari / WebKit** $\ge 10$
- **Microsoft Edge** $\ge 14$

Cross-browser functionality and selective network shard loading are verified automatically in CI via Playwright across Chromium, Firefox, and WebKit.

---

## 7. Verification & Manifest

Every distributed package includes `manifest.json` containing cryptographic hashes and exact codepoint mappings:
```json
{
  "family": "TW-Sung",
  "upstreamVersion": "20260805",
  "packageVersion": "20260805.0.0",
  "builderVersion": "0.1.0",
  "slicingStrategy": {
    "type": "google-tc-plus-cns-tail",
    "googleRepository": "googlefonts/nam-files",
    "googleCommit": "1d38a7d77ce11452ccbfe8fa9a0cb728ee6d7cd3",
    "tailBinSize": 135
  },
  "statistics": {
    "uniqueCodepoints": 113000,
    "googleCoveredCodepoints": 17704,
    "tailCodepoints": 95296,
    "woff2Files": 842,
    "totalWoff2Bytes": 45000000
  }
}
```

Validate package integrity locally using the CLI:
```bash
cns-webfont validate packages/tw-sung
```

---

## 8. Automation & Supply-Chain Security

### Automated Upstream Monitoring
The GitHub Actions workflow (`.github/workflows/release.yml`) runs on a weekly schedule.
1. Inspects `OpenDataFilesList.csv` and `release.txt` from the official repository.
2. Compares upstream release timestamps against currently published npm registry metadata.
3. Exits with code 0 (no-op) if already up-to-date.
4. If an upstream update is detected:
   - Downloads official ZIP archives and validates SHA-256 hashes.
   - Builds both `TW-Sung` and `TW-Kai`.
   - Executes validation and regression gates (refuses to publish if character coverage drops $>2\%$).
   - Executes cross-browser Playwright test suite.
   - Enforces package size guard (`npm pack --dry-run` unpacked size $< 90\text{ MiB}$).

### npm Trusted Publishing (OIDC)
The release workflow utilizes **npm Trusted Publishing via GitHub OIDC**:
- No long-lived npm secret tokens are stored in the repository.
- Short-lived identity tokens are minted using `id-token: write` permissions during release jobs.
- Provenance attestations are generated and signed for all published packages.

### Google Slicing Update Policy
Changes to Google Fonts Traditional Chinese slicing files are monitored weekly by `.github/workflows/check-google-slices.yml`.
When upstream changes occur:
- A Pull Request is opened detailing the codepoint and subset differences.
- **No automated merge or publish occurs**: slice strategy updates are reviewed manually to prevent unnecessary CDN cache invalidation.

---

## 9. Local Development & Toolchain

### Prerequisites
- [Pixi](https://pixi.sh) package manager
- Node.js (for browser tests)

Target platform support matrix:
`(Windows, macOS, Linux) x (x64, arm64)` *(macOS ARM-only)*.

### Setup Environment
```bash
pixi run test
```

### Pre-commit Hooks
Pre-commit hooks are configured with `ruff` and `pyproject-fmt`:
```bash
# Run linter and formatter
pixi run lint

# Automatically format code and pyproject.toml
pixi run format
```

### CLI Commands
```bash
# Check upstream status vs npm
pixi run cns-webfont check-upstream

# Inspect font file
pixi run cns-webfont inspect sources/TW-Sung-98_1.ttf --role core

# Run full build offline
pixi run cns-webfont build-all --sources-dir sources --output-dir packages --offline --upstream-version 20260805
```

---

## 10. Licensing & Attribution

This project maintains strict license separation:

| Component | License | Details |
| :--- | :--- | :--- |
| **Builder Toolchain Source Code** | **MIT License** | See [LICENSE](LICENSE) |
| **Generated Font Software** | **SIL Open Font License 1.1** | See [LICENSE-OFL.txt](packages/tw-sung/LICENSE-OFL.txt) |

### Attribution Notice
The font glyphs and data are provided by the **Ministry of Digital Affairs, Taiwan (數位發展部)** under the Open Data Program.
Official notice and attribution details are documented in [NOTICE.md](packages/tw-sung/NOTICE.md).
No Reserved Font Name (RFN) is declared by the upstream copyright holder; the family names `TW-Sung` and `TW-Kai` may be used directly.
