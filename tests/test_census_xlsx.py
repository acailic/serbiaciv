import tempfile, unittest
from pathlib import Path

from openpyxl import Workbook

from pipeline.core import census_xlsx


def workbook(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["", "Потација", "Ukupno", "Срби", "Роми"])
    ws.append(["Рашка область", "с", "100", "90", "10"]); ws.append(["", "м", "50", "45", "5"]); ws.append(["", "ж", "50", "45", "5"])
    ws.append(["Тутин", "с", "100", "90", "10"])
    ws.append(["Тутин", "с", "100", "90", "-"]); ws.cell(row=6, column=1).alignment = census_xlsx.indent(3)
    ws.append(["Насеље", "м", "...", "", "3"]); ws.cell(row=7, column=1).alignment = census_xlsx.indent(4)
    wb.save(path)


class ReadRowsTest(unittest.TestCase):
    def test_indent_sex_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.xlsx"
            workbook(p)
            rows = census_xlsx.read_rows(p)
        self.assertEqual([(r["level"], r["sex"]) for r in rows], [(0, "t"), (0, "m"), (0, "f"), (0, "t"), (3, "t"), (4, "m")])
        self.assertEqual(rows[0]["cells"], {"Ukupno": 100, "Срби": 90, "Роми": 10})
        self.assertEqual(rows[4]["cells"], {"Ukupno": 100, "Срби": 90, "Роми": 0})  # "-" is a real zero
        self.assertEqual(rows[5]["cells"], {"Ukupno": None, "Срби": None, "Роми": 3})  # "..." and blank are missing
        self.assertIsNone(rows[1]["name"])

    def test_areas_follow_the_indent_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.xlsx"
            workbook(p)
            areas = census_xlsx.areas(census_xlsx.read_rows(p))
        self.assertEqual(len(areas), 1)
        oblast = areas[0]
        self.assertEqual((oblast["name"], oblast["level"]), ("Рашка область", 0))
        self.assertEqual(oblast["rows"]["m"]["cells"]["Ukupno"], 50)
        self.assertEqual([a["name"] for a in oblast["children"]], ["Тутин"])
        grad = oblast["children"][0]
        self.assertEqual(grad["rows"]["t"]["cells"]["Роми"], 0)


def sheet(path: Path, cells: dict, merges=(), indents=None):
    """A workbook laid out like the census ones: {row: column values} (1-based, None leaves a cell empty),
    merged header ranges and {row: indent of column A}."""
    wb = Workbook()
    ws = wb.active
    for r, values in cells.items():
        for c, v in enumerate(values, start=1):
            if v is not None:
                ws.cell(row=r, column=c, value=v)
    for rng in merges:
        ws.merge_cells(rng)
    for r, level in (indents or {}).items():
        ws.cell(row=r, column=1).alignment = census_xlsx.indent(level)
    wb.save(path)


def read(cells, merges=(), indents=None):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.xlsx"
        sheet(p, cells, merges, indents)
        return census_xlsx.read_rows(p)


class ReadRealLayoutTest(unittest.TestCase):
    """What the published workbooks do: a merged title, a stacked merged header, upper-case sex markers in the
    third column, the urban marker in the untitled second one, a row of "..." for Kosovo and a legend."""

    CELLS = {
        1: ["Становништво према старости и полу", None, None, None, None, None, None, "Population by age and sex", None, None],
        2: ["  Регион\n        Област", None, "Пол", "Укупно \nTotal", "Старост / Age", None],
        3: [None, None, None, None, "0–4", "5–9"],
        4: [None] * 6,
        5: ["РЕПУБЛИКА СРБИЈА", "", "С", 100, 60, 40],
        6: ["    ", "", "М", 50, 30, 20],
        7: ["    ", "", "Ж", 50, 30, 20],
        8: ["Суботица", "г", "С", 10, "-", "..."],
        9: ["Регион Косово и Метохија", None, "С", "...", "...", "..."],
        10: [None] * 6,
        11: ["Списак ознака:", None, None, None, None, None],
        12: ["Нема појаве", "-", None, "-", None, None],
        13: ["Не располаже се податком", "...", None, "...", None, None],
        14: ["градско насеље", "г", None, "u", None, None],
    }
    MERGES = ["A1:G1", "H1:J1", "A2:A4", "C2:C4", "D2:D4", "E2:F2"]

    def test_rows_start_after_the_header_and_end_before_the_legend(self):
        rows = read(self.CELLS, self.MERGES, {8: 2})
        self.assertEqual([(r["name"], r["sex"], r["level"], r["urban"]) for r in rows], [
            ("РЕПУБЛИКА СРБИЈА", "t", 0, False), (None, "m", 0, False), (None, "f", 0, False), ("Суботица", "t", 2, True),
        ])

    def test_titles_are_the_stacked_header_and_values_are_numbers(self):
        rows = read(self.CELLS, self.MERGES, {8: 2})
        self.assertEqual(list(rows[0]["cells"]), ["Укупно Total", "Старост / Age › 0–4", "Старост / Age › 5–9"])
        self.assertEqual(list(rows[0]["cells"].values()), [100, 60, 40])
        self.assertEqual(list(rows[3]["cells"].values()), [10, 0, None])  # "-" is 0, "..." is None


class ReadColumnsTest(unittest.TestCase):
    def test_untitled_column_is_titled_by_its_letter(self):
        rows = read({1: ["Регион", None, "Укупно"], 2: ["Србија", 7, 100]})
        self.assertEqual(rows[0]["cells"], {"B": 7, "Укупно": 100})
        self.assertIsNone(rows[0]["sex"])  # numbers, not sex markers

    def test_a_number_in_the_second_column_is_not_mistaken_for_a_sex(self):
        rows = read({1: ["Регион", "Укупно\nTotal", "Other"], 2: ["Србија", 100, 1], 3: ["Србија – Север", 50, 1]})
        self.assertEqual([(r["name"], r["sex"]) for r in rows], [("Србија", None), ("Србија – Север", None)])
        self.assertEqual(rows[1]["cells"], {"Укупно Total": 50, "Other": 1})

    def test_header_merged_over_two_columns_is_one_column(self):
        rows = read({1: ["Регион", "Пол", "Укупно\nTotal", "Непознато\nUnknown", None], 2: ["Србија", "с", 100, 7, None]},
                    ["D1:E1"])
        self.assertEqual(rows[0]["cells"], {"Укупно Total": 100, "Непознато Unknown": 7})

    def test_two_columns_with_one_title_are_an_error(self):
        with self.assertRaisesRegex(ValueError, "свега"):
            read({1: ["Регион", "Пол", "свега", "свега"], 2: ["Србија", "с", 1, 2]})

    def test_numbers_typed_as_text_are_numbers(self):
        rows = read({1: ["", "Ukupno", "Old"], 2: ["A", "100", "43.85"]})
        self.assertEqual(rows[0]["cells"], {"Ukupno": 100, "Old": 43.85})


class AreasTest(unittest.TestCase):
    def test_one_row_per_area_and_siblings_at_one_indent(self):
        rows = read({1: ["Регион", "Укупно"], 2: ["Регион", 10], 3: ["Област", 10], 4: ["Општина", 6], 5: ["Насеље", 6]},
                    indents={3: 2, 4: 2, 5: 4})
        top = census_xlsx.areas(rows)
        self.assertEqual([a["name"] for a in top], ["Регион"])
        region = top[0]
        self.assertEqual([a["name"] for a in region["children"]], ["Област", "Општина"])  # one indent: siblings
        self.assertEqual((region["children"][0]["parent"]["name"], sorted(region["children"][0]["rows"])), ("Регион", ["t"]))
        opstina = region["children"][1]
        self.assertEqual(opstina["rows"]["t"]["cells"]["Укупно"], 6)
        self.assertEqual([a["name"] for a in opstina["children"]], ["Насеље"])


if __name__ == "__main__":
    unittest.main()
