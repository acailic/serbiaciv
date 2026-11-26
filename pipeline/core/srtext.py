"""Serbian script helpers: Latin ↔ Cyrillic transliteration and a search key.

Serbian is written in both scripts with one letter for each sound, so the conversion is mechanical. Everything in
this project is authored in Serbian Latin; Cyrillic is generated from it. web/js/i18n/transliterate.js mirrors the
two tables and PROTECTED token for token (tests/test_srtext.py checks that they agree).
"""

from __future__ import annotations

import re
import unicodedata

# Latin → Cyrillic. Digraphs first, so "lj", "nj" and "dž" never split into two letters.
_L2C_DIGRAPHS = (("DŽ", "Џ"), ("Dž", "Џ"), ("dž", "џ"), ("LJ", "Љ"), ("Lj", "Љ"), ("lj", "љ"), ("NJ", "Њ"), ("Nj", "Њ"), ("nj", "њ"))
_L2C = str.maketrans({
    "a": "а", "b": "б", "c": "ц", "č": "ч", "ć": "ћ", "d": "д", "đ": "ђ", "e": "е", "f": "ф", "g": "г", "h": "х",
    "i": "и", "j": "ј", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "š": "ш",
    "t": "т", "u": "у", "v": "в", "z": "з", "ž": "ж",
    "A": "А", "B": "Б", "C": "Ц", "Č": "Ч", "Ć": "Ћ", "D": "Д", "Đ": "Ђ", "E": "Е", "F": "Ф", "G": "Г", "H": "Х",
    "I": "И", "J": "Ј", "K": "К", "L": "Л", "M": "М", "N": "Н", "O": "О", "P": "П", "R": "Р", "S": "С", "Š": "Ш",
    "T": "Т", "U": "У", "V": "В", "Z": "З", "Ž": "Ж",
})

# Cyrillic → Latin, one letter at a time. The three Cyrillic digraph letters are handled per word (see to_latin).
_C2L = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "ć", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "č", "ш": "š",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
    "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "Ћ": "Ć", "У": "U",
    "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Ш": "Š",
})
# lower-case letter → Latin digraph; upper-case letter → (mixed-case, all-caps) digraph
_C2L_DIGRAPHS: dict[str, object] = {"љ": "lj", "њ": "nj", "џ": "dž", "Љ": ("Lj", "LJ"), "Њ": ("Nj", "NJ"), "Џ": ("Dž", "DŽ")}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)  # a run of letters, any script

# Names written in Latin in both scripts: foreign publishers, products and acronyms. Matched as whole words.
PROTECTED = (
    "AWS", "COG", "Copernicus", "ESA", "ESA WorldCover", "Eurostat", "GISCO", "GLO-30", "GeoJSON", "GitHub", "NACE",
    "Natural Earth", "OpenStreetMap", "OurAirports", "Overpass", "UNESCO", "USGS", "Wikidata", "WRI", "geoBoundaries",
)
_PROTECT_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(t) for t in sorted(PROTECTED, key=len, reverse=True)) + r")(?![A-Za-z])"
)


def to_cyrillic(text: str) -> str:
    """Serbian Latin → Cyrillic. Protected names stay Latin. Other scripts pass through untouched."""
    if not text:
        return text
    out = []
    for k, part in enumerate(_PROTECT_RE.split(str(text))):
        if k % 2:
            out.append(part)
            continue
        for latin, cyrillic in _L2C_DIGRAPHS:
            part = part.replace(latin, cyrillic)
        out.append(part.translate(_L2C))
    return "".join(out)


def to_latin(text: str) -> str:
    """Serbian Cyrillic → Latin. A word set entirely in capitals gets capital digraphs (ЉУБАВ → LJUBAV)."""
    if not text:
        return text
    text = str(text)
    out, pos = [], 0
    for m in _WORD.finditer(text):
        out.append(text[pos:m.start()])
        word = m.group(0)
        if any(ch in _C2L_DIGRAPHS or ord(ch) in _C2L for ch in word):
            caps = word.isupper() and len(word) > 1
            out.append("".join(
                (_C2L_DIGRAPHS[ch][caps] if isinstance(_C2L_DIGRAPHS[ch], tuple) else _C2L_DIGRAPHS[ch])
                if ch in _C2L_DIGRAPHS else ch.translate(_C2L) for ch in word))
        else:
            out.append(word)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def fold_key(text) -> str:
    """One search key for both scripts and for typed text without diacritics: lowercase ASCII letters and digits."""
    if text is None:
        return ""
    latin = to_latin(str(text)).replace("đ", "dj").replace("Đ", "Dj")
    folded = unicodedata.normalize("NFD", latin)
    ascii_ = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_.lower()).split())


def okrug_name(oblast_name: str) -> str:
    """"Nišavska oblast" → "Nišavski okrug": the everyday name of the unit RZS and Eurostat call an oblast."""
    stem = re.sub(r"\s+oblast$", "", oblast_name.strip())
    return (stem[:-1] if stem.endswith("a") else stem) + "i okrug"
