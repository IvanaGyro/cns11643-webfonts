import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

test.describe("CNS11643 Web Font Loading and Slicing", () => {
  const fixturePath = path.resolve(__dirname, "../fixtures/test-page.html");
  const manifestPath = path.resolve(__dirname, "../../packages/tw-sung/manifest.json");

  test("document.fonts.check and selective shard network loading", async ({ page }) => {
    const requestedShards: string[] = [];

    // Intercept network requests for WOFF2 files
    await page.route("**/*.woff2", (route) => {
      const url = route.request().url();
      const filename = path.basename(new URL(url).pathname);
      requestedShards.push(filename);
      route.continue();
    });

    await page.goto(`file://${fixturePath}`);
    await page.waitForLoadState("networkidle");

    // 1. Assert document.fonts.check returns true for loaded common text
    const isFontLoaded = await page.evaluate(() => {
      return document.fonts.check('24px "TW-Sung"');
    });
    expect(isFontLoaded).toBe(true);

    // 2. Network Assertion: Common TC text MUST NOT download tail shards
    const tailRequests = requestedShards.filter((fn) => fn.startsWith("tail-"));
    expect(tailRequests.length).toBe(0);

    // 3. Dynamic Rare Character Test
    // If manifest exists, pick the first codepoint from the first tail shard
    let rareChar = "\u{20000}"; // Default Ext-B test character
    if (fs.existsSync(manifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
      const firstTailShard = manifest.shards.find(
        (s: { sliceType: string; codepointCount: number }) => s.sliceType === "tail" && s.codepointCount > 0
      );
      if (firstTailShard) {
        // Parse the first codepoint from unicodeRanges (e.g. "U+XXXX...")
        const match = firstTailShard.unicodeRanges.match(/U\+([0-9A-Fa-f]+)/);
        if (match) {
          const cp = parseInt(match[1], 16);
          rareChar = String.fromCodePoint(cp);
        }
      }
    }

    const requestsBefore = requestedShards.length;

    // Inject rare character into page
    await page.evaluate((char) => {
      const el = document.getElementById("rare-container");
      if (el) el.textContent = char;
    }, rareChar);

    // Wait for potential font shard load
    await page.evaluate(async () => {
      await document.fonts.ready;
    });

    // 4. Print readiness test: verify document.fonts.ready succeeds prior to printing
    const readyStatus = await page.evaluate(async () => {
      await document.fonts.ready;
      return document.fonts.status;
    });
    expect(readyStatus).toBe("loaded");
  });
});
