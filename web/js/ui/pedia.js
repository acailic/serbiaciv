// The Almanah: what every number means and exactly where it comes from (Serbian data; vocabulary: docs/GLOSSARY.md).
import { resolveTables } from "../terrain.js";
import { esc, int } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "Energija", mineral: "Minerali", agri: "Poljoprivreda" };
const SCALE = { linear: "linearna skala", log: "logaritamska skala" };
// A source with several datasets carries its vintage as {dataset: "Procene stanovništva, 1991–2025"}: a reader gets the
// values, once each and in the file's order, since the dataset keys are English identifiers and two datasets can share
// a file; a plain string is passed through.
export const vintageText = (v) => (v && typeof v === "object" ? [...new Set(Object.values(v))].join("; ") : v || "");

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;

  const pages = {
    "O ovoj karti": () => `
      ${h2("pedia", "📖", "O ovoj karti")}
      <p>Ovo je prava Srbija, nacrtana kao strategija. Ništa nije izmišljeno: svaki heks, grad i broj dolazi iz javnih
      podataka, navedenih pod <i>Izvorima</i>.</p>
      <h4>Kako je napravljena</h4>
      <p>Srbija, sa Kosovom i Metohijom, projektovana je Alberskom jednakopovršinskom projekcijom i isečena na
      ${data.world.grid.cols}×${data.world.grid.rows} heksova, svaki po ${data.world.grid.radius * 2} km od ugla do ugla. Svaki heks pripada
      okrugu i opštini na čijem se središtu nalazi. Teren dolazi iz uzoraka nadmorske visine (Copernicus GLO-30), a boja
      zemljišta iz pokrivača zemljišta (ESA WorldCover) unutar svakog heksa.</p>
      <p>Kosovo i Metohija je u okviru karte: njegov teren, reke i granice opština crtaju se iz stvarnih podataka. Republički
      zavod za statistiku i Eurostat ne objavljuju statistiku za njegove okruge, pa tamo gde drugi okruzi imaju brojeve stoji
      <i>nema podataka</i>, a ne nula.</p>
      <p><b>Gradovi</b> su opštine koje su gradovi: svaka ima gradsko naselje od najmanje 10.000 stanovnika (Popis 2022) i
      najmanje 25.000 stanovnika na svom području (procene RZS), i stoji na svom gradskom naselju. Brojevi grada pokrivaju
      celu njegovu opštinu, a ne samo naselje; Grad Beograd, Novi Sad, Niš, Požarevac, Vranje i Užice prikazani su kao po
      jedan grad, sa zbirom svojih gradskih opština.</p>
      <h4>Kontrole</h4>
      <p>Prevlačenje ili strelice / WASD za pomeranje · točkić, +/– ili dvoklik za uvećanje · klik na grad ili okrug ga
      otvara · / ili ⌘K za pretragu · L za smenu sočiva · R za prikaz ili skrivanje resursa · ? za sve prečice · Esc za
      zatvaranje.</p>
      <p>Adresna traka uvek drži vezu na ono što gledate (sočivo, izbor i pogled); upotrebite <i>Podeli</i> da je
      iskopirate ili da preuzmete sliku.</p>`,
    Prinosi: () => `
      ${h2("y-production", "⚙️", "Prinosi")}
      <p>Prinosi iz strategije preslikani na stvarne mere. Prinosi po zaposlenima broje <i>stanovnike</i> koji rade u
      nekoj delatnosti (gde radnik živi, ne gde radi). <b>Zlato je BDP</b>: proizvodnja u jednoj godini, računata tamo
      gde se radi. Za okrug je to njegov BDP iz Eurostata, a za grad procena: BDP okruga prema udelu grada u zaposlenima okruga.</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? " (BDP)" : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      <h4>Nezaposlenost i prihodi</h4>
      <p>Nezaposlenost = nezaposleni ÷ aktivno stanovništvo (Popis 2022). Prosečna neto zarada je RZS-ova zarada zaposlenih
      u opštini (na ime rada, u dinarima); medijalna kirija i vrednost kuća po opštinama nisu objavljeni u izvorima ove
      karte, pa se ne prikazuju.</p>`,
    Okruzi: () => `
      ${h2("terrain", "🗺️", "Okruzi")}
      <p>Kliknite na bilo koji heks kopna bez grada da otvorite njegov okrug. Brojevi okruga zbir su njegovih opština iz
      istih tabela kao i za gradove (${esc(data.nation.vintage)}${data.nation.gdp_vintage ? `; BDP iz: ${esc(data.nation.gdp_vintage)}` : ""}),
      a ne zbir njegovih gradova, pa se i sela računaju. Stope se ne sabiraju: udeo starih je ponderisan stanovništvom,
      zarada zaposlenima, a nezaposlenost je iz zbirnih brojeva.</p>
      <p><b>Rangovi</b> („#3 od 25“) porede 25 okruga Srbije bez Kosova i Metohije; 1 je najveći. Pet okruga Kosova i
      Metohije je na karti, ali nema statistiku, pa nije rangirano. Republički zavod za statistiku i Eurostat te iste
      oblasti zovu <i>oblast</i> (NUTS-3); na ovoj karti zovu se okruzi.</p>
      ${data.states ? "" : `<p class="muted">Ova verzija podataka nema states.json, pa paneli okruga pokazuju samo imena i gradove.</p>`}`,
    Teren: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", "Teren")}
      <p>Svaki heks ima srednju nadmorsku visinu uzoraka Copernicus GLO-30 (30 m) unutar njega. Reljef dolazi iz srednje
      visine i hrapavosti (standardne devijacije) tih uzoraka; senčenje dolazi iz razlika visine sa susednim heksima, pri
      svetlu sa severozapada.</p>
      <h4>${icon("l-forest", "🌲", { size: 16 })} Pokrivač zemljišta</h4>
      ${hasCover
        ? `<p>Osnovna boja svakog heksa je njegova najveća grupa pokrivača zemljišta (ESA WorldCover 2021, 10 m): najveća
           grupa među uzorcima zemljišta unutar njega. Mali simboli pokazuju mešavinu: drveće raste sa udelom šume, a njive,
           trske, žbunje i travke označavaju obradivo zemljište, močvare, žbunje i travnjake.</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">Ova verzija podataka nema sloj pokrivača zemljišta; zemlja je obojena po visini.</p>`}
      <h4>Reljef</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} Voda</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>Preko granice</h4>
      <p class="muted">Strano zemljište (susedne države) crtano je pod svetlom maglom: prikazano je radi konteksta, a ne
      crtano detaljno.</p>`;
    },
    Sočiva: () => `
      ${h2("layers", "▤", "Sočiva")}
      <p>Sočiva boje mapu po jednoj meri, sastavljenoj iz podataka po opštinama (${esc(data.lenses.vintage)}). Zavod i popis
      objavljuju po opštini, a o tome gde ljudi žive unutar opštine ništa nije poznato, pa statističko sočivo daje svakom
      heksu opštine vrednost te opštine: ništa se ne interpolira i nijedna opština se ne deli. Za Kosovo i Metohiju nema
      statistike, pa su njegovi heksovi, kao i strano zemljište i voda, bez vrednosti. Tri sočiva zemljišta čitaju se heks po
      heks iz world.json, pa obuhvataju i Kosovo i Metohiju.</p>
      <p>Legenda pokazuje koliko heksova pada na svaku vrednost. Zadržite kursor ili prevucite preko nje da pokažete samo taj
      raspon na karti.</p>
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">${SCALE[l.scale] || esc(l.scale)}, ${int(l.domain[0])}–${int(l.domain[1])} ${esc(l.unit)}${
            l.higher_is === "good" ? " · više je bolje" : l.higher_is === "bad" ? " · više je loše" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Resursi: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", "Resursi")}<p class="muted">Ova verzija podataka nema sloj resursa.</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", "⛏️", "Resursi")}
      <p>Resursi obeležavaju najveće elektrane, rudnike i nalazišta Srbije na heksima na kojima se nalaze. Prikazuju se samo
      značajna mesta: prag svake vrste piše u njenom opisu. Pri umanjenju heks pokazuje svoj najviše rangirani resurs; uvećajte
      da vidite više. Pritisnite <b>R</b> da ih prikažete ili sakrijete.</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>Vrsta</th><th>Šta se računa</th><th>Mesta</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">vrednost u ${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}<br><span class="muted">Izvor: ${esc(srcName(t.source))}</span></td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Izvori: () => `
      ${h2("pedia", "📖", "Izvori")}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(vintageText(s.vintage)) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">početna stranica</a></span></p>
        ${(s.files || []).length
          ? `<table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1).replace(".", ",")} MB</td></tr>`).join("")}</table>`
          : (s.curated ? `<p class="muted">Ništa nije preuzeto: podaci su pročitani sa navedene stranice.</p>` : "")}`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "O ovoj karti";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">Almanah</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(p)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "O ovoj karti") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
