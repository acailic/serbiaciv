// Shareable URL state:  #lens=income&city=35620&state=06&at=x,y,zoom
//   at = map-km centre (rounded) and zoom as log2(scale / home-fit scale), so a link frames the same area on any screen.
// Lens or selection changes push a history entry (so Back undoes them); camera moves replace the current one.


export function parseHash(hash) {
  const p = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  const out = { lens: p.get("lens") || null, city: p.get("city") || null, state: p.get("state") || null, at: null,
    script: ["lat", "cyr"].includes(p.get("script")) ? p.get("script") : null };
  const at = (p.get("at") || "").split(",").map(Number);
  if (at.length === 3 && at.every(Number.isFinite)) out.at = at;
  return out;
}

export function formatHash(o) {
  const parts = [];
  if (o.lens) parts.push(`lens=${encodeURIComponent(o.lens)}`);
  if (o.city) parts.push(`city=${encodeURIComponent(o.city)}`);
  if (o.state) parts.push(`state=${encodeURIComponent(o.state)}`);
  if (o.at) parts.push(`at=${Math.round(o.at[0])},${Math.round(o.at[1])},${(+o.at[2]).toFixed(2).replace(/\.?0+$/, "") || "0"}`);
  if (["lat", "cyr"].includes(o.script)) parts.push(`script=${o.script}`);
  return parts.length ? "#" + parts.join("&") : "";
}

/** Change only the script parameter, preserving the rest of a shared link. */
export function withScript(hash, script) {
  const parts = String(hash || "").replace(/^#/, "").split("&").filter(Boolean)
    .filter((part) => part.split("=", 1)[0] !== "script");
  if (["lat", "cyr"].includes(script)) parts.push(`script=${script}`);
  return parts.length ? `#${parts.join("&")}` : "";
}
