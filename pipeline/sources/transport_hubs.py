"""Serbia's river ports and airports: what the map's "hubs" layer draws and what their tooltips say.

Three sources, each with one publisher behind it:

* ``river_ports`` – the Agency for the Management of Ports (Agencija za upravljanje lukama, AUL) publishes one
  presentation a year, "Analiza aktivnosti u lukama i pristaništima", with the cargo transshipped in every port area
  (lučko područje). The table lives inside a chart whose cached values this module reads, so no figure is retyped.
* ``airports`` – OurAirports' public-domain list of the world's airports: which Serbian airports are large or medium,
  with their ICAO code, coordinates and scheduled service.
* ``airport_traffic`` – Eurostat's annual passengers per airport (avia_paoa; Serbia reports Beograd and Niš) and the
  operator Morava's own statistics page for Kraljevo, which Eurostat does not carry. Cargo is published only in PDF
  reports, so it is left out.

Nothing here knows about hexes; the infrastructure builder places the sites.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from xml.etree import ElementTree

from ..core import srb
from ..core.source import Source, SourceInfo
from ..core.srtext import to_latin

AUL_FILE = "analiza-aktivnosti-u-lukama-i-pristanishtima-u-2025.pptx"
OURAIRPORTS_FILE = "airports.csv"
EUROSTAT_FILE = "avia_paoa.json"
MORAVA_FILE = "morava-statistika.html"

PORT_MARKERS = ("Панчево", "Смедерево")  # the per-port chart is the one naming these port areas
CHART_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
ICAO = re.compile(r"^[A-Z]{4}$")


def _cache_points(node) -> dict[int, str]:
    """{idx: text} of a chart's <c:strCache> or <c:numCache>."""
    out = {}
    for pt in node.findall(f"{CHART_NS}pt"):
        v = pt.find(f"{CHART_NS}v")
        out[int(pt.get("idx", len(out)))] = (v.text or "") if v is not None else ""
    return out


def _int(text: str) -> int | None:
    digits = text.replace(".", "").replace(",", "").replace(" ", "")
    return int(digits) if digits.isdigit() else None


def _tonnes(text: str) -> int | None:
    """A chart value in tonnes, rounded to whole tonnes; None when it is blank or not a number."""
    try:
        v = float(text)
    except ValueError:
        return None
    return round(v)


def ports_from_pptx(data: bytes) -> tuple[int, list[dict]]:
    """(year, [{name, tons}]) from the AUL presentation: the chart that names the port areas, its latest series the
    current year, tonnes rounded to whole tonnes. Names come out in Serbian Latin."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    charts = sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/charts/chart\d+\.xml", n)),
                    key=lambda n: int(re.findall(r"\d+", n)[-1]))
    for name in charts:
        root = ElementTree.fromstring(zf.read(name))
        series = []
        for ser in root.iter(f"{CHART_NS}ser"):
            tx = ser.find(f"{CHART_NS}tx//{CHART_NS}v")
            cat = ser.find(f"{CHART_NS}cat//{CHART_NS}strCache")
            val = ser.find(f"{CHART_NS}val//{CHART_NS}numCache")
            label = (tx.text or "").strip() if tx is not None else ""
            if cat is None or val is None or not label.isdigit():
                continue
            series.append((int(label), _cache_points(cat), _cache_points(val)))
        named = {v.strip() for _, cats, _ in series for v in cats.values()}
        if not series or not all(m in named for m in PORT_MARKERS):
            continue
        year = max(y for y, _, _ in series)
        ports = []
        for y, cats, vals in series:
            if y != year:
                continue
            for idx, nm in sorted(cats.items()):
                tons = _tonnes(vals.get(idx, ""))
                if tons is not None:
                    ports.append({"name": to_latin(nm.strip()), "tons": tons})
        return year, ports
    raise ValueError(f"no port-area chart ({', '.join(PORT_MARKERS)}) in {AUL_FILE}")


def airports_from_csv(text: str) -> list[dict]:
    """OurAirports rows of Serbia's large and medium airports: {icao, type, name, lon, lat, municipality, scheduled}."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("iso_country") != "RS" or row.get("type") not in srb.AIRPORT_TYPES:
            continue
        code = (row.get("icao_code") or row.get("ident") or "").strip().upper()
        if not ICAO.match(code):
            continue
        try:
            lon, lat = float(row["longitude_deg"]), float(row["latitude_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"icao": code, "type": row["type"], "name": row.get("name") or code, "lon": lon, "lat": lat,
                    "municipality": (row.get("municipality") or "").strip() or None,
                    "scheduled": row.get("scheduled_service") == "yes"})
    out.sort(key=lambda a: a["icao"])
    return out


def passengers_from_jsonstat(data: dict, country: str = "RS") -> dict[str, dict[int, int | None]]:
    """{icao: {year: passengers carried or None}} from Eurostat's JSON-stat (avia_paoa), one reporting country."""
    dims, sizes, names = data["dimension"], data["size"], data["id"]

    def pos(dim: str, code: str) -> int:
        return dims[dim]["category"]["index"][code]

    fixed = {"freq": pos("freq", "A"), "unit": pos("unit", "PAS"), "tra_meas": pos("tra_meas", "PAS_CRD"),
             "schedule": pos("schedule", "TOTAL"), "tra_cov": pos("tra_cov", "TOTAL")}

    def flat(code_i: int, time_i: int) -> str:
        idx = [code_i if n == "rep_airp" else time_i if n == "time" else fixed[n] for n in names]
        f, stride = 0, 1
        for n, i in zip(reversed(names), reversed(idx)):
            f += i * stride
            stride *= sizes[names.index(n)]
        return str(f)

    years = dims["time"]["category"]["index"]
    out: dict[str, dict[int, int | None]] = {}
    for code, ci in dims["rep_airp"]["category"]["index"].items():
        if not code.startswith(f"{country}_"):
            continue
        series = {}
        for y, ti in years.items():
            v = data.get("value", {}).get(flat(ci, ti))
            series[int(y)] = None if v in (None, "") else round(float(v))
        out[code.split("_", 1)[1]] = series
    return out


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.S)]


def passengers_from_html(html: str) -> dict[int, int]:
    """{year: passengers} from a page holding a table with a GODINA row (years) and a BROJ PUTNIKA row (passengers)."""
    for table in re.findall(r"<table.*?</table>", html, flags=re.S):
        rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", table, flags=re.S)]
        head = next((r for r in rows if r and r[0].upper() == "GODINA"), None)
        pax = next((r for r in rows if r and r[0].upper() == "BROJ PUTNIKA"), None)
        if not head or not pax:
            continue
        out = {}
        for y, v in zip(head[1:], pax[1:]):
            if y.isdigit() and _int(v) is not None:
                out[int(y)] = _int(v)
        return out
    return {}


class RiverPorts(Source):
    info = SourceInfo(
        id="river_ports",
        title="Promet robe u lukama i pristaništima",
        publisher="Agencija za upravljanje lukama (AUL)",
        homepage="http://www.aul.gov.rs/prezentacije",
        license="Javno objavljena godišnja analiza (prezentacija AUL)",
        description="Godišnja analiza AUL: kolika je količina tereta pretovarana u svakom lučkom području (Dunav, Sava, "
                    "Tisa). Luke su na karti postavljene po naselju po kome je lučko područje imenovano.",
        used_for=["Rečne luke"],
    )

    def fetch(self, force=False):
        self.download(srb.AUL_PORTS_URL, AUL_FILE, force=force, expect_binary=True)

    def process(self) -> dict:
        year, ports = ports_from_pptx((self.raw_dir / AUL_FILE).read_bytes())
        print(f"    {len(ports)} port areas, cargo of {year}")
        return {"vintage": "Agencija za upravljanje lukama: Uporedni pregled tereta pretovarenog u lučkim područjima "
                           f"sa presekom na dan 31.12.{year}. godine",
                "year": year, "ports": ports, "_files": [AUL_FILE]}


class Airports(Source):
    info = SourceInfo(
        id="airports",
        title="Aerodromi Srbije (OurAirports)",
        publisher="OurAirports",
        homepage="https://ourairports.com/data/",
        license="Javno dobro (public domain)",
        description="Veliki i srednji aerodromi u Srbiji sa ICAO oznakom, položajem i podatkom o redovnom saobraćaju.",
        used_for=["Aerodromi"],
    )

    def fetch(self, force=False):
        self.download(srb.OURAIRPORTS_URL, OURAIRPORTS_FILE, force=force)

    def process(self) -> dict:
        airports = airports_from_csv((self.raw_dir / OURAIRPORTS_FILE).read_text(encoding="utf-8"))
        print(f"    {len(airports)} airports")
        return {"vintage": "OurAirports: airports.csv", "airports": airports, "_files": [OURAIRPORTS_FILE]}


class AirportTraffic(Source):
    info = SourceInfo(
        id="airport_traffic",
        title="Putnici na aerodromima Srbije",
        publisher="Eurostat (avia_paoa); Aerodrom Morava",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/avia_paoa/default/table?lang=en",
        license="Eurostat: CC BY 4.0; Aerodrom Morava: javno objavljena statistika",
        description="Godišnji broj prevezenih putnika po aerodromima: Beograd i Niš po Eurostatu, Kraljevo po statistici "
                    "Aerodroma Morava. Teretni saobraćaj nije objavljen u mašinski čitljivom obliku.",
        used_for=["Aerodromi"],
    )

    def fetch(self, force=False):
        self.download(srb.EUROSTAT_AVIA_URL, EUROSTAT_FILE, force=force)
        self.download(srb.MORAVA_STATS_URL, MORAVA_FILE, force=force)

    def process(self) -> dict:
        eurostat = passengers_from_jsonstat(json.loads((self.raw_dir / EUROSTAT_FILE).read_text(encoding="utf-8")))
        morava = passengers_from_html((self.raw_dir / MORAVA_FILE).read_text(encoding="utf-8", errors="replace"))
        traffic: dict[str, dict[int, int | None]] = {k: dict(v) for k, v in eurostat.items()}
        if morava:
            traffic["LYKV"] = morava  # Kraljevo: the operator's own count; Eurostat carries no row for it
        years = sorted({y for s in traffic.values() for y, v in s.items() if v is not None})
        latest = years[-1] if years else None
        print(f"    passengers for {sorted(traffic)} airports, latest year {latest}")
        return {"vintage": f"Eurostat avia_paoa i Aerodrom Morava: putnici do {latest}. godine",
                "traffic": {k: {str(y): v for y, v in sorted(s.items())} for k, s in sorted(traffic.items())},
                "_files": [EUROSTAT_FILE, MORAVA_FILE]}
