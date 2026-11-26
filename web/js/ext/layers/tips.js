// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (park visitor counts are not published in Serbia, so parks rank by area;
// UNESCO sites and curated landmarks are an editorial pick; a blank figure means no data, never zero).
import { esc, compact, int, pct, money } from "../../format.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n, d = 1) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");

/** A money amount in the currency of the map's data (format.js money). */
const amount = (n) => (n == null || !Number.isFinite(n) ? "–" : money(n));

const HUB_NAME = { L: "Veliki čvor", M: "Srednji čvor", S: "Mali čvor", N: "Primarni aerodrom koji nije čvor" };
const PORT_TYPE = { coastal: "Morska luka", great_lakes: "Luka na Velikim jezerima", inland: "Rečna luka" };

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const lines = [
      `<b>${esc(p.name)}</b> ${muted(`${esc(PORT_TYPE[p.type] || "Luka")}, ${esc(p.state || "")}`)}`,
      `#${esc(p.rank)} po tonaži · <b>${num(p.tons)}</b> t (${esc(yr)})`,
    ];
    if (p.foreign != null || p.domestic != null) lines.push(`Inostrani ${num(p.foreign)} · domaći ${num(p.domestic)}`);
    if (p.imports != null || p.exports != null) lines.push(`Uvoz ${num(p.imports)} · izvoz ${num(p.exports)}`);
    lines.push(muted("Glavne luke; nacrtane na središtu lučkog područja (dugačke rečne luke su približne)."));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(a.name)}</b> ${muted(esc([a.city, a.state].filter(Boolean).join(", ")))}`];
    lines.push(a.hub ? esc(HUB_NAME[a.hub] || a.hub) : "Teretni aerodrom (nije primarni putnički aerodrom)");
    if (a.enplanements != null) {
      let ch = "";
      if (a.enplanements_prev > 0) {
        const r = a.enplanements / a.enplanements_prev - 1;
        ch = ` (${sign(r)}${pct(Math.abs(r), 1)} u odnosu na ${a.year - 1})`;
      }
      lines.push(`<b>${num(a.enplanements)}</b> putnika ukrcano ${esc(a.year)}${ch}`);
    }
    if (a.cargo_lbs != null) lines.push(`Težina teretnih aviona pri sletanju ${num(a.cargo_lbs)} lb`);
    lines.push(muted("Podaci o ukrcanim putnicima i teretnom saobraćaju, za kalendarsku godinu."));
    return lines.join("<br>");
  },
  fort(f, m) {
    const comp = m.data.military?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || "Vojni objekat";
    const tier = { major: "Veliki objekat", base: "Baza", site: "Manji objekat" }[f.tier] || "";
    const status = { act: "", semi: " · ograničena aktivnost", care: " · u konzervaciji" }[f.status] ?? "";
    const lines = [
      `<b>${esc(f.name)}</b> ${muted(esc(f.state || ""))}`,
      `${esc(name)}${f.joint ? " · zajednička baza" : ""} · ${esc(tier)}${esc(status)}`,
    ];
    if (f.area_km2 != null) lines.push(`Površina unutar granice ${int(f.area_km2)} km²`);
    lines.push(muted("Veličina znaka prati površinu unutar granice, a ne broj pripadnika."));
    return lines.join("<br>");
  },
  range(r, m) {
    const comp = m.data.military?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(r.name)}</b> ${muted(esc(r.state || ""))}`,
      `Zabranjeni teren · ${esc(comp?.name || "")} · ${int(r.area_km2)} km²`,
      muted("Jedan od 30 najvećih vojnih poligona, nacrtan na heksovima koje pokriva."),
    ].join("<br>");
  },
  wonder(x, m) {
    const k = WONDER_KINDS[x.kind]?.name || "Čudo";
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const okrug = m.data.states?.find((s) => s.fips === x.state)?.name || x.state;
    const mt = x.metrics || {};
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc(okrug || ""))}`];
    if (x.kind === "university") {
      lines.push(`${esc(k)} · #${esc(x.rank)} po broju upisanih studenata`);
      if (mt.enrollment != null) lines.push(`<b>${int(mt.enrollment)}</b> studenata (${esc(mt.enrollment_year || "")})`);
      if (mt.rd_usd != null) lines.push(`Istraživanje i razvoj ${amount(mt.rd_usd)} (${esc(mt.year)})`);
    } else if (x.curated) {
      lines.push(mt.inscribed != null
        ? `${esc(k)} · na UNESCO-ovoj listi svetske baštine od ${esc(mt.inscribed)}`
        : `${esc(k)} · ručni izbor (urednički, ne po podacima)`);
      if (x.listed_as) lines.push(muted(`Upisano kao: ${esc(x.listed_as)}`));
    } else {
      lines.push(`${esc(k)} · #${esc(x.rank)} po površini${mt.unit_type ? ` među ${esc(mt.unit_type === "Nacionalni park" ? "nacionalnim parkovima" : "ostalim zaštićenim područjima")}` : ""}`);
      if (mt.area_km2 != null) lines.push(`<b>${int(mt.area_km2)}</b> km²`);
      if (mt.designated) lines.push(`Zaštićeno od ${esc(mt.designated)}.`);
      if (mt.visits != null) lines.push(`${num(mt.visits)} poseta (${esc(mt.year)})`);
    }
    if (x.state_note) lines.push(muted(esc(x.state_note)));
    if (x.note) lines.push(muted(esc(x.note)));
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const t = m.data.trade || {};
    const a = rt.a?.short || rt.a?.name || r.a, b = rt.b?.short || rt.b?.name || r.b;
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(MODE_STYLE[k]?.label || k)} ${pct(v, 0)}`).join(" · ");
    const com = t.commodities?.[r.top_commodity];
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(`trgovinski put br. ${esc(r.rank)}`)}`,
      `<b>${amount(r.value_musd * 1e6)}</b> robe godišnje, ${num(r.tons_k * 1e3)} t (procena, ${esc(t.year ?? "")})`,
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(`Najznačajnija roba: ${esc(com)}`);
    lines.push(muted("Zbir u oba smera. Nacrtan kao luk između najvećih gradova zona: podaci beleže gde teret kreće i gde staje, a ne njegov put."));
    return lines.join("<br>");
  },
};
