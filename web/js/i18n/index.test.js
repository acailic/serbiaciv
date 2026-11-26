// web/js/i18n/index.js (the page's script), web/js/app/urlstate.js (script= in the hash) and web/js/format.js
// (Serbian number formats). Run: node --test "web/js/i18n/**/*.test.js"
import { test } from "node:test";
import assert from "node:assert/strict";
import { compact, int, eur, rsd, money, dollars, pct, yieldValue, popShort, esc } from "../format.js";
import { parseHash, formatHash, withScript } from "../app/urlstate.js";
import { initialScript, getScript, script, setScript, installScriptToggle, watchDom, STORAGE_KEY } from "./index.js";

// --- a miniature page: the few things index.js touches -------------------------------------------------------------
// boot.js puts the script on <html data-script>. Elements and text nodes can mutate, and MutationObserver hands
// each mutation to its callback at once (the browser does so a microtask later).
class Elem {
  constructor(name, attrs = {}) {
    this.nodeType = 1;
    this.localName = name;
    this.attrs = { ...attrs };
    this.childNodes = [];
    this.parentElement = null;
  }
  append(...kids) {
    kids.forEach((k) => {
      k.parentElement = this;
      this.childNodes.push(k);
    });
    this.mutate({ type: "childList", target: this, addedNodes: kids });
    return this;
  }
  get documentElement() { return this.childNodes.find((c) => c.localName === "html") || null; }
  getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }
  hasAttribute(n) { return n in this.attrs; }
  setAttribute(n, v) {
    if (this.getAttribute(n) === String(v)) return;
    this.attrs[n] = String(v);
    this.mutate({ type: "attributes", target: this, attributeName: n });
  }
  get textContent() { return this.childNodes.map((c) => (c.nodeType === 3 ? c.data : c.textContent)).join(""); }
  set textContent(v) {
    this.childNodes = [];
    if (v !== "") this.append(new Text(v));
    else this.mutate({ type: "childList", target: this, addedNodes: [] });
  }
  matches(selector) {
    return selector.split(",").some((s) => (s.trim() === "[data-no-translit]" ? "data-no-translit" in this.attrs : s.trim() === this.localName));
  }
  closest(selector) {
    for (let e = this; e; e = e.parentElement) if (e.matches(selector)) return e;
    return null;
  }
  get dataset() {
    const el = this;
    return { get script() { return el.attrs["data-script"]; }, set script(v) { el.attrs["data-script"] = v; } };
  }
  mutate(record) { MutationObserver.last?.callback([record]); }
}
class Text {
  constructor(data) {
    this.nodeType = 3;
    this.parentElement = null;
    this._data = data;
  }
  get data() { return this._data; }
  set data(v) {
    this._data = v;
    this.parentElement?.mutate({ type: "characterData", target: this });
  }
}
class MutationObserver {
  constructor(callback) { this.callback = callback; }
  observe(target, options) { this.target = target; this.options = options; MutationObserver.last = this; }
}
const byId = {};
const html = new Elem("html");
html.append(
  new Elem("body").append(
    byId.brand = new Elem("div", { title: "Srbija" }).append(new Text("Srbija")),
    byId.panel = new Elem("aside", { "aria-label": "Detalji" }),
    byId.input = new Elem("input", { placeholder: "Pretraga gradova i okruga" }),
    byId.keep = new Elem("p").append(new Text("Izvor: "), byId.name = new Elem("span", { "data-no-translit": "" }).append(new Text("Eurostat"))),
    byId.code = new Elem("pre").append(new Text("Ljubljana")),
    byId.img = new Elem("img", { alt: "Zastava", src: "x.svg" }),
  ),
);
byId.input.value = "Niš"; // what a visitor typed: the property, not an attribute
const document = new Elem("#document").append(html);
const stored = new Map();
const calls = [];
Object.assign(globalThis, {
  document,
  MutationObserver,
  localStorage: { getItem: (k) => stored.get(k) ?? null, setItem: (k, v) => stored.set(k, String(v)) },
  history: { replaceState: (s, t, url) => calls.push(`replaceState ${url}`) },
  location: { hash: "#lens=income&at=395,247,0", pathname: "/", search: "", reload: () => calls.push("reload") },
});
const button = () => ({
  attrs: {}, handlers: {}, textContent: "",
  setAttribute(n, v) { this.attrs[n] = v; },
  addEventListener(type, fn) { this.handlers[type] = fn; },
});
const show = (s) => { html.dataset.script = s; calls.length = 0; location.hash = "#lens=income&at=395,247,0"; };

// --- which script a page load starts in ---------------------------------------------------------------------------

test("initialScript: the hash wins, then the stored choice, then the browser language", () => {
  const cases = [
    [{ hash: "#script=cyr", stored: "lat", language: "en-US" }, "cyr"],
    [{ hash: "#lens=income&script=cyr", stored: null, language: "en-US" }, "cyr"],
    [{ hash: "#script=lat", stored: "cyr", language: "sr-RS" }, "lat"],
    [{ hash: "", stored: "cyr", language: "en-US" }, "cyr"],
    [{ hash: "#lens=relief", stored: "lat", language: "sr" }, "lat"],
    // a value that is not a script is no choice at all
    [{ hash: "#script=bogus", stored: "cyr", language: "en-US" }, "cyr"],
    [{ hash: "#script=bogus", stored: null, language: "sr" }, "cyr"],
    [{ hash: "", stored: "bogus", language: "en-US" }, "lat"],
  ];
  for (const [input, want] of cases) assert.equal(initialScript(input), want, JSON.stringify(input));
});

test("initialScript: a first visit is Cyrillic for Serbian browsers that do not ask for Latin", () => {
  for (const language of ["sr", "sr-RS", "SR", "sr-rs", "sr-Cyrl-RS"]) assert.equal(initialScript({ hash: "", stored: null, language }), "cyr", language);
  for (const language of ["sr-Latn", "sr-Latn-RS", "sr-latn", "en-US", "de", "hr-HR", "ru", "", undefined]) {
    assert.equal(initialScript({ hash: "", stored: null, language }), "lat", language);
  }
  assert.equal(initialScript(), "lat");
});

// --- the script of the page on screen ------------------------------------------------------------------------------

test("getScript and script follow <html data-script>", () => {
  show("lat");
  assert.equal(getScript(), "lat");
  assert.equal(script("Beograd"), "Beograd");
  show("cyr");
  assert.equal(getScript(), "cyr");
  assert.equal(script("Beograd"), "Београд");
  assert.equal(script("Nišavski okrug"), "Нишавски округ");
  assert.equal(script("Izvor: Eurostat"), "Извор: Eurostat");
  assert.equal(script(""), "");
  assert.equal(script(null), null);
  delete html.attrs["data-script"];
  assert.equal(getScript(), "lat"); // boot.js did not run: Latin
});

test("setScript stores the choice, puts it in the hash, then reloads", () => {
  show("lat");
  setScript("cyr");
  assert.equal(stored.get(STORAGE_KEY), "cyr");
  assert.deepEqual(calls, ["replaceState /#lens=income&at=395,247,0&script=cyr", "reload"]);

  show("cyr");
  location.hash = "#lens=income&at=395,247,0&script=cyr";
  setScript("lat");
  assert.equal(stored.get(STORAGE_KEY), "lat");
  assert.deepEqual(calls, ["replaceState /#lens=income&at=395,247,0&script=lat", "reload"]);
});

test("the hash carries both script choices", () => {
  assert.equal(formatHash({ lens: "income", script: "cyr" }), "#lens=income&script=cyr");
  assert.equal(formatHash({ lens: "income", script: "lat" }), "#lens=income&script=lat");
  assert.equal(initialScript({ hash: formatHash({ lens: "income", script: "lat" }), stored: "cyr" }), "lat");
  assert.equal(formatHash({ script: "cyr" }), "#script=cyr");
  assert.equal(formatHash({ at: [395.2, 247, 0.5], script: "cyr" }), "#at=395,247,0.5&script=cyr");
  assert.equal(parseHash("#lens=income&script=cyr").script, "cyr");
  assert.equal(parseHash("#script=lat").script, "lat");
  assert.equal(parseHash("#lens=income").script, null);
  // switching edits only that parameter: whatever else the link carries is written back exactly as it was
  assert.equal(withScript("#lens=relief&layers=roads,rail&script=lat", "cyr"), "#lens=relief&layers=roads,rail&script=cyr");
  assert.equal(withScript("#script=cyr&at=1,2,3", "lat"), "#at=1,2,3&script=lat");
  assert.equal(withScript("#script=cyr", "lat"), "#script=lat");
  assert.equal(withScript("", "cyr"), "#script=cyr");
});

test("the toggle shows the script it switches to, and stays as written", () => {
  show("lat");
  const b = button();
  installScriptToggle(b);
  assert.equal(b.textContent, "Ћир");
  assert.equal(b.attrs["data-no-translit"], "");
  b.handlers.click();
  assert.deepEqual(calls, ["replaceState /#lens=income&at=395,247,0&script=cyr", "reload"]);

  show("cyr");
  location.hash = "#lens=income&script=cyr";
  const c = button();
  installScriptToggle(c);
  assert.equal(c.textContent, "Lat");
  assert.equal(c.attrs["data-no-translit"], "");
  c.handlers.click();
  assert.deepEqual(calls, ["replaceState /#lens=income&script=lat", "reload"]);
});

// --- the page as it changes ------------------------------------------------------------------------------------------

test("watchDom does nothing in Latin mode", () => {
  show("lat");
  watchDom();
  assert.equal(byId.brand.textContent, "Srbija");
  assert.equal(MutationObserver.last, undefined);
});

test("watchDom transliterates the page, then everything the app adds or changes", () => {
  show("cyr");
  watchDom();
  const observer = MutationObserver.last;
  assert.equal(observer.target, document);
  // the page as it was when the script started
  assert.equal(byId.brand.textContent, "Србија");
  assert.equal(byId.brand.getAttribute("title"), "Србија");
  assert.equal(byId.panel.getAttribute("aria-label"), "Детаљи");
  assert.equal(byId.input.getAttribute("placeholder"), "Претрага градова и округа");
  assert.equal(byId.img.getAttribute("alt"), "Застава");
  // text the app writes later: a new node, a changed node, a changed attribute, a replaced element content
  const line = new Text("Nišavski okrug");
  byId.panel.append(line);
  assert.equal(line.data, "Нишавски округ");
  line.data = "Kosovsko-mitrovački okrug";
  assert.equal(line.data, "Косовско-митровачки округ");
  byId.panel.setAttribute("title", "Otvori izveštaj");
  assert.equal(byId.panel.getAttribute("title"), "Отвори извештај");
  byId.panel.textContent = "Novi Sad";
  assert.equal(byId.panel.textContent, "Нови Сад");
  assert.deepEqual(observer.options, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["title", "aria-label", "alt", "placeholder"] });
});

test("watchDom leaves alone what must stay as written", () => {
  show("cyr");
  watchDom();
  // never the value of an input
  assert.equal(byId.input.value, "Niš");
  // a protected name, and code
  assert.equal(byId.keep.textContent, "Извор: Eurostat");
  assert.equal(byId.name.textContent, "Eurostat");
  assert.equal(byId.code.textContent, "Ljubljana");
  // attributes it does not look at
  assert.equal(byId.img.getAttribute("src"), "x.svg");
  for (const name of ["script", "style", "kbd", "textarea"]) {
    const el = new Elem(name).append(new Text("Beograd"));
    byId.panel.append(el);
    assert.equal(el.textContent, "Beograd", name);
  }
});

// --- numbers as Serbia writes them (docs/GLOSSARY.md, "Numbers") --------------------------------------------------

test("compact: hilj., mil., mlrd and bil. around a decimal comma", () => {
  const cases = [
    [6549901, "6,5 mil."], [250000, "250 hilj."], [8.2e10, "82 mlrd"], [123456, "123,5 hilj."], [1.5e12, "1,5 bil."],
    [9999999, "10 mil."], [1e8, "100 mil."], [1.234e11, "123 mlrd"], [-250000, "-250 hilj."], [999, "999"], [0, "0"],
  ];
  for (const [n, want] of cases) assert.equal(compact(n), want, String(n));
  assert.equal(compact(null), "–");
  assert.equal(compact(undefined), "–");
  assert.equal(compact(NaN), "–");
});

test("int: digits in threes, separated by dots", () => {
  assert.equal(int(1234567), "1.234.567");
  assert.equal(int(1000), "1.000");
  assert.equal(int(999), "999");
  assert.equal(int(109462.4), "109.462");
  assert.equal(int(-5000), "-5.000");
  assert.equal(int(null), "–");
});

test("eur and rsd: the currency follows the number after a space", () => {
  assert.equal(eur(8.2e10), "82 mlrd €");
  assert.equal(eur(4.2e9), "4,2 mlrd €");
  assert.equal(eur(null), "–");
  assert.equal(rsd(109462), "109.462 RSD");
  assert.equal(rsd(85000.6), "85.001 RSD");
  assert.equal(rsd(null), "–");
});

test("money and dollars are kept for upstream's callers: euros and dinars under their old names", () => {
  assert.equal(money, eur);
  assert.equal(dollars, rsd);
  assert.equal(money(8.2e10), "82 mlrd €");
  assert.equal(dollars(109462), "109.462 RSD");
  assert.equal(money(null), "–");
  assert.equal(dollars(null), "–");
});

test("pct: a decimal comma and a space before the percent sign", () => {
  assert.equal(pct(0.123), "12,3 %");
  assert.equal(pct(0.1), "10,0 %");
  assert.equal(pct(0.123, 0), "12 %");
  assert.equal(pct(0.05678, 2), "5,68 %");
  assert.equal(pct(-0.012), "-1,2 %");
  assert.equal(pct(null), "–");
});

test("yieldValue: euros for the yield counted in euros, otherwise the plain compact form", () => {
  assert.equal(yieldValue({ unit: "eur" }, 8.2e10), "82 mlrd €");
  assert.equal(yieldValue({ unit: "workers" }, 250000), "250 hilj.");
});

test("popShort: the population on a city banner", () => {
  assert.equal(popShort(1700000), "1,7 mil.");
  assert.equal(popShort(250000), "250 hilj.");
  assert.equal(popShort(14000000), "14 mil.");
  assert.equal(popShort(999), "1 hilj.");
});

test("esc is unchanged", () => {
  assert.equal(esc(`<a href="x" title="Niš">&'`), "&lt;a href=&quot;x&quot; title=&quot;Niš&quot;&gt;&amp;&#39;");
});
