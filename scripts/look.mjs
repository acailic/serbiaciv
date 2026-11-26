// Look at the site in a headless Chromium: wait for the map, save a screenshot, print the console errors as JSON.
//
//   uv run python -m pipeline serve --port 8765            (in another terminal)
//   NODE_PATH="$HOME/.nvm/versions/node/v22.23.2/lib/node_modules" node scripts/look.mjs http://127.0.0.1:8765/ /tmp/look.png
//
// Playwright is the globally installed package; ES modules do not read NODE_PATH, hence createRequire.
// Optional third argument: a hash to append (#lens=relief, #script=cyr, ...).
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [url, out, hash = ""] = process.argv.slice(2);
if (!url || !out) {
  console.error("usage: node scripts/look.mjs <url> <out.png> [<hash>]");
  process.exit(2);
}

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  await page.goto(url + hash, { waitUntil: "load", timeout: 60000 });
  // The app removes #loading from the page when the first frame is drawn (it does not merely hide it).
  await page.waitForFunction(() => { const el = document.getElementById("loading"); return !el || el.hidden; }, null, { timeout: 60000 });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: out });
  const info = await page.evaluate(() => ({
    title: document.title,
    script: document.documentElement.dataset.script || null,
    canvas: (() => { const c = document.getElementById("map"); return c ? [c.width, c.height] : null; })(),
    topbar: (document.getElementById("yields")?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200),
  }));
  console.log(JSON.stringify({ ...info, errors: errors.slice(0, 10) }));
} finally {
  await browser.close();
}
