"""pipeline/build/citizens.py against synthetic Popis 2022 tables: the mapping, the null rule, the rounding, the
national row, KiM nulls and the Serbian Latin strings. No network, no raw workbooks."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from pipeline.build import citizens as C

CYRILLIC = re.compile("[\u0400-\u04ff]")


def occupation(**over):
    """One occupation row with the workbook's labels (table 25: ISCO-08 major groups, with their hyphenation
    artefacts and the English label that is wrong for the machine operators)."""
    cells = {
        "Укупно Total": 1000,
        "Занимање / › руководиоци, функционери и законодавци managers": 100,
        "Занимање / › стручњаци и уметници professionals": 200,
        "Занимање / › Инжињери, стручни сарадници и техничари technicians and associate professionals": 100,
        "Занимање / › админи- стративни службеници clerical support workers": 50,
        "Занимање / › услужна и трговачка занимања service and sales workers": 150,
        "Occupation › пољопри-вредници, шумари, рибари и сродни skilled agricultural, forestry and fishery workers": 20,
        "Occupation › занатлије и сродни craft and related trades workers": 80,
        "Occupation › руковаоци машинама и построје- њима, монтери и возачи skilled agricultural, forestry and fishery workers": 100,
        "Occupation › једноставна занимања elementary occupations": 100,
        "Occupation › војна занимања armed forces occupations": 40,
        "Occupation › непознато unknown": 60,
    }
    cells.update(over)
    return cells


def education(**over):
    cells = {
        "Укупно Total": 1000,
        "Без школске спреме Without educational attainment": 20,
        "Непотпуно основно образовање Incomplete primary education": 30,
        "Основно образовање Primary education": 200,
        "Средње образовање Secondary education › свега Аll": 500,
        "Средње образовање Secondary education › гимназија Gymnasium": 100,
        "Више образовање High education": 100,
        "Високо образовање Higher education": 140,
        "Непознато Unknown": 10,
    }
    cells.update(over)
    return cells


def migration(**over):
    cells = {
        "Укупно Total": 1000,
        "Од рођења станује у истом насељу Lives in the same settlement since birth": 500,
        "Досељено становништво Migrant population › укупно total": 500,
        "Досељено становништво Migrant population › са подручја Републике Србије, и то: within the Republic of Serbia, of which: › свега all": 400,
        "Досељено становништво Migrant population › из иностранства, и то: from abroad, of which: › свега all": 100,
        "… › из бивших република СФРЈ from the former SFRY republics": 70,
        "… › из других држава from other countries": 25,
        "… › непозната држава досељења unknown country of migration": 5,
    }
    cells.update(over)
    return cells


def commute(**over):
    cells = {
        "Економски активно становништво које обавља занимање Economic… › укупно total": 300,
        "… › у оквиру исте општине within the same municipality": 100,
        "… › у другој општини in another municipality": 150,
        "… › у другој области in another area": 49,
        "… › у страној држави in the foreign country": 1,
    }
    cells.update(over)
    return cells


def age_row():
    return {"t": list(range(1, 19)), "m": [0] * 18, "f": [0] * 18}


class OccupationTests(unittest.TestCase):
    def test_groups_follow_the_isco_major_groups(self):
        counts = C.occupation_cells(occupation())
        self.assertEqual(counts, {"executive": 100, "engineer": 300, "scholar": None, "healer": None, "service": 250,
                                  "clerk": 50, "farmer": 20, "builder": 80, "maker": 100})

    def test_unpublished_groups_stay_null_not_zero(self):
        counts = C.occupation_cells(occupation())
        self.assertIsNone(counts["scholar"])
        self.assertIsNone(counts["healer"])
        self.assertIsNone(C.occupation_cells(None))

    def test_a_missing_column_leaves_its_group_null_never_zero(self):
        cells = occupation()
        del cells["Occupation › занатлије и сродни craft and related trades workers"]
        counts = C.occupation_cells(cells)
        self.assertIsNone(counts["builder"])
        self.assertEqual(counts["executive"], 100)
        self.assertIsNone(C.education_cells({"Укупно Total": 1, "Без школске спреме Without educational attainment": 2})["less_than_hs"])
        # two columns matching one fragment is an error, not a pick
        cells = occupation()
        cells["Occupation › занатлије и сродни craft and related trades workers (copy)"] = 1
        with self.assertRaises(ValueError):
            C.occupation_cells(cells)


class RowTests(unittest.TestCase):
    def test_row_keeps_counts_and_shares_and_figures(self):
        counts = C.occupation_cells(occupation())
        r = C.row(counts, 1000, 20)
        self.assertEqual(r["total"], 1000)
        self.assertEqual(r["shares"]["executive"], 0.1)
        self.assertIsNone(r["shares"]["scholar"])
        self.assertEqual(sum(r["figures"].values()), 20)
        self.assertEqual(r["figures"]["scholar"], 0)
        self.assertNotIn("figures", C.row(counts, 1000))

    def test_largest_remainder_sums_to_n_and_breaks_ties_towards_the_larger_then_earlier_key(self):
        figs = C.largest_remainder({"a": 1, "b": 1, "c": 2}, 5)
        self.assertEqual(figs, {"a": 1, "b": 1, "c": 3})  # a and b tie: both get one
        self.assertEqual(sum(figs.values()), 5)
        figs = C.largest_remainder({"a": 3, "b": 3}, 1)
        self.assertEqual(figs, {"a": 1, "b": 0})  # a tie of equals: the earlier key wins
        self.assertEqual(C.largest_remainder({"a": 0, "b": 0}, 10), {"a": 0, "b": 0})
        self.assertEqual(C.largest_remainder({"a": None, "b": 5}, 10), {"a": 0, "b": 10})

    def test_commute_derives_the_home_settlement_and_stays_null_when_impossible(self):
        counts = C.commute_counts({"total": 300, "same_unit": 100, "other_unit": 150, "other_oblast": 49, "abroad": 1}, 1000)
        self.assertEqual(counts, {"home_settlement": 700, "same_municipality": 100, "other_municipality": 150, "other_area": 49, "abroad": 1})
        self.assertIsNone(C.commute_counts({"total": 300}, 200)["home_settlement"])  # more migrants than employed: no figure
        self.assertIsNone(C.commute_counts(None, 1000))
        self.assertIsNone(C.commute_counts({"total": 300, "same_unit": None, "other_unit": 1, "other_oblast": 1, "abroad": 1}, 1000)["same_municipality"])

    def test_age_bins_are_the_census_brackets(self):
        counts = C.age_counts(list(range(1, 19)))
        self.assertEqual(counts, {"child": 6, "young": 15, "midlife": 45, "elder": 105})  # 1+2+3, 4+5+6, 7…11, 12…18
        self.assertIsNone(C.age_counts([1] * 17))
        self.assertIsNone(C.age_counts(None))

    def test_education_and_nativity_sum_the_published_columns(self):
        edu = C.education_cells(education())
        self.assertEqual(edu, {"less_than_hs": 50, "primary": 200, "high_school": 500, "bachelors": 100, "graduate": 140})
        nat = C.nativity_cells(migration())
        self.assertEqual(nat, {"same_settlement": 500, "elsewhere_serbia": 400, "former_yugoslavia": 70, "other_country": 25})


class SpecialistTests(unittest.TestCase):
    def test_specialists_follow_the_ratio_rule(self):
        nat = {"workforce": {"shares": {"executive": 0.2, "engineer": 0.3, "service": 0.3, "farmer": 0.1}}}
        rec = {"workforce": {"shares": {"executive": 0.4, "engineer": 0.3, "service": 0.1, "farmer": 0.2}}}
        sp = C.specialists(rec, nat)
        self.assertEqual([(s["row"], s["key"], s["ratio"]) for s in sp],
                         [("workforce", "executive", 2.0), ("workforce", "farmer", 2.0), ("workforce", "service", 0.33)])
        # a category under 1% both here and nationally is skipped; a null share is skipped too
        rec["workforce"]["shares"]["farmer"] = 0.005
        nat["workforce"]["shares"]["farmer"] = 0.005
        self.assertNotIn("farmer", [s["key"] for s in C.specialists(rec, nat)])
        rec["workforce"]["shares"]["executive"] = None
        self.assertNotIn("executive", [s["key"] for s in C.specialists(rec, nat)])
        rec["workforce"]["shares"]["executive"] = 0.1
        nat["workforce"]["shares"]["executive"] = 0
        self.assertNotIn("executive", [s["key"] for s in C.specialists(rec, nat)])

    def test_at_most_four_over_and_two_under(self):
        nat = {"workforce": {"shares": {k: 0.1 for k in C.OCCUPATION}}}
        rec = {"workforce": {"shares": {"executive": 0.3, "engineer": 0.3, "service": 0.3, "clerk": 0.1, "builder": 0.02, "maker": 0.02, "farmer": 0.02}}}
        sp = C.specialists(rec, nat)
        hi = [s for s in sp if s["ratio"] >= C.SPECIALIST_HIGH]
        lo = [s for s in sp if s["ratio"] <= C.SPECIALIST_LOW]
        self.assertEqual((len(hi), len(lo)), (3, 2))


class RecordTests(unittest.TestCase):
    def test_city_rows_sum_its_parts_and_a_kim_city_is_null(self):
        cities = [{"id": "A", "counties": ["10001", "10002"]}, {"id": "K", "counties": ["25001"]}]
        census_units = {
            "10001": {"age": age_row(), "commute": {"total": 300, "same_unit": 100, "other_unit": 150, "other_oblast": 49, "abroad": 1}},
            "10002": {"age": age_row(), "commute": {"total": 200, "same_unit": 50, "other_unit": 100, "other_oblast": 49, "abroad": 1}},
        }
        occ = {"10001": occupation(), "10002": occupation(**{"Укупно Total": 500})}
        edu = {"10001": education(), "10002": education(**{"Укупно Total": 500})}
        mig = {"10001": migration(), "10002": migration(**{"Укупно Total": 500})}
        recs = C.city_records(cities, census_units, occ, edu, mig)
        a = recs["A"]
        self.assertEqual(a["workforce"]["total"], 1500)
        self.assertEqual(a["age"]["counts"], {"child": 12, "young": 30, "midlife": 90, "elder": 210})
        self.assertEqual(a["commute"]["counts"]["home_settlement"], 1000)
        self.assertEqual(a["education"]["total"], 1500)
        self.assertIsNone(recs["K"]["workforce"])
        self.assertIsNone(recs["K"]["age"])
        nat = C.national_row(occupation(), education(), migration(), commute(), dict(zip(
            [f"Старост / Age › {i}" for i in range(18)], [1] * 18)))
        self.assertIsNone(C.full_row(recs["K"], nat))  # KiM: no census, the whole record is null
        full = C.full_row(a, nat)
        self.assertTrue(full["reliable"])
        self.assertEqual(list(full), ["workforce", "age", "commute", "education", "nativity", "specialists", "reliable"])

    def test_a_part_without_a_row_makes_the_city_row_null(self):
        cities = [{"id": "A", "counties": ["10001", "10002"]}]
        census_units = {"10001": {"age": age_row(), "commute": {"total": 10, "same_unit": 1, "other_unit": 1, "other_oblast": 1, "abroad": 1}}}
        recs = C.city_records(cities, census_units, {"10001": occupation()}, {}, {"10001": migration()})
        self.assertIsNone(recs["A"]["education"])
        self.assertEqual(recs["A"]["workforce"]["total"], 1000)
        self.assertEqual(recs["A"]["commute"]["counts"]["home_settlement"], 990)


class NationalRowTests(unittest.TestCase):
    def test_national_row_reads_the_republic_cells(self):
        age_cells = {f"Старост / Age › {i}": 10 for i in range(18)}
        age_cells["Укупно Total"] = 180
        nat = C.national_row(occupation(), education(), migration(), commute(), age_cells)
        self.assertEqual(nat["workforce"]["total"], 1000)
        self.assertEqual(nat["workforce"]["counts"]["engineer"], 300)
        self.assertEqual(nat["age"]["counts"], {"child": 30, "young": 30, "midlife": 50, "elder": 70})
        self.assertEqual(nat["commute"]["counts"], {"home_settlement": 700, "same_municipality": 100, "other_municipality": 150, "other_area": 49, "abroad": 1})
        self.assertEqual(nat["nativity"]["total"], 1000)
        self.assertEqual(nat["specialists"], [])
        self.assertNotIn("reliable", nat)
        self.assertEqual(sum(nat["workforce"]["figures"].values()), 20)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = Path(self.tmp.name)
        age_cells = {f"Старост / Age › {i}": 10 for i in range(18)}
        age_cells["Укупно Total"] = 180
        self.nat = C.national_row(occupation(), education(), migration(), commute(), age_cells)
        cities = [{"id": "A", "counties": ["10001"]}, {"id": "K", "counties": ["25001"]}]
        census_units = {"10001": {"age": age_row(), "commute": {"total": 300, "same_unit": 100, "other_unit": 150, "other_oblast": 49, "abroad": 1}}}
        self.recs = C.city_records(cities, census_units, {"10001": occupation()}, {"10001": education()}, {"10001": migration()})
        (self.web / "cities.json").write_text(json.dumps(cities), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, doc):
        (self.web / "citizens.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def test_document_shape_and_serbian_latin(self):
        doc = C.make_doc(self.nat, self.recs)
        self.assertEqual(list(doc), ["version", "vintage", "year", "sources", "figures", "rows", "groups", "rule", "national", "cities"])
        self.assertEqual(doc["figures"], {"workforce": 20, "age": 10, "commute": 10})
        self.assertEqual(doc["rule"]["specialist_high"], 1.5)
        self.assertEqual(doc["rule"]["min_share"], 0.01)
        self.assertEqual(list(doc["rows"]), ["workforce", "age", "commute", "education", "nativity"])
        self.assertEqual([g["key"] for g in doc["groups"]["age"]], ["child", "young", "midlife", "elder"])
        self.assertEqual([g["key"] for g in doc["groups"]["workforce"]],
                         ["executive", "engineer", "scholar", "healer", "service", "clerk", "farmer", "builder", "maker"])
        self.assertEqual([g["key"] for g in doc["groups"]["education"]], ["less_than_hs", "primary", "high_school", "bachelors", "graduate"])
        self.assertEqual([g["key"] for g in doc["groups"]["commute"]], ["home_settlement", "same_municipality", "other_municipality", "other_area", "abroad"])
        self.assertEqual([g["key"] for g in doc["groups"]["nativity"]], ["same_settlement", "elsewhere_serbia", "former_yugoslavia", "other_country"])
        self.assertIsNone(doc["cities"]["K"])
        # 300 of 900 classified jobs × 20 icons = 6.67 → 6 whole figures + one of the three remainders
        self.assertEqual(doc["cities"]["A"]["workforce"]["figures"], {"executive": 2, "engineer": 7, "scholar": 0, "healer": 0,
                                                                   "service": 6, "clerk": 1, "farmer": 0, "builder": 2, "maker": 2})
        texts = [doc["vintage"], doc["rule"]["text"], *doc["rows"].values()]
        for groups in doc["groups"].values():
            for g in groups:
                texts += [g["label"], g["lines"]]
                self.assertTrue(g["icon"].startswith("c-"), g)
        for t in texts:
            self.assertFalse(CYRILLIC.search(t), t)
        self.assertIn("š", doc["rule"]["text"])  # Serbian Latin with its diacritics, not ASCII English
        self.assertNotIn(" the ", doc["rule"]["text"])
        self.assertEqual(doc["groups"]["education"][0]["label"], "Bez završene osnovne škole")
        self.assertEqual(doc["groups"]["age"][0]["label"], "Dete (do 14)")

    def test_check_passes_and_notes_the_null_city(self):
        self.write(C.make_doc(self.nat, self.recs))
        levels = C.check(self.web)
        self.assertEqual([l for l, _ in levels], ["PASS", "NOTE"])
        self.assertIn("2 cities, 1 without a census row", levels[0][1])

    def test_check_fails_on_a_broken_file(self):
        doc = copy.deepcopy(C.make_doc(self.nat, self.recs))
        doc["version"] = 2
        self.write(doc)
        self.assertEqual(C.check(self.web)[0][0], "FAIL")
        doc["version"] = 1
        doc["figures"]["age"] = 12
        self.write(doc)
        self.assertEqual(C.check(self.web)[0][0], "FAIL")
        doc["figures"]["age"] = 10
        doc["cities"]["ZZ"] = doc["cities"]["A"]
        self.write(doc)
        self.assertTrue(any(l == "FAIL" and "ZZ" in m for l, m in C.check(self.web)))
        (self.web / "citizens.json").write_text("{", encoding="utf-8")
        self.assertEqual(C.check(self.web)[0][0], "FAIL")


if __name__ == "__main__":
    unittest.main()
