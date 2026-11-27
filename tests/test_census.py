"""The census source on workbooks laid out like the published ones, with their real column titles.

The synthetic census covers three oblasti: Belgrade's (whose one row stands for Grad Beograd), Južnobačka (Grad
Novi Sad, which the census labels by the bare city name) and Nišavska (Grad Niš with two of its gradske opštine,
one of them a Palilula too, and one plain opština). Every area has a population that is a multiple of 2000; a
column holds a fixed share of it (in per mille), the men's and women's rows two and three fifths. "Градска" and
"Остала" split every area, as in the published tables.
"""

import http.server
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook, load_workbook

from pipeline.core import census_xlsx, fetch, srb, source, territory
from pipeline.sources import census
from pipeline.sources.census import Census

TOTAL = "Укупно Total"
ACTIVE = "Економски активни / Economically active"
INACTIVE = "Економски неактивни / Economically inactive"
CHRISTIAN = "Хришћанска / Christian"
SECONDARY = "Средње образовање Secondary education"
VOCATIONAL = f"{SECONDARY} › средње стручне школе у трајању Secondary vocational schools"
WORKERS = ("Економски активно становништво које обавља занимање "
           "Economically active population performing an occupation")
SAME_AREA = f"{WORKERS} › у истој области within the same area"
MIGRANTS = "Досељено становништво Migrant population"
FROM_SERBIA = f"{MIGRANTS} › са подручја Републике Србије, и то: within the Republic of Serbia, of which:"
FROM_ABROAD = f"{MIGRANTS} › из иностранства, и то: from abroad, of which:"

AGE_GROUPS = ("0–4", "5–9", "10–14", "15–19", "20–24", "25–29", "30–34", "35–39", "40–44", "45–49", "50–54", "55–59",
              "60–64", "65–69", "70–74", "75–79", "80–84", "85 и више 85 and over")
AGE = [f"Старост / Age › {g}" for g in AGE_GROUPS]

ETHNICITY = ["Срби Serbs", "Aлбанци Albanians", "Бошњаци Bosniaks", "Бугари Bulgarians", "Буњевци Bunjevci", "Власи Vlachs",
             "Горанци Goranci", "Југословени Yugoslavs", "Мађари Hungarians", "Македонци Macedonians", "Муслимани Muslims",
             "Немци Germans", "Роми Roma people", "Румуни Romanians", "Руси Russians", "Русини Ruthenians",
             "Словаци Slovaks", "Словенци Slovenians", "Украјинци Ukrainians", "Хрвати Croats", "Црногорци Montenegrins",
             "Остали Other", "Регионалнa припадност Regional affiliation", "Нису се изјаснили Did not declare", "Непознато Unknown"]
ETHNIC_KEYS = ["srbi", "albanci", "bosnjaci", "bugari", "bunjevci", "vlasi", "goranci", "jugosloveni", "madjari", "makedonci",
               "muslimani", "nemci", "romi", "rumuni", "rusi", "rusini", "slovaci", "slovenci", "ukrajinci", "hrvati",
               "crnogorci", "ostali", "regionalna_pripadnost", "nisu_se_izjasnili", "nepoznato"]

NACE = ["Пољопривреда, шумарство и рибарство Agriculture, forestry and fishing", "Рударство Mining and quarrying",
        "Прерађивачка индустрија Manufacturing",
        "Снабдевање електричном енергијом, гасом, паром и климатизација Electricity, gas, steam and air conditioning supply",
        "Грађевинарство Construction", "Трговина на велико и трговина на мало; поправка моторних возила и мотоцикала "
        "Wholesale and retail trade and repair of motor vehicles and motorcycles",
        "Саобраћај и складиштење Transportation and storage",
        "Услуге смештаја и исхране Accommodation and food service activities",
        "Информисање и комуникације Information and communication",
        "Финансијске делатности и делатност осигурања Financial and insurance activities",
        "Пословање некретнинама Real estate acitivities",
        "Стручне, научне, иновационе и техничке делатности Professional, scientific and technical activities",
        "Административне и помоћне услужне делатности Administrative and support service activities",
        "Државна управа и одбрана; обавезно социјално осигурање Public administration and defence; compulsory social security",
        "Образовање Education", "Здравствена и социјална заштита Human health and social work activities",
        "Уметност; забава и рекреација Arts, entertainment and recreation",
        "Остале услужне делатности Other service activities",
        "Делатност домаћинства као послодавца; делатност домаћинстава која производе робу и услуге за сопствене потребе "
        "Activities of households as employers of domestic personnel; undifferentiated goods- and services-producing "
        "activities of households for own use",
        "Делатност екстериторијалних организација и тела Activities of extraterritorial organisations and bodies"]

# table → (columns as (title, share of the area's population in per mille; 0 prints as "-"), the sex markers of
# the three rows, "" for the tables without sex)
TABLES = {
    "settlement_population": ([(TOTAL, 1000)], ""),
    "settlement_age_sex": ([(TOTAL, 1000)] + list(zip(AGE, [40] * 16 + [160, 200])), "СМЖ"),
    "municipality_age_sex": ([(TOTAL, 1000)] + list(zip(AGE, [40] * 16 + [160, 200])), "СМЖ"),
    "ethnicity": ([(TOTAL, 1000), (ETHNICITY[0], 760)] + [(t, 10) for t in ETHNICITY[1:]], "СМЖ"),
    "religion": ([(TOTAL, 1000), (f"{CHRISTIAN} › cвега All", 840), (f"{CHRISTIAN} › православна Orthodox", 800),
                  (f"{CHRISTIAN} › католичка Catholic", 20), (f"{CHRISTIAN} › протестантска Protestant", 10),
                  (f"{CHRISTIAN} › остале хришћанске Other Christian", 10), ("Исламска Islam", 110),
                  ("Јудаистичка Judaism", 10), ("Источњачке вероисповести Eastern religions", 10),
                  ("Остале вероисповести Otherreligions", 10), ("Агностици Agnostics", 10),
                  ("Нису верници (атеисти) Not believers (atheists)", 10),
                  ("Нису се изјаснили Did not declare", 0), ("Непознато Unknown", 10)], "смж"),
    "education": ([(TOTAL, 800), ("Без школске спреме Without educational attainment", 20),
                   ("Непотпуно основно образовање Incomplete primary education", 50),
                   ("Основно образовање Primary education", 200), (f"{SECONDARY} › свега Аll", 300),
                   (f"{SECONDARY} › гимназија Gymnasium", 80),
                   (f"{VOCATIONAL} › краћем од 4 године Shorter than 4 years", 60), (f"{VOCATIONAL} › 4 године 4 years", 140),
                   (f"{SECONDARY} › специјализација после средњег образовања Specialisation after secondary education", 20),
                   ("Више образовање High education", 50), ("Високо образовање Higher education", 170),
                   ("Непознато Unknown", 10)], "СМЖ"),
    "activity": ([(TOTAL, 1000), (f"{ACTIVE} › свега all", 450), (f"{ACTIVE} › обављају занимање perform occupation", 400),
                  (f"{ACTIVE} › незапослени / unemployed", 50), (f"{INACTIVE} › свега all", 550),
                  (f"{INACTIVE} › деца млађа од 15 година children less than 15 years", 200)], "смж"),
    "industry": ([(TOTAL, 400), (NACE[0], 100)] + [(t, 14) for t in NACE[1:]] + [("Непознато Unknown", 20)], "смж"),
    "commute": ([(f"{WORKERS} › укупно total", 400), (f"{SAME_AREA} › у оквиру исте општине within the same municipality", 200),
                 (f"{SAME_AREA} › у другој општини in another municipality", 80),
                 (f"{WORKERS} › у другој области in another area", 100),
                 (f"{WORKERS} › у страној држави in the foreign country", 20)], "смж"),
    "migration": ([(TOTAL, 1000), ("Од рођења станује у истом насељу Lives in the same settlement since birth", 550),
                   (f"{MIGRANTS} › укупно total", 450), (f"{FROM_SERBIA} › свега all", 350),
                   (f"{FROM_SERBIA} › из друге области from another area", 200), (f"{FROM_ABROAD} › свега all", 100)], ""),
}

# (label, indent, population, unit id) of every area, in the order the census prints them
AREAS = [
    ("РЕПУБЛИКА СРБИЈА", 0, 56000, None),
    ("СРБИЈА – СЕВЕР", 0, 32000, None),
    ("Београдски регион", 0, 12000, None),
    ("Београдска област (Град Београд)", 2, 12000, None),
    ("Палилула", 2, 12000, "70203"),
    ("Регион Војводине", 0, 20000, None),
    ("Јужнобачка област", 2, 20000, None),
    ("Нови Сад", 2, 20000, "89010"),
    ("СРБИЈА – ЈУГ", 0, 24000, None),
    ("Регион Јужне и Источне Србије", 0, 24000, None),
    ("Нишавска област", 2, 24000, None),
    ("Град Ниш", 2, 14000, "79022"),
    ("Медијана", 3, 8000, "71331"),
    ("Палилула", 3, 6000, "71323"),
    ("Алексинац", 2, 10000, "70025"),
]
KOSOVO = ("Регион Косово и Метохија", 0, None, None)  # the census prints "..." for the region it did not enumerate
# the settlements the two settlement tables print under a unit: (unit id, label, population, urban)
SETTLEMENTS = [
    ("70203", "Борча", 2000, False),
    ("70203", "Београд (Палилула)", 10000, True),
    ("89010", "Нови Сад", 16000, True),
    ("89010", "Футог", 4000, False),
    ("71331", "Брзи Брод", 2000, False),
    ("71331", "Ниш (Медијана)", 6000, True),
    ("71323", "Чокот", 2000, False),
    ("71323", "Ниш (Палилула)", 4000, True),
    ("70025", "Алексинац", 7000, True),
    ("70025", "Врћеновица", 1000, False),
    ("70025", "Добро Село", 2000, False),  # no settlement of that name in the territory list
]
MISSING = ("ethnicity", "Медијана", "Aлбанци Albanians")  # the one cell the office prints "..." for


def _cells(key, label, n):
    values = []
    for title, share in TABLES[key][0]:
        if n is None or (key, label, title) == MISSING:
            values.append("...")
        elif share == 0:
            values.append("-")
        else:
            values.append(n * share // 1000)
    return values


def write_workbooks(raw: Path, skip=(), twice=()):
    """The ten workbooks where fetch() downloads them. `skip` leaves out the rows of (table, label); `twice`
    writes them twice."""
    for key, (columns, markers) in TABLES.items():
        settlement_table = key.startswith("settlement_")
        wb = Workbook()
        ws = wb.active
        ws.append([f"Наслов {key}"] + [None] * (len(columns) + 2))
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns) + 3)
        # column A names the areas, the settlement tables keep the urban marker in an untitled column B
        ws.append(["Регион\n      Област\n      Град – општина"] + [None] * settlement_table + ["Пол"] * bool(markers)
                  + [title for title, _ in columns])

        def row(label, level, marker, sex, values):
            cells = [label] + ["г" if marker else ""] * settlement_table + [sex] * bool(markers) + values
            r = ws.max_row + 1
            for c, v in enumerate(cells, start=1):
                if v is not None:
                    ws.cell(row=r, column=c, value=v)
            if level is not None:
                ws.cell(row=r, column=1).alignment = census_xlsx.indent(level)

        def area(label, level, n, marker=False):
            if (key, label) in skip:
                return
            for _ in range(2 if (key, label) in twice else 1):
                parts = (n, n * 2 // 5, n * 3 // 5) if markers and n is not None else (n,)
                for k, part in enumerate(parts):  # the first row names the area, the others leave A blank
                    row(label if k == 0 else " ", level if k == 0 else None, marker, markers[k] if markers else None,
                        _cells(key, label, part))

        for label, level, n, unit in [*AREAS, KOSOVO]:
            area(label, level, n)
            if n is None:
                continue
            area("Градска", 1, n // 2)
            area("Остала", 1, n // 2)
            if key == "activity":  # the age rows that follow every area's three
                for k, letter in enumerate(markers):
                    row("15-19" if k == 0 else " ", 7 if k == 0 else None, False, letter, _cells(key, "15-19", n // 50))
            if settlement_table:
                for owner, name, population, urban in SETTLEMENTS:
                    if owner == unit:
                        area(name, 4, population, urban)
        dest = raw / "census" / srb.CENSUS_FILES[key][1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        wb.save(dest)


class CensusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.raw = Path(cls.tmp.name)
        write_workbooks(cls.raw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self._live_in(self.raw)
        self.data = Census().process()
        self.units = self.data["units"]

    def _live_in(self, raw):
        """Make the source find its workbooks under `raw` (Source.raw_dir and core.fetch keep their own RAW)."""
        for p in (mock.patch.object(fetch, "RAW", raw), mock.patch.object(source, "RAW", raw)):
            p.start()
            self.addCleanup(p.stop)

    def _process(self, **changes):
        """process() on a second synthetic census, written with `changes` (see write_workbooks)."""
        with tempfile.TemporaryDirectory() as tmp:
            write_workbooks(Path(tmp), **changes)
            self._live_in(Path(tmp))
            return Census().process()

    def test_info(self):
        info = Census.info
        self.assertEqual((info.id, info.publisher, info.homepage),
                         ("census", "Republički zavod za statistiku", "https://popis2022.stat.gov.rs/"))
        self.assertEqual(self.data["vintage"], info.title)

    def test_the_interim_lists_the_files_it_read(self):
        self.assertEqual(sorted(self.data), ["_files", "settlements", "units", "vintage"])
        self.assertEqual(sorted(self.data["_files"]), sorted(srb.CENSUS_FILES[k][1] for k in census.FETCH_TABLES))

    def test_units_and_their_kinds(self):
        self.assertEqual(sorted(self.units), ["70025", "70203", "71323", "71331", "79014", "79022", "89010"])
        self.assertEqual({k: u["kind"] for k, u in self.units.items()}, {
            "70025": "opstina", "70203": "gradska_opstina", "71323": "gradska_opstina", "71331": "gradska_opstina",
            "79014": "beograd", "79022": "grad", "89010": "grad"})
        self.assertEqual((self.units["79022"]["name"], self.units["79022"]["oblast"]), ("Grad Niš", "RS225"))
        self.assertEqual(self.units["89010"]["name"], "Grad Novi Sad")
        self.assertTrue(all(u["households"] is None for u in self.units.values()))

    def test_values_come_from_the_rows_with_both_sexes(self):
        self.assertEqual(self.units["71331"]["population"], 8000)  # not 3200 or 4800
        ethnic = self.units["71331"]["ethnicity"]
        self.assertEqual(list(ethnic), ["total", *ETHNIC_KEYS])
        self.assertEqual(ethnic, {"total": 8000, "srbi": 6080, "albanci": None, **dict.fromkeys(ETHNIC_KEYS[2:], 80)})
        leaves = ["70025", "70203", "71323", "71331", "89010"]  # the units that are not the sum of other units
        self.assertEqual(sum(self.units[u]["ethnicity"]["total"] for u in leaves), 56000)  # the country's row
        self.assertEqual(sum(self.units[u]["age"]["m"][0] for u in leaves), 896)  # 40% of 4% of 56,000
        self.assertEqual(sum(self.units[u]["age"]["t"][0] for u in leaves), 2240)  # 4% of 56,000

    def test_age_by_sex(self):
        age = self.units["71331"]["age"]
        self.assertEqual(list(age), ["m", "f", "t"])
        self.assertEqual([len(a) for a in age.values()], [18, 18, 18])
        self.assertEqual((age["t"][0], age["m"][0], age["f"][0], age["t"][-1]), (320, 128, 192, 1600))

    def test_education_religion_and_activity(self):
        u = self.units["71331"]
        self.assertEqual(u["education"], {"total15": 6400, "none": 160, "incomplete_primary": 400, "primary": 1600,
                                          "secondary": 2400, "higher": 1760, "unknown": 80})
        self.assertEqual(u["religion"], {"total": 8000, "orthodox": 6400, "catholic": 160, "protestant": 80,
                                         "other_christian": 80, "muslim": 880, "jewish": 80, "eastern": 80, "other": 80,
                                         "agnostic": 80, "nonbeliever": 80, "undeclared": 0, "unknown": 80})
        self.assertEqual(u["activity"], {"employed": 3200, "unemployed": 400, "inactive": 4400, "total15": 6400})
        self.assertEqual(u["commute"], {"total": 3200, "same_unit": 1600, "other_unit": 640, "other_oblast": 800,
                                        "abroad": 160})
        self.assertEqual(u["migration"], {"total": 8000, "same_settlement": 4400, "internal": 2800, "abroad": 800})

    def test_industry_covers_every_nace_section(self):
        industry = self.units["71331"]["industry"]
        self.assertEqual(list(industry), ["total", *map(chr, range(ord("A"), ord("V"))), "unknown"])
        self.assertEqual((industry["total"], industry["A"], industry["B"], industry["U"], industry["unknown"]),
                         (3200, 800, 112, 112, 160))

    def test_settlements_join_the_two_settlement_tables(self):
        rows = [(s["id"], s["name"], s["unit"], s["oblast"], s["urban"], s["population"], s["age"][0])
                for s in self.data["settlements"]]
        self.assertEqual(rows, [
            ("704865", "Borča", "70203", "RS110", False, 2000, 80),
            ("791075", "Beograd (Palilula)", "70203", "RS110", True, 10000, 400),
            ("802824", "Novi Sad", "89010", "RS123", True, 16000, 640),
            ("802883", "Futog", "89010", "RS123", False, 4000, 160),
            ("728934", "Brzi Brod", "71331", "RS225", False, 2000, 80),
            ("792047", "Niš (Medijana)", "71331", "RS225", True, 6000, 240),
            ("729639", "Čokot", "71323", "RS225", False, 2000, 80),
            ("792055", "Niš (Palilula)", "71323", "RS225", True, 4000, 160),
            ("700614", "Aleksinac", "70025", "RS225", True, 7000, 280),
            ("700754", "Vrćenovica", "70025", "RS225", False, 1000, 40),
            (None, "Dobro Selo", "70025", "RS225", False, 2000, 80),  # a name the territory list does not have
        ])

    def test_a_unit_a_table_does_not_list_gets_none_for_it(self):
        units = self._process(skip={("religion", "Алексинац"), ("migration", "Медијана")})["units"]
        self.assertIsNone(units["70025"]["religion"])
        self.assertEqual(units["70025"]["education"]["total15"], 8000)
        self.assertIsNone(units["71331"]["migration"])
        self.assertEqual(units["71331"]["religion"]["orthodox"], 6400)

    def test_an_alias_must_match_one_row_of_every_workbook(self):
        for changes in ({"skip": {("religion", "Нови Сад")}}, {"twice": {("industry", "Нови Сад")}}):
            with self.subTest(changes), self.assertRaisesRegex(ValueError, "Нови Сад.*RS123"):
                self._process(**changes)

    def test_changed_ethnicity_column_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_workbooks(raw)
            path = raw / "census" / srb.CENSUS_FILES["ethnicity"][1]
            workbook = load_workbook(path)
            sheet = workbook.active
            sheet["D2"].value, sheet["E2"].value = sheet["E2"].value, sheet["D2"].value
            workbook.save(path)
            workbook.close()
            self._live_in(raw)
            with self.assertRaisesRegex(ValueError, "unexpected ethnicity columns"):
                Census().process()

    def test_areas_are_named_under_the_parent_found_before_them(self):
        religion, population = Census()._walk("religion"), Census()._walk("settlement_population")
        self.assertEqual(dict(religion.counts), {"upper": 6, "oblast": 3, "exact": 3, "alias": 4})
        self.assertEqual(dict(population.counts), {"upper": 6, "oblast": 3, "exact": 13, "alias": 4, "unmatched": 1})
        self.assertEqual([u[0] for u in population.unmatched], ["Добро Село"])
        self.assertEqual(sorted(religion.units), ["70025", "70203", "71323", "71331", "79014", "79022", "89010"])


class FetchTest(unittest.TestCase):
    class Handler(http.server.BaseHTTPRequestHandler):
        paths = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            FetchTest.Handler.paths.append(self.path)
            body = b"PK\x03\x04not really a workbook"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def test_downloads_the_ten_tables_and_paces_the_requests(self):
        Handler = FetchTest.Handler
        Handler.paths = []
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(srb, "CENSUS_BASE", f"http://127.0.0.1:{server.server_address[1]}"), \
                mock.patch.object(fetch, "RAW", Path(tmp)), mock.patch.object(census.time, "sleep") as sleep, \
                mock.patch("builtins.print"):
            Census().fetch()
            self.assertEqual(Handler.paths, [f"/{srb.CENSUS_FILES[k][0]}/{srb.CENSUS_FILES[k][1]}" for k in census.FETCH_TABLES])
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "census").iterdir()),
                             sorted([*(srb.CENSUS_FILES[k][1] for k in census.FETCH_TABLES), "manifest.json"]))
            self.assertEqual([call.args for call in sleep.call_args_list], [(1.0,)] * len(census.FETCH_TABLES))
            Census().fetch()  # cached: no request, no waiting
            self.assertEqual(len(Handler.paths), len(census.FETCH_TABLES))
            self.assertEqual(sleep.call_count, len(census.FETCH_TABLES))

    def test_fetch_includes_the_occupation_workbook_required_by_citizens(self):
        with mock.patch.object(Census, "download") as download, mock.patch.object(census.time, "sleep"):
            Census().fetch()
        self.assertIn(srb.CENSUS_FILES["occupation"][1], [call.args[1] for call in download.call_args_list])


if __name__ == "__main__":
    unittest.main()
