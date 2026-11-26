"""Reader for the Excel tables of Popis 2022, the 2022 census published by RZS.

Every table is one worksheet with the same anatomy: a merged title, a header of one to three stacked rows, and
then the areas in a fixed order (the country, its halves, the regions, and inside each region its oblasti with
their opštine, gradske opštine and, in the two settlement tables, the settlements). An area has one row (the
tables without sex) or three (``с`` both sexes, ``м`` men, ``ж`` women), and only the first row carries the name.

How deep an area sits in that order is read from the indent of column A, which the tables do not use
consistently (an oblast and its opštine often share an indent). The source that joins these rows to the
territory tree therefore goes by name and row order; read_rows only reports the indent as ``level``.
"""

from __future__ import annotations

import math

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

MAX_LEVEL = 4  # the deepest indent the hierarchy uses: a settlement
TITLE_SEP = " › "  # joins the stacked header cells of one column: "Економски неактивни › свега"
URBAN_MARKER = "г"  # printed next to an urban settlement ("gradsko naselje") in the untitled column by the name
_SEX = {"с": "t", "м": "m", "ж": "f"}


def indent(level: int) -> Alignment:
    """The alignment that puts a row `level` steps deep in the hierarchy (what read_rows returns as "level")."""
    return Alignment(indent=level)


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value):
    """The number a cell holds (cells typed by hand often keep theirs as text), None for any other cell."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except ValueError:
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None


def _value(value):
    """One cell as read_rows reports it: a number, 0 for "-" (the office prints it for "none"), None for
    everything else ("...", blank, text)."""
    return 0 if isinstance(value, str) and value.strip() == "-" else _number(value)


def _sex(value) -> str | None:
    return _SEX.get(value.strip().lower()) if isinstance(value, str) else None


def _line(value) -> str:
    """A header cell on one line: each run of whitespace, the line break between the Cyrillic and the English
    title included, becomes one space."""
    return " ".join(str(value).split())


def _merged(sheet) -> tuple[dict, set]:
    """(covered, titles): `covered` maps the cells a merged range hides to the range's first cell, `titles` is
    the set of first cells of ranges that span more than one column (the merged title above the header)."""
    covered, titles = {}, set()
    for rng in sheet.merged_cells.ranges:
        first = (rng.min_row - 1, rng.min_col - 1)
        if rng.max_col > rng.min_col:
            titles.add(first)
        for r in range(rng.min_row - 1, rng.max_row):
            for c in range(rng.min_col - 1, rng.max_col):
                if (r, c) != first:
                    covered[(r, c)] = first
    return covered, titles


def _header(grid: list[list], covered: dict, merged_titles: set) -> tuple[int, dict]:
    """(first data row, {column: [header texts]}).

    The header row is the first row that is neither blank nor a merged title; the header runs to the first row
    that holds a number. A column's header texts are its non-blank cells from the header row down, so a column
    under a merged group cell ("Економски неактивни") is titled with that group first. A column whose deepest
    header cell belongs to a range that starts further left ("Непознато", merged over two columns) has no title
    of its own and is left out.
    """
    header = next(r for r, row in enumerate(grid)
                  if not all(_blank(v) or (r, c) in merged_titles for c, v in enumerate(row)))
    first_data = next(r for r in range(header + 1, len(grid)) if any(_number(v) is not None for v in grid[r]))
    paths = {}
    for c in range(1, len(grid[header])):
        path, deepest = [], None
        for r in range(header, first_data):
            v = grid[r][c]
            if v is None and (r, c) in covered:  # a merged cell shows the text of the range's first cell
                first_row, first_col = covered[(r, c)]
                v = grid[first_row][first_col]
            if _blank(v):
                continue
            deepest = (r, c)
            if not path or path[-1] != _line(v):
                path.append(_line(v))
        if deepest is not None and covered.get(deepest, deepest)[1] == c:
            paths[c] = path
    return first_data, paths


def _sex_column(grid: list[list], first_data: int, last: int, paths: dict) -> int | None:
    """The column headed ``Пол`` or, where no column is, the first whose data cells are all sex markers."""
    headed = next((c for c, p in paths.items() if p[-1] == "Пол"), None)
    if headed is not None:
        return headed
    data = range(first_data, last + 1)
    return next((c for c in range(1, len(grid[first_data]))
                 if any(_sex(grid[r][c]) for r in data) and all(_sex(grid[r][c]) or _blank(grid[r][c]) for r in data)),
                None)


def read_rows(path) -> list[dict]:
    """The data rows of the workbook's first sheet, in sheet order, as
    ``dict(level, name, sex, urban, cells)``.

    level  the indent of column A (0 … MAX_LEVEL for areas of the hierarchy)
    name   the text of column A, None on the rows that continue an area
    sex    "t" (``с``), "m" (``м``) or "f" (``ж``); None where the sheet has no sex column or the cell is empty
    urban  True when the row carries the office's marker of an urban settlement
    cells  {column title: number | None}: every column except the name and the sex column that holds a number
           somewhere in the sheet, None where the cell has none. A title is the column's header ("Укупно Total",
           "Економски неактивни › свега"); a column without a header, such as the one with the urban marker,
           is titled by its spreadsheet letter.

    Rows below the last cell that holds a number are not read: they are the sheet's legend ("Списак ознака:").
    """
    wb = load_workbook(path, read_only=False, data_only=True)
    try:
        sheet = wb.worksheets[0]
        grid = [list(row) for row in sheet.iter_rows(values_only=True)]
        indents = {cell.row: cell.alignment.indent for cell in sheet["A"]}
        covered, merged_titles = _merged(sheet)
        first_data, paths = _header(grid, covered, merged_titles)
        last = max(r for r in range(first_data, len(grid)) if any(_number(v) is not None for v in grid[r]))
        sex_col = _sex_column(grid, first_data, last, paths)
        marker_col = 1 if 1 not in paths and sex_col != 1 else None

        rows, used = [], set()
        for r in range(first_data, last + 1):
            name = grid[r][0]
            sex = _sex(grid[r][sex_col]) if sex_col is not None else None
            cells = {c: v for c in range(1, len(grid[r])) if c != sex_col and (v := _value(grid[r][c])) is not None}
            if _blank(name) and sex is None and not cells:
                continue  # a blank row
            used.update(cells)
            rows.append((r, None if _blank(name) else name, sex, cells))

        titles = {c: TITLE_SEP.join(paths[c]) if c in paths else get_column_letter(c + 1) for c in used}
        duplicates = sorted(t for t in titles.values() if list(titles.values()).count(t) > 1)
        if duplicates:
            raise ValueError(f"{path}: columns share a title: {duplicates}")
        return [{
            "level": int(indents.get(r + 1) or 0),
            "name": name,
            "sex": sex,
            "urban": marker_col is not None and grid[r][marker_col] == URBAN_MARKER,
            "cells": {titles[c]: cells.get(c) for c in sorted(used)},
        } for r, name, sex, cells in rows]
    finally:
        wb.close()


def areas(rows: list[dict]) -> list[dict]:
    """The rows grouped into the areas they describe, nested by walking the indent stack:
    ``dict(name, level, parent=<Area | None>, rows={"m": Row, "f": Row, "t": Row | None}, children=[Area])``.

    An area's first row carries its name; the rows that follow leave it blank or repeat it and differ only in
    the sex. A row without a sex (the tables that have one row per area) is the area's "t" row.
    """
    grouped = []
    for row in rows:
        name = row["name"]
        if name is None and not grouped:
            continue
        if name is None or (grouped and name == grouped[-1]["name"]):
            area = grouped[-1]
            if name is not None:  # the name repeated at another depth moves the area there
                area["level"] = row["level"]
        else:
            area = {"name": name, "level": row["level"], "parent": None, "rows": {}, "children": []}
            grouped.append(area)
        area["rows"][row["sex"] or "t"] = row

    top, stack = [], []
    for area in grouped:
        while stack and stack[-1]["level"] >= area["level"]:
            stack.pop()
        area["parent"] = stack[-1] if stack else None
        (stack[-1]["children"] if stack else top).append(area)
        stack.append(area)
    return top
