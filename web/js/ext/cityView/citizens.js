// City View "Citizens" rows: the city's people as rows of small figures (citizens.json, Popis 2022).
//
//   citizensHtml(m, data) → HTML      the rows (placeholders for the figure canvases)
//   mountCitizens(host, m, data)       paints the figures and wires the hover / focus read-out
//
// Each row: N figures (workforce 20, ages 10, where people work 10 from the file; schooling and birthplace 10,
// rounded here with the same largest-remainder method), a caption ("each figure ≈ 1.200 zaposlenih"), a read-out
// line that a hovered or focused figure fills ("1 od 7 zaposlenih u Beogradu su rukovodioci (Srbija: 1 od 18)")
// and a thin bar with the Republic's mix for comparison. The categories, their order and their labels come from
// the file's groups; SHORT and PHRASE only shorten and conjugate them. A row the census does not publish is said
// so, never drawn as zeros.
import { esc, int, pct } from "../../format.js";
import { compact } from "./fmt.js";
import { CATEGORY_COLOR, figureCanvas, loadPainter } from "./figures.js";

const ROWS = [
  { id: "workforce", title: "Radna snaga", sub: "po glavnim grupama zanimanja", noun: ["zaposleni", "zaposlenih"], n: null },
  { id: "age", title: "Generacije", sub: "po starosti", noun: ["stanovnik", "stanovnika"], n: null },
  { id: "commute", title: "Gde zaposleni rade", sub: "dnevne migracije: mesto rada", noun: ["zaposleni", "zaposlenih"], n: null },
  { id: "education", title: "Školska sprema", sub: "stanovništvo sa 15 i više godina", noun: ["stanovnik", "stanovnika (15+)"], n: 10 },
  { id: "nativity", title: "Poreklo doseljenja", sub: "odakle su se doselili", noun: ["stanovnik", "stanovnika"], n: 10 },
];
const NATION = "Srbija";

// [singular, plural] verb phrase per category, for "1 od 7 zaposlenih u X je rukovodilac" / "3 od 10 … su rukovodioci".
const PHRASE = {
  workforce: {
    executive: ["je rukovodilac, funkcioner ili zakonodavac", "su rukovodioci, funkcioneri i zakonodavci"],
    engineer: ["je stručnjak, inženjer ili tehničar", "su stručnjaci, inženjeri i tehničari"],
    scholar: ["je nastavnik ili predavač", "su nastavnici i predavači"],
    healer: ["radi u zdravstvu", "rade u zdravstvu"],
    service: ["radi u uslugama ili trgovini", "rade u uslugama ili trgovini"],
    clerk: ["je administrativni službenik", "su administrativni službenici"],
    farmer: ["bavi se poljoprivredom, šumarstvom ili ribolovom", "bave se poljoprivredom, šumarstvom ili ribolovom"],
    builder: ["je zanatlija ili srodni radnik", "su zanatlije i srodni radnici"],
    maker: ["rukuje mašinom, montira ili vozi", "rukuju mašinama, montiraju ili voze"],
  },
  age: {
    child: ["ima do 14 godina", "imaju do 14 godina"],
    young: ["ima 15–29 godina", "imaju 15–29 godina"],
    midlife: ["ima 30–54 godine", "imaju 30–54 godine"],
    elder: ["ima 55 ili više godina", "imaju 55 ili više godina"],
  },
  commute: {
    home_settlement: ["radi u naselju u kom stanuje", "rade u naselju u kom stanuju"],
    same_municipality: ["radi u drugom naselju iste opštine", "rade u drugom naselju iste opštine"],
    other_municipality: ["radi u drugoj opštini", "rade u drugoj opštini"],
    other_area: ["radi u drugom okrugu", "rade u drugom okrugu"],
    abroad: ["radi u inostranstvu", "rade u inostranstvu"],
  },
  education: {
    less_than_hs: ["nema završenu osnovnu školu", "nemaju završenu osnovnu školu"],
    primary: ["ima osnovnu školu", "imaju osnovnu školu"],
    high_school: ["ima srednju školu", "imaju srednju školu"],
    bachelors: ["ima višu školu", "imaju višu školu"],
    graduate: ["ima fakultet, master ili doktorat", "imaju fakultet, master ili doktorat"],
  },
  nativity: {
    same_settlement: ["od rođenja stanuje u istom naselju", "od rođenja stanuju u istom naselju"],
    elsewhere_serbia: ["doseljen je iz drugog mesta u Srbiji", "doseljeni su iz drugog mesta u Srbiji"],
    former_yugoslavia: ["doselio se iz bivše jugoslovenske republike", "doselili su se iz bivših jugoslovenskih republika"],
    other_country: ["doselio se iz druge države", "doselili su se iz drugih država"],
  },
};

// Short legend labels (the file's labels are long); a category without one shows the file's label.
const SHORT = {
  workforce: { executive: "Rukovodioci", engineer: "Stručnjaci i tehničari", scholar: "Nastavnici", healer: "Zdravstvo",
    service: "Usluge i trgovina", clerk: "Administrativa", farmer: "Poljoprivreda", builder: "Zanatlije", maker: "Mašine i transport" },
  age: { child: "do 14", young: "15–29", midlife: "30–54", elder: "55+" },
  commute: { home_settlement: "U naselju", same_municipality: "Ista opština", other_municipality: "Druga opština", other_area: "Drugi okrug", abroad: "U inostranstvu" },
  education: { less_than_hs: "Bez osnovne", primary: "Osnovna", high_school: "Srednja", bachelors: "Viša", graduate: "Fakultet i više" },
  nativity: { same_settlement: "Od rođenja ovde", elsewhere_serbia: "Doseljeni u Srbiji", former_yugoslavia: "Bivša SFRJ", other_country: "Druge države" },
};

/** Largest-remainder rounding of counts into n figures (the pipeline's method, for rows without figures). */
export function largestRemainder(counts, keys, n) {
  const tot = keys.reduce((a, k) => a + (counts[k] || 0), 0);
  if (!(tot > 0)) return null;
  const raw = keys.map((k) => ((counts[k] || 0) / tot) * n);
  const out = raw.map(Math.floor);
  let left = n - out.reduce((a, v) => a + v, 0);
  const order = raw.map((v, j) => [v - Math.floor(v), j]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let k = 0; k < left; k++) out[order[k][1]]++;
  return Object.fromEntries(keys.map((k, j) => [k, out[j]]));
}

/** "1 od 7", "3 od 10", "manje od 1 od 1.000". */
export function oneIn(share) {
  if (share == null || !Number.isFinite(share)) return null;
  if (share <= 0) return { text: "nijedan", plural: true };
  if (share < 0.001) return { text: "manje od 1 od 1.000", plural: false };
  if (share >= 0.3) {
    const k = Math.round(share * 10);
    return k >= 10 ? { text: "skoro svi", plural: true } : { text: `${int(k)} od 10`, plural: k !== 1 };
  }
  const n = Math.round(1 / share);
  return { text: `1 od ${int(n)}`, plural: n === 1 };
}

function sentence(rowId, key, share, natShare, cityName, noun) {
  const a = oneIn(share);
  if (!a) return "";
  const ph = PHRASE[rowId]?.[key] || ["je u ovoj grupi", "su u ovoj grupi"];
  const nat = oneIn(natShare);
  const lead = a.text.charAt(0).toUpperCase() + a.text.slice(1);
  return `${lead} ${noun[1]} u ${cityName} ${a.plural ? ph[1] : ph[0]}${nat ? ` (${NATION}: ${nat.text})` : ""}`;
}

function rowModel(rowDef, row, nat, groups, figuresN) {
  const keys = (groups[rowDef.id] || []).map((g) => g.key);
  const n = figuresN[rowDef.id] ?? rowDef.n ?? 10;
  const figs = row.figures || largestRemainder(row.counts || {}, keys, n);
  const natFigs = nat?.figures || (nat ? largestRemainder(nat.counts || {}, keys, n) : null);
  return { keys, n, figs, natFigs };
}

// Specialists by row/key from the file (ratios from unrounded shares).
function specMap(city) {
  const m = new Map();
  for (const s of city?.specialists || []) m.set(`${s.row}|${s.key}`, s);
  return m;
}

/** The Citizens rows. data = citizens.json (or null / undefined while loading). */
export function citizensHtml(m, data) {
  const c = m.city;
  if (data === undefined) return `<p class="muted cv-note">Učitavamo stanovništvo…</p>`;
  if (!data || !data.cities) return `<p class="muted cv-note">Podaci o stanovništvu nisu dostupni.</p>`;
  const row0 = data.cities[c.id];
  if (!row0) {
    return `<p class="muted cv-note">Popis stanovništva 2022. nije sproveden za ${esc(c.name)}, pa ovde nema podataka o stanovništvu.</p>`;
  }
  const nat = data.national || {};
  const groups = data.groups || {};
  const specs = specMap(row0);
  const label = Object.fromEntries(Object.entries(groups).map(([r, gs]) => [r, Object.fromEntries(gs.map((g) => [g.key, g.label]))]));
  const short = (r, k) => SHORT[r]?.[k] || label[r]?.[k] || k;
  const vintage = esc(data.vintage || "Popis 2022");

  // Headline chips from the file's own shares: higher education and residents who moved from abroad
  // (bivše jugoslovenske republike + druge države), each against the national share.
  const sumShare = (row, ks) => (row?.shares && ks.every((k) => row.shares[k] != null) ? ks.reduce((a, k) => a + row.shares[k], 0) : null);
  const hi = [sumShare(row0.education, ["bachelors", "graduate"]), sumShare(nat.education, ["bachelors", "graduate"])];
  const abroad = [sumShare(row0.nativity, ["former_yugoslavia", "other_country"]), sumShare(nat.nativity, ["former_yugoslavia", "other_country"])];
  const chip = (pair, fmt, lbl, tip) => (pair[0] == null ? "" : `<div class="cv-cz-chip" title="${esc(tip)}"><b>${fmt(pair[0])}</b><span>${esc(lbl)}</span>${pair[1] != null ? `<small>${NATION} ${fmt(pair[1])}</small>` : ""}</div>`);
  const top = (row0.specialists || []).find((s) => s.ratio >= (data.rule?.specialist_high ?? 1.5));
  const topRow = ROWS.find((r) => r.id === top?.row);
  const ratio = (r) => `${r.toFixed(1).replace(".", ",")}×`;
  const great = top && topRow ? `<div class="cv-great" style="--fc:${esc(CATEGORY_COLOR[top.row]?.[top.key] || "#c9a45c")}">
      <span class="cv-great-fig" data-great="${esc(top.row)}|${esc(top.key)}" aria-hidden="true"></span>
      <div><small>Ističu se</small><b>${esc(label[top.row]?.[top.key] || top.key)}</b>
      <span>${pct(top.share, 1)} ${topRow.noun[1]} ovde, ${pct(top.national, 1)} u ${NATION}i: ${ratio(top.ratio)} nacionalnog udela.</span></div></div>` : "";

  const rows = ROWS.map((rd) => {
    const row = row0[rd.id];
    const head = `<div class="cv-cz-h"><b>${esc(rd.title)}</b><span>${esc(rd.sub)}</span></div>`;
    if (!row) {
      return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}
        <p class="muted cv-note">Popis 2022. ne objavljuje ovu tabelu za ${esc(c.name)}, pa je ovaj red prazan.</p></div>`;
    }
    const { keys, n, figs, natFigs } = rowModel(rd, row, nat[rd.id], groups, data.figures || {});
    if (!figs) return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}<p class="muted cv-note">Nema brojeva za ovaj red.</p></div>`;
    const per = row.total / n;
    const cells = [];
    for (const k of keys) {
      for (let j = 0; j < (figs[k] || 0); j++) {
        const sp = specs.get(`${rd.id}|${k}`);
        const mark = sp ? (sp.ratio >= 1 ? "up" : "down") : "";
        // One tab stop per category (its first figure), not one per figure.
        cells.push(`<span class="cv-fig${mark ? ` ${mark}` : ""}" tabindex="${j ? -1 : 0}" role="img" data-k="${esc(k)}" aria-label="${esc(label[rd.id]?.[k] || k)}"></span>`);
      }
    }
    // Legend: every category, with its share, the national share and a chevron for specialists. Categories that
    // round to no figure are still listed (greyed), so nothing silently disappears; a category the census does not
    // publish (a null share) is listed as "nema podataka".
    const legend = keys.map((k) => {
      const sh = row.shares?.[k], ns = nat[rd.id]?.shares?.[k];
      const sp = specs.get(`${rd.id}|${k}`);
      const chev = sp ? `<em class="${sp.ratio >= 1 ? "up" : "down"}" title="${ratio(sp.ratio)} nacionalnog udela">${sp.ratio >= 1 ? "▲" : "▼"}</em>` : "";
      const tip = sh == null ? "nema podataka" : `${pct(sh, 1)}${ns != null ? ` (${NATION}: ${pct(ns, 1)})` : ""}${figs[k] ? "" : ". Zaokružuje se bez figure."}`;
      return `<span class="cv-cz-k${figs[k] ? "" : sh == null ? " na" : " zero"}" data-k="${esc(k)}" title="${esc(label[rd.id]?.[k] || k)}: ${esc(tip)}"><i style="background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}"></i>${esc(short(rd.id, k))} <small>${sh != null ? pct(sh, 0) : "–"}</small>${chev}</span>`;
    }).join("");
    // The national comparison bar (shares), aligned with the figures' order.
    const usBar = nat[rd.id]?.shares ? `<div class="cv-cz-us" title="${NATION}: isti redosled"><span>${NATION}</span><div>${keys.map((k) => {
      const s = nat[rd.id].shares[k] || 0;
      return s > 0 ? `<i style="flex:${s};background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}" title="${esc(short(rd.id, k))}: ${pct(s, 1)} u ${NATION}i"></i>` : "";
    }).join("")}</div></div>` : "";
    const cap = `Svaka figura ≈ ${compact(per)} ${rd.noun[1]} · ukupno ${compact(row.total)}${rd.n && !row.figures ? " · zaokruženo ovde" : ""}`;
    return `<div class="cv-cz-row" data-row="${rd.id}" style="--n:${n}">${head}
      <div class="cv-figs" role="group" aria-label="${esc(rd.title)}: ${keys.filter((k) => figs[k]).map((k) => `${figs[k]} od ${n} ${short(rd.id, k)}`).join(", ")}">${cells.join("")}</div>
      ${usBar}
      <div class="cv-cz-out" aria-live="polite" data-default="${esc(cap)}">${esc(cap)}</div>
      <div class="cv-cz-legend">${legend}</div>
    </div>`;
  }).join("");

  const unreliable = row0.reliable === false
    ? `<p class="cv-warn">Podaci su procena sa velikom greškom uzorka, pa ih čitajte kao okvirne.</p>` : "";
  return `
    <div class="cv-cz-top">
      ${chip(hi, (v) => pct(v, 0), "sa višom ili visokom školom", "Stanovništvo 15+ sa višim ili visokim obrazovanjem (Popis 2022, tabela 3)")}
      ${chip(abroad, (v) => pct(v, 0), "doseljeni iz inostranstva", "Stanovništvo doseljeno iz bivših jugoslovenskih republika ili drugih država (Popis 2022, tabela 13)")}
    </div>
    ${great}
    ${unreliable}
    <div class="cv-cz${row0.reliable === false ? " unreliable" : ""}">${rows}</div>
    <p class="cv-note">${vintage}: zanimanja (tabela 25), starost (tabela 2), dnevne migracije, školska sprema (tabela 3) i migratorna obeležja (tabela 13). Figure su zaokružene (najveći ostatak) da svaki red zbraja ikone; stavite kursor ili dodirnite figuru za njen udeo. ▲▼ = najmanje 1,5× odnosno najviše 0,67× nacionalnog udela. Nacionalni red je Republika Srbija bez Kosova i Metohije.</p>`;
}

/** Paint the figure canvases and wire the read-outs. */
export function mountCitizens(host, m, data) {
  if (!host || !data?.cities?.[m.city.id]) return;
  const row0 = data.cities[m.city.id];
  const nat = data.national || {};
  const dpr = Math.min(3, Math.max(1, Math.round((devicePixelRatio || 1) * 2) / 2));
  const paintAll = () => {
    host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
      const rid = rowEl.dataset.row;
      rowEl.querySelectorAll(".cv-fig").forEach((el) => {
        const src = figureCanvas(rid, el.dataset.k, 36, dpr);
        const cv = document.createElement("canvas");
        cv.width = src.width;
        cv.height = src.height;
        cv.getContext("2d").drawImage(src, 0, 0);
        el.replaceChildren(cv);
      });
    });
    const g = host.querySelector("[data-great]");
    if (g) {
      const [rid, k] = g.dataset.great.split("|");
      const src = figureCanvas(rid, k, 36, dpr);
      const cv = document.createElement("canvas");
      cv.width = src.width;
      cv.height = src.height;
      cv.getContext("2d").drawImage(src, 0, 0);
      g.replaceChildren(cv);
    }
  };
  paintAll();
  // Once the citizen painter (render/art/people.js) loads, repaint the figures.
  loadPainter().then(() => { if (host.isConnected) paintAll(); });

  host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
    const rid = rowEl.dataset.row;
    const rd = ROWS.find((r) => r.id === rid);
    const row = row0[rid];
    const out = rowEl.querySelector(".cv-cz-out");
    if (!row || !out) return;
    const show = (k) => {
      rowEl.querySelectorAll("[data-k]").forEach((el) => el.classList.toggle("lit", el.dataset.k === k));
      rowEl.classList.toggle("focus", !!k);
      if (!k) {
        out.textContent = out.dataset.default;
        out.classList.remove("on");
        return;
      }
      const sh = row.shares?.[k], us = nat[rid]?.shares?.[k];
      out.innerHTML = `${esc(sentence(rid, k, sh, us, m.city.name, rd.noun))}<small>${sh != null ? pct(sh, 1) : "nema podataka"} ovde${us != null ? ` · ${pct(us, 1)} u ${NATION}i` : ""}${row.counts?.[k] != null ? ` · ≈${compact(row.counts[k])}` : ""}</small>`;
      out.classList.add("on");
    };
    let pinned = null;
    rowEl.addEventListener("pointerover", (e) => {
      const el = e.target.closest("[data-k]");
      if (el && rowEl.contains(el)) show(el.dataset.k);
    });
    rowEl.addEventListener("pointerleave", () => show(pinned));
    rowEl.addEventListener("focusin", (e) => {
      const el = e.target.closest("[data-k]");
      if (el) show(el.dataset.k);
    });
    rowEl.addEventListener("focusout", () => show(pinned));
    // A tap pins the category (phones have no hover); another tap on it lets go.
    rowEl.addEventListener("click", (e) => {
      const el = e.target.closest("[data-k]");
      if (!el) return;
      pinned = pinned === el.dataset.k ? null : el.dataset.k;
      show(pinned);
    });
  });
}
