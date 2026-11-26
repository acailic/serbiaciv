"""Scanner used by test_no_english_ui.py to find the strings a reader can see in the web app.

A display string is either a text node of an HTML template literal (``<span>Pretraga</span>``) or a string literal
that is handed to a display sink (``el.textContent = "..."``, ``el.title = "..."``, ``{ label: "..." }``,
``toast("...")``). Interpolations ``${...}`` are blanked first, and literals that are identifiers (snake_case,
kebab-case, selectors) do not count. Comments are skipped: code comments are written in English on purpose.
"""
from __future__ import annotations

import pathlib
import re

EXPR = re.compile(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
SINK = (
    r"(?:textContent|innerText|title|placeholder|alt|label|text|message|msg|toast|status|caption|heading|name|"
    r"description|desc|tooltip|hint|sub|note|body|header|footer|summary|rule|tip|unit|legend|ariaLabel"
    r")\s*[:=]\s*$"
)
CALL = r"(?:toast|setStatus|announce|showToast|alert|confirm|setAttribute)\s*\(\s*(?:\"[a-z-]+\",|'[a-z-]+',)?\s*$"
# A literal after ``||`` or ``??`` is what a reader sees when the real value is missing: `?.name || "State"`.
FALLBACK = r"(?:\|\||\?\?)\s*$"
HTML_ATTR = re.compile(r"""\b(?:title|aria-label|alt|placeholder|aria-description|aria-roledescription)="([^"]*)\"""")


def literals(src: str):
    """Yield (line, quote, text, before) for every string/template literal outside comments."""
    out = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i)
            if j < 0:
                break
            line += src.count("\n", i, j)
            i = j + 2
        elif c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                j += 1
            out.append((line, c, src[i + 1:j], src[max(0, i - 120):i]))
            line += src.count("\n", i, j)
            i = j + 1
        else:
            i += 1
    return out


def readable(body: str) -> bool:
    """A literal a person could read: words with spaces, or one capitalised word (never an identifier)."""
    b = body.strip()
    if not b or re.fullmatch(r"[a-z0-9_\-:.#/]+", b):
        return False
    if re.search(r"[{};=<>]|://|@\x00|^\x00?$", b):
        return False
    return " " in b or bool(re.fullmatch(r"[A-ZÀ-ÖØ-ÞČĆĐŠŽ][A-Za-zÀ-ÖØ-öø-ÿČĆĐŠŽčćđšž]+", b))


def display_strings(src: str):
    """Yield (line, text) for every string a reader can see in a JS module."""
    seen = set()
    for line, quote, text, before in literals(src):
        body = EXPR.sub("\x00", text)
        if quote == "`":
            for m in re.finditer(r">([^<>`]+)<", body):
                t = " ".join(m.group(1).replace("\x00", " ").split())
                if t and (line, t) not in seen:
                    seen.add((line, t))
                    yield line, t
        if readable(body) and (re.search(SINK, before) or re.search(CALL, before) or re.search(FALLBACK, before)):
            t = " ".join(body.replace("\x00", " ").split())
            if (line, t) not in seen:
                seen.add((line, t))
                yield line, t


def html_strings(src: str):
    """Yield (line, text) for the text nodes and labelled attributes of index.html."""
    for m in re.finditer(r">([^<>]+)<", src):
        t = " ".join(m.group(1).split())
        if t:
            yield src.count("\n", 0, m.start()) + 1, t
    for m in HTML_ATTR.finditer(src):
        t = " ".join(m.group(1).split())
        if t:
            yield src.count("\n", 0, m.start()) + 1, t


def js_files(web: pathlib.Path):
    for f in sorted((web / "js").rglob("*.js")):
        if not f.name.endswith(".test.js"):
            yield f


WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿČĆĐŠŽčćđšž]+")


def words(text: str):
    return [w.lower() for w in WORD.findall(text)]


def load_wordlist(path: pathlib.Path) -> frozenset[str]:
    """One word per line; lines that start with # are prose."""
    return frozenset(w for line in path.read_text(encoding="utf-8").splitlines()
                     for w in line.split() if w and not line.startswith("#"))
