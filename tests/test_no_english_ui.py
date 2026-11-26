"""No English in the Serbian UI: every string a reader can see is Serbian Latin.

The dictionary (tests/data/english_words.txt) is every alphabetic word of the system's American English list, so an
English label does not slip through because its word also happens to be an id or a file name in the data. Serbian
words that collide with English ones are allowlisted below (ALLOWED_WORDS), one reason each, as are names of sources,
fonts, software and file formats (ALLOWED). Everything else that reads as English fails the test, with file and line.

A guard only sees what its scanner reads: text nodes of template literals, literals assigned to a display sink, the
text of index.html and the text fields of the data files. Rendered HTML (``document.body.innerText``) is the other
half of the check and is done in the browser.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ui_text  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
WORDS = ROOT / "tests" / "data" / "english_words.txt"

# Whole strings that may carry English: names of sources, software, formats, places abroad.
ALLOWED = [
    r"Natural Earth", r"OpenStreetMap", r"Copernicus", r"Eurostat", r"WorldCover", r"GLO-?30", r"Palatino",
    r"Segoe UI", r"GitHub", r"Wikidata", r"Wikipedia", r"usaciv", r"serbiaciv", r"\.zip\b", r"\.png\b", r"\.json\b",
    r"\.csv\b", r"\.pdf\b", r"\bURL\b", r"\bPNG\b", r"\bAPI\b", r"\bLAU\b", r"\bNUTS\b", r"\bOECD\b", r"\bUNESCO\b",
    r"\bEPS\b", r"\bEMS\b", r"\bAERS\b", r"\bRZS\b", r"\bGIS\b", r"\bSRTM\b", r"\bDEM\b", r"\bCORINE\b", r"\bNACE\b",
    r"\bCOG\b", r"\bCDR\b", r"\bESA\b", r"\bJRC\b", r"\bEurostat\b", r"\bEIA\b", r"\bBLS\b", r"\bBEA\b", r"\bNOAA\b",
    r"\bUSGS\b", r"\bMRLC\b", r"\bACS\b", r"\bFAF\b", r"\bQCEW\b", r"\bBDS\b", r"\bMIT\b", r"\bWASD\b", r"\bEsc\b",
    r"\bLatin\b.*\bLatin\b", r"Ctrl", r"Shift", r"Alt\b", r"Enter\b", r"Karpathy", r"Raja Koduri", r"Google",
    r"Chrome", r"Safari", r"Firefox", r"Edge\b", r"Mac\b", r"Windows", r"Linux", r"i ?Phone", r"Android", r"i ?Pad",
    r"\bOSM\b", r"\bNominatim\b", r"\bOverpass\b", r"\bGeoJSON\b", r"\bTopoJSON\b", r"\bShapefile\b", r"\bogr2ogr\b",
    r"\bGDAL\b", r"\brasterio\b", r"\bgeopandas\b", r"\bshapely\b", r"\bnumpy\b", r"\bD3\b", r"\bCanvas\b",
    r"\bWebGL\b", r"\bSVG\b", r"\bDOM\b", r"\bCSS\b", r"\bHTML\b", r"\bJS\b", r"\bJSON\b", r"\bHTTP\b", r"\bHTTPS\b",
    r"\bCDN\b", r"\bLFS\b", r"\bCI\b", r"\bGitHub Pages\b", r"\bVercel\b", r"\bNode\b", r"\bTypeScript\b",
    # Names in the data: Nikola Tesla, the mountain Tara, Felix Romuliana, "the Gibraltar of the Danube", the river Sava.
    r"\bTesla\b", r"\bTara\b", r"\bFelix\b", r"\bGibraltar\b", r"\bSave\b",
    r"\bHE\b",  # hidroelektrana, as a plant's name begins: HE Đerdap 1
    # The branches of upstream's military layer, named only if that layer is ever shipped: Serbia has no such data.
    r"^(Army|Navy|Air Force & Space Force|Marine Corps|Army National Guard|Air National Guard|Reserve|Defense agency)$",
]
ALLOWED_RE = [re.compile(p) for p in ALLOWED]
# Words that are English and Serbian at once, so the dictionary cannot tell them apart.
ALLOWED_WORDS = {
    # units and abbreviations: godina (t/god), hektar, kilometar, megabajt, broj, na primer, Republika Srbija
    "god", "ha", "km", "mb", "br", "npr", "rs",
    # the same international word: master studije, film, sport, filter, histogram, logaritamska skala (log X), minimum, period
    "master", "film", "sport", "filter", "histogram", "log", "minimum", "period",
    # Serbian words the English list happens to contain
    "cara",  # genitive of car
    "robe",  # genitive of roba (promet robe)
    "figure",  # plural of figura
    "nafta", "gas", "auto",  # nafta i gas, auto-putevi
    "grad", "luke", "red", "rang", "mere", "minus", "pet", "put", "van", "sad", "led",  # Novi Sad; led i sneg
    "po", "na", "od", "da", "ne", "se", "pa", "do", "pod", "ali", "bi", "ni", "ono", "ova", "to", "pored", "gusto", "traci",
    "vera",  # vera i narodnost
    "ko",  # ko radi
    "tog", "ga",  # svaki heks tog okruga; godinu u kojoj ga ima
    "park", "primer",  # nacionalni park; na primer
    "suva",  # Suva Reka, opština na Kosovu i Metohiji, u napomeni o Šar-planini
    "mil",  # mil. = milion; hilj. = hiljada
}


def offending(text: str, dictionary: frozenset[str]) -> list[str]:
    if any(r.search(text) for r in ALLOWED_RE):
        return []
    return sorted({w for w in ui_text.words(text) if w in dictionary and w not in ALLOWED_WORDS})


def find_violations(web: pathlib.Path = WEB, dictionary=None):
    dictionary = dictionary or ui_text.load_wordlist(WORDS)
    out = []
    for f in ui_text.js_files(web):
        for line, text in ui_text.display_strings(f.read_text(encoding="utf-8")):
            hits = offending(text, dictionary)
            if hits:
                out.append((f.relative_to(ROOT).as_posix(), line, text, hits))
    for line, text in ui_text.html_strings((web / "index.html").read_text(encoding="utf-8")):
        hits = offending(text, dictionary)
        if hits:
            out.append(("web/index.html", line, text, hits))
    return out


TEXT_KEYS = {"name", "title", "label", "description", "desc", "summary", "note", "text", "tip", "hint",
             "tooltip", "caption", "unit", "legend", "long", "short", "headline", "sub", "body"}  # not "rule": that is an id


def find_data_violations(web: pathlib.Path = WEB, dictionary=None):
    """Text fields of the data files (names, rules, notes): the Almanac reads them out."""
    dictionary = dictionary or ui_text.load_wordlist(WORDS)

    def walk(v, path, out, f, skip=()):
        if isinstance(v, dict):
            for k, x in v.items():
                # A "rules" object (infrastructure.json) holds its paragraphs directly: roads, rail, ports, airports.
                if isinstance(x, str) and (k in TEXT_KEYS or path[-1:] == ["rules"]) and k not in skip:
                    hits = offending(x, dictionary)
                    if hits:
                        out.append((f, 0, f"{'/'.join(map(str, path))}.{k}: {x[:80]}", hits))
                else:
                    walk(x, path + [k], out, f, skip)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, path + [i], out, f, skip)

    out = []
    # Place names (opštine, rivers, towns of Kosovo and Metohija) come from the gazetteers and are not UI prose:
    # Bela Palanka, Mali Zvornik, Ada and Dunav/Dunărea are Serbian and Romanian, whatever the English list says.
    GAZETTEER = {"world.json": ("name",), "kim_towns.json": ("name",)}
    for f in sorted((web / "data").glob("*.json")):
        rel = f.relative_to(ROOT).as_posix()
        walk(json.loads(f.read_text(encoding="utf-8")), [], out, rel, GAZETTEER.get(f.name, ()))
    return out


class NoEnglishUiTest(unittest.TestCase):
    maxDiff = None

    def test_web_js_and_index_html_carry_no_english(self):
        violations = find_violations()
        self.assertEqual([], [f"{f}:{line} {t!r} <- {h}" for f, line, t, h in violations])

    def test_data_text_fields_carry_no_english(self):
        violations = find_data_violations()
        self.assertEqual([], [f"{f} {t!r} <- {h}" for f, _, t, h in violations])


if __name__ == "__main__":
    unittest.main()
