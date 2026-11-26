// Smoke test of the app as it is served: load it in a headless Chromium, open the advisors and the City View, and
// fail on anything a reader would see broken.
//
//   node tests/browser/smoke.mjs http://127.0.0.1:8765/serbiaciv/       (a local copy under its Pages subpath)
//   node tests/browser/smoke.mjs https://<owner>.github.io/serbiaciv/   (the published app)
//
// The address is the base of the app and ends with a slash. Playwright comes from the repository's node_modules
// (the deploy workflow installs it there) or, through NODE_PATH, from a global install; ES modules do not read
// NODE_PATH, hence createRequire. Exit code: 0 when every check passed, 1 when one failed, 2 on a usage error.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const base = (process.argv[2] || "").trim();
if (!/^https?:\/\/[^/]+\/([^?#]*\/)?$/.test(base)) {
  console.error("usage: node tests/browser/smoke.mjs <base url of the app, ending with a slash>");
  process.exit(2);
}

// Every file the app loads (scripts/stage_serbia_pages.py stages exactly these), and the ones this visit must fetch.
const DATA = ["world.json", "cities.json", "states.json", "nation.json", "sources.json", "counties.json", "lenses.json",
  "lens-values.json", "kim_towns.json", "infrastructure.json", "resources.json", "wonders.json", "citizens.json",
  "districts.json"];
const FETCHED = ["world.json", "cities.json", "states.json", "nation.json", "sources.json", "lenses.json",
  "counties.json", "infrastructure.json", "wonders.json", "resources.json", "citizens.json", "districts.json"];
// The capital, and a line each advisor shows only once its file is in.
const CITY = "79014";
const ADVISORS = [["economy", "BDP SRBIJE"], ["energy", "SNAGA NA KARTI"], ["commerce", "NAJPROMETNIJI AERODROM"],
  ["culture", "ČUDA"]];
const MISSING_FILE_NOTE = /još nije uključena|nije učitana/;
const BROKEN = [/\bundefined\b/, /\bNaN\b/, /\[object Object\]/];

const problems = [];
let checks = 0;
const check = (ok, message) => { checks += 1; if (!ok) problems.push(message); return Boolean(ok); };

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const requested = new Set();
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("requestfailed", (r) => problems.push(`request failed: ${r.url()} (${r.failure()?.errorText || "no reason given"})`));
  page.on("response", (r) => {
    if (r.status() >= 400) problems.push(`HTTP ${r.status()}: ${r.url()}`);
    const m = /\/data\/([^/?]+)\.json/.exec(r.url());
    if (m) requested.add(`${m[1]}.json`);
  });

  const dockText = () => page.evaluate(() => document.querySelector(".adv-dock")?.innerText || "");
  const textOf = (selector) => page.evaluate((s) => document.querySelector(s)?.innerText || "", selector);
  const brokenIn = (text) => BROKEN.filter((re) => re.test(text)).map(String);
  // Waits until the predicate over the page holds; false when it never does.
  const eventually = (predicate, arg, ms) => page.waitForFunction(predicate, arg, { timeout: ms }).then(() => true, () => false);

  // The app removes #loading when the first frame is drawn (it does not merely hide it).
  await page.goto(`${base}#city=${CITY}&advisor=economy`, { waitUntil: "load", timeout: 60000 });
  check(await eventually(() => { const el = document.getElementById("loading"); return !el || el.hidden; }, null, 60000),
    "the first frame was not drawn within 60 s (#loading never went away)");
  await page.waitForTimeout(1500);

  const map = await page.evaluate(() => { const c = document.getElementById("map"); return c ? [c.width, c.height] : null; });
  check(Array.isArray(map) && map[0] > 0 && map[1] > 0, `the map canvas has no size: ${JSON.stringify(map)}`);
  const title = await page.title();
  check(/Srbija/.test(title), `the title is not Serbian: ${title}`);
  const yields = (await textOf("#yields")).replace(/\s+/g, " ").trim();
  check(/\d/.test(yields), `the top bar shows no figures: "${yields}"`);
  check(brokenIn(yields).length === 0, `broken text in the top bar: ${brokenIn(yields)}`);

  for (const id of ["density", "pop_change", "natural_increase", "age65", "education", "wages", "unemployment",
    "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "elevation", "relief", "land_cover"]) {
    const result = await page.evaluate((id) => {
      try {
        window.__app.setLens(id);
        const lens = window.__app.state.lens;
        return { id: lens?.id, count: lens?.values?.filter((x) => x != null).length || 0 };
      } catch (e) { return { error: e.message }; }
    }, id);
    check(result.id === id && result.count > 0, `lens ${id} did not show values: ${JSON.stringify(result)}`);
  }
  await page.evaluate(() => window.__app.setLens(null));
  await page.locator("#search-input").fill("Priština");
  check(await page.locator("#search-results .sr-item").count() > 0, "Kosovo town search has no Priština result");
  await page.locator("#search-input").press("Enter");
  check(await page.evaluate(() => window.__app.w && window.__app.data.kim_towns?.towns?.length === 29),
    "Kosovo towns are not loaded");

  for (const [id, line] of ADVISORS) {
    await page.evaluate((h) => { location.hash = h; }, `#city=${CITY}&advisor=${id}`);
    const shown = await eventually((needle) => (document.querySelector(".adv-dock")?.innerText || "").includes(needle), line, 20000);
    await page.waitForTimeout(1200);
    const text = await dockText();
    check(shown, `the ${id} advisor never showed "${line}"`);
    check(!MISSING_FILE_NOTE.test(text), `the ${id} advisor says a data file is missing: ${text.replace(/\s+/g, " ").slice(0, 200)}`);
    check(brokenIn(text).length === 0, `broken text in the ${id} advisor: ${brokenIn(text)}`);
  }

  // Close the advisors (Escape is theirs), then open the City View of the capital the way a reader does.
  await page.keyboard.press("Escape");
  await page.evaluate((h) => { location.hash = h; }, `#city=${CITY}`);
  const open = page.locator("button", { hasText: "Otvori Pregled grada" }).first();
  await open.click({ timeout: 20000 });
  const residents = await page.evaluate(async () => {
    const { buildModel } = await import("./js/ext/cityView/model.js");
    const app = window.__app;
    return buildModel(app, app.data.cities.find((city) => city.id === "79014")).tiles.filter((tile) => tile.residents != null).length;
  });
  check(residents > 0, "City View has no per-hex population estimates");
  const districts = await eventually(() => /Kampus/.test(document.querySelector("[data-districts]")?.innerText || ""), null, 20000);
  check(districts, "the City View shows no districts of the capital");
  // The two panels fill separately, each when its own file has arrived; a short placeholder stands in until then.
  const citizensLoaded = await eventually(() => {
    const c = document.querySelector("[data-citizens]");
    return Boolean(c) && c.innerText.length > 200 && !/Učitavamo/.test(c.innerText);
  }, null, 20000);
  const citizens = await textOf("[data-citizens]");
  check(citizensLoaded && citizens.length > 100,
    `the City View shows no citizens of the capital (${citizens.replace(/\s+/g, " ").slice(0, 80)})`);
  const badge = (await textOf("[data-ctype]")).trim();
  check(badge.length > 0, "the City View shows no city type");
  const cityView = await page.evaluate(() => {
    const host = document.querySelector("[data-districts]")?.closest(".panel, .app-dock, section, div");
    return host ? host.innerText : "";
  });
  check(brokenIn(cityView).length === 0, `broken text in the City View: ${brokenIn(cityView)}`);
  await page.waitForTimeout(1500);

  for (const name of FETCHED) check(requested.has(name), `${name} was not requested by the app`);
  // A file the app loads only on some other visit must still be served: ask for every one of them from the page.
  const served = await page.evaluate(async (names) => {
    const out = {};
    for (const name of names) {
      try {
        const r = await fetch(`data/${name}`);
        out[name] = r.ok ? (await r.json(), "ok") : `HTTP ${r.status}`;
      } catch (e) { out[name] = `not JSON (${e.message})`; }
    }
    return out;
  }, DATA);
  const unserved = Object.entries(served).filter(([, state]) => state !== "ok");
  check(unserved.length === 0, `data files not served: ${JSON.stringify(Object.fromEntries(unserved))}`);
  const sourceArchive = await page.request.get(`${base}serbiaciv-source.zip`);
  check(sourceArchive.ok(), `the Help source archive is not served: HTTP ${sourceArchive.status()}`);

  await page.goto(`${base}#lens=density&script=lat`, { waitUntil: "load", timeout: 60000 });
  check(await eventually(() => !document.getElementById("loading") && window.__app?.state.lens?.id === "density", null, 20000),
    "a shared density lens link did not load the map");

  const ok = problems.length === 0;
  console.log(JSON.stringify({ ok, base, checks, problems, requested: [...requested].sort() }, null, 2));
  process.exitCode = ok ? 0 : 1;
} catch (e) {
  problems.push(`the smoke test itself stopped: ${e.message}`);
  console.log(JSON.stringify({ ok: false, base, checks, problems }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
