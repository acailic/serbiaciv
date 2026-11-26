"""pipeline.sources.rzs_db on hand-written records: the pure mappings, fetch() and process()."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, rzs, source, srb, territory
from pipeline.sources import rzs_db


def rec(unit, value, **dims):
    return {"IDTer": unit + " " * (5 - len(unit)), "skrIndikator": "Prosečne neto zarade", "Vrednost": value, **dims}


class ByUnitTest(unittest.TestCase):
    def test_filters_by_indicator_and_dimensions_and_strips_ids(self):
        rows = [rec("70017", "10", nPol="Ukupno"), rec("70246", "…", nPol="Ukupno"), rec("70017", "99", nPol="Muško"),
                {**rec("70017", "7", nPol="Ukupno"), "skrIndikator": "Prosečne bruto zarade"}]
        self.assertEqual(rzs_db.by_unit(rows, "Prosečne neto", nPol="Ukupno"), {"70017": 10.0, "70246": None})
        self.assertEqual(rzs_db.by_unit(rows, nPol="Ukupno"), {"70017": 7.0, "70246": None})  # the last record wins
        self.assertEqual(rzs_db.by_unit(rows, "Prosečne neto", nPol="Žensko"), {})


class SumPartsTest(unittest.TestCase):
    def test_counts_sum_and_a_missing_part_makes_none(self):
        self.assertEqual(rzs_db.sum_parts({"a": 1.0, "b": 2.0, "c": None}, ["a", "b"]), 3.0)
        self.assertIsNone(rzs_db.sum_parts({"a": 1.0, "b": None}, ["a", "b"]))


# --- hand-written records ----------------------------------------------------------------------------------------

BELGRADE = territory.parts_of(territory.GRAD_BEOGRAD)  # the 17 city municipalities
NIŠ = territory.parts_of("79022")
KOSOVO = [u for u in territory.units() if u.startswith("9")]
UNITS = territory.units()
ALIBUNAR = "80039"  # a plain opština: in no aggregate


def row(unit, indicator, value, year="2025", status="A", **dims):
    """A record as the office writes it: the id padded, the value a string, one year."""
    return {"IDTer": unit.ljust(6), "skrIndikator": indicator, "Vrednost": value, "nVrTacka": year,
            "God+Mes": year + "00", "IDStatusPodatka": status, **dims}


def nace(letter):
    """The nKD08 text the office writes for a NACE section."""
    return f"{letter} - delatnost {letter}"


def leaves(entry):
    """Every number or None at the end of a table entry ("by_nace" nests one dict)."""
    return [leaf for v in entry.values() for leaf in (leaves(v) if isinstance(v, dict) else [v])]


class PopulationTest(unittest.TestCase):
    def test_one_list_per_unit_and_belgrade_the_sum_of_its_parts(self):
        rows = [
            row("70017", rzs_db.POPULATION, "30723", "1991"), row("70017", rzs_db.POPULATION, "21041"),
            row(ALIBUNAR, rzs_db.POPULATION, "-", "1991", status="M"), row(ALIBUNAR, rzs_db.POPULATION, "26711"),
            row("79022", rzs_db.POPULATION, "248079"),  # the office's own row for a grad
            row(NIŠ[0], rzs_db.POPULATION, "-", "1991", status="M"), row(NIŠ[0], rzs_db.POPULATION, "-", status="M"),
            *[row(p, rzs_db.POPULATION, "1000") for p in BELGRADE[:16]],
        ]
        years, pop = rzs_db.population(rows)
        self.assertEqual(years, [1991, 2025])
        self.assertEqual(pop["70017"], [30723.0, 21041.0])
        self.assertEqual(pop[ALIBUNAR], [None, 26711.0])  # "-" is no data, not zero
        self.assertEqual(pop["79022"], [None, 248079.0])
        self.assertIsNone(pop[NIŠ[0]])  # nothing in any year: no list
        self.assertIsNone(pop["79014"])  # one of the 17 parts is missing
        self.assertEqual(sorted(pop), UNITS)
        self.assertTrue(all(v is None or len(v) == 2 for v in pop.values()))

    def test_belgrade_year_by_year(self):
        rows = [row(p, rzs_db.POPULATION, "1000") for p in BELGRADE] + [row(BELGRADE[0], rzs_db.POPULATION, "900", "2024")]
        years, pop = rzs_db.population(rows)
        self.assertEqual(years, [2024, 2025])
        self.assertEqual(pop["79014"], [None, 17000.0])
        for unit in KOSOVO:
            self.assertIsNone(pop[unit])


class Share65Test(unittest.TestCase):
    ALEXANDROVAC = {"Ukupno": "21041", "65–69": "1793", "70–74": "1803", "75–79": "1209", "80–84": "596", "85 i više godina": "459"}

    def rows(self, unit, **instead):
        return [row(unit, rzs_db.POPULATION, instead.get(g, v), nStarGrupa=g) for g, v in self.ALEXANDROVAC.items()]

    def test_share_is_the_five_oldest_groups_over_the_total(self):
        rows = self.rows("70017") + [r for p in BELGRADE for r in self.rows(p)]
        shares = rzs_db.share_65(rows)
        self.assertEqual(shares["70017"], 5860 / 21041)
        self.assertNotIn("79014", shares)  # a share is computed, never summed
        self.assertEqual(len(shares), 18)

    def test_a_missing_group_or_total_leaves_no_share(self):
        self.assertEqual(rzs_db.share_65(self.rows("70017", **{"85 i više godina": "-"})), {"70017": None})
        self.assertEqual(rzs_db.share_65(self.rows("70017", Ukupno="…")), {"70017": None})
        self.assertEqual(rzs_db.share_65(self.rows("70017", **{"70–74": "0"})), {"70017": 4057 / 21041})  # a real zero counts


class OverUnitsTest(unittest.TestCase):
    def test_counts_sum_belgrade_but_a_rate_a_share_or_a_wage_does_not(self):
        table = {p: 2.0 for p in BELGRADE}
        table["70017"] = 3.0
        counts = rzs_db.over_units(table, summed=True)
        rates = rzs_db.over_units(table, summed=False)
        self.assertEqual(counts["79014"], 34.0)
        self.assertIsNone(rates["79014"])
        self.assertEqual((counts["70017"], rates["70017"]), (3.0, 3.0))
        self.assertEqual(sorted(counts), UNITS)
        self.assertTrue(all(counts[u] is None and rates[u] is None for u in KOSOVO))

    def test_a_missing_part_empties_belgrade_and_a_grad_keeps_its_own_row(self):
        table = {p: 1.0 for p in BELGRADE[1:]}  # one part is missing
        table.update({part: 5.0 for part in NIŠ})
        table["79022"] = 9.0
        counts = rzs_db.over_units(table, summed=True)
        self.assertIsNone(counts["79014"])
        self.assertEqual(counts["79022"], 9.0)  # the office's row, not the sum of Niš's parts
        table.pop("79022")
        self.assertEqual(rzs_db.over_units(table, summed=True)["79022"], 25.0)  # without a row: the sum of the parts
        self.assertIsNone(rzs_db.over_units(table, summed=False)["79022"])


class EmploymentTest(unittest.TestCase):
    def test_total_is_the_office_s_own_row_and_every_section_is_a_key(self):
        rows = [row("70017", rzs_db.EMPLOYMENT, "4612", nKD08="Ukupno"),
                row("70017", rzs_db.EMPLOYMENT, "65", nKD08=nace("A")),
                row("70017", rzs_db.EMPLOYMENT, "7", nKD08=nace("B")),
                row("70017", rzs_db.EMPLOYMENT, "0", nKD08=nace("C")),
                row("70017", rzs_db.EMPLOYMENT, "-", nKD08=nace("D"), status="M")]
        employment = rzs_db.employment(rows)
        self.assertEqual(employment["70017"]["total"], 4612.0)  # not the sum of the sections (72)
        by_nace = employment["70017"]["by_nace"]
        self.assertEqual(sorted(by_nace), [letter for _, letter, _ in srb.INDUSTRIES])
        self.assertEqual([by_nace[k] for k in "ABCD"], [65.0, 7.0, 0.0, None])  # a real zero stays 0, "-" is None
        self.assertEqual(sorted(employment), UNITS)
        self.assertIsNone(employment["79014"]["total"])

    def test_belgrade_is_the_sum_of_its_parts_total_by_total_and_section_by_section(self):
        rows = []
        for p in BELGRADE:
            rows += [row(p, rzs_db.EMPLOYMENT, "10", nKD08="Ukupno"), row(p, rzs_db.EMPLOYMENT, "1", nKD08=nace("A")),
                     row(p, rzs_db.EMPLOYMENT, "0", nKD08=nace("B"))]
        rows.append(row(BELGRADE[3], rzs_db.EMPLOYMENT, "-", nKD08=nace("A"), status="M"))
        belgrade = rzs_db.employment(rows)["79014"]
        self.assertEqual(belgrade["total"], 170.0)
        self.assertEqual((belgrade["by_nace"]["A"], belgrade["by_nace"]["B"]), (None, 0.0))  # one part's "A" is missing


class LifeExpectancyTest(unittest.TestCase):
    def test_m_and_f_per_unit_and_never_a_sum(self):
        rows = [row("70017", rzs_db.LIFE_EXPECTANCY, "74.53", nPol="Muško"), row("70017", rzs_db.LIFE_EXPECTANCY, "79.77", nPol="Žensko"),
                row("79022", rzs_db.LIFE_EXPECTANCY, "73.01", nPol="Muško"),
                *[row(p, rzs_db.LIFE_EXPECTANCY, "70.0", nPol="Muško") for p in BELGRADE]]
        table = rzs_db.life_expectancy(rows)
        self.assertEqual(table["70017"], {"m": 74.53, "f": 79.77})
        self.assertEqual(table["79022"], {"m": 73.01, "f": None})
        self.assertEqual(table["79014"], {"m": None, "f": None})  # a rate is never summed
        self.assertEqual(sorted(table), UNITS)
        self.assertTrue(all(table[u] == {"m": None, "f": None} for u in KOSOVO))


class FlaggedTest(unittest.TestCase):
    def test_only_statuses_other_than_a_and_selected_like_by_unit(self):
        rows = [row("70017", rzs_db.BIRTHS, "138"), row("80284", rzs_db.BIRTHS, "-", status="M"),
                row("70017", rzs_db.DEATHS, "349", status="P"), rec("70246", "9")]
        self.assertEqual(rzs_db.flagged(rows), {"80284": "M", "70017": "P"})
        self.assertEqual(rzs_db.flagged(rows, "Živorođeni"), {"80284": "M"})
        self.assertEqual(rzs_db.flagged(rows, "Živorođeni", nPol="Ukupno"), {})
        self.assertEqual(rzs_db.flagged([]), {})


class YearTest(unittest.TestCase):
    def test_the_one_year_of_an_export(self):
        self.assertEqual(rzs_db.year_of([row("70017", rzs_db.BIRTHS, "1"), row("70092", rzs_db.BIRTHS, "2")]), 2025)
        for records in ([], [row("70017", rzs_db.BIRTHS, "1"), row("70017", rzs_db.BIRTHS, "2", "2024")]):
            with self.assertRaises(RuntimeError):
                rzs_db.year_of(records)


# --- the source --------------------------------------------------------------------------------------------------

class RawFolder(unittest.TestCase):
    """A raw folder with hand-written exports, and print kept out of the test output."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raw = Path(tmp.name)
        for patcher in (mock.patch.object(source, "RAW", self.raw), mock.patch.object(fetch, "RAW", self.raw),
                        mock.patch("builtins.print")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, name, records):
        path = self.raw / "rzs_db" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records), encoding="utf-8")


def fake_datasets(without: str = "") -> dict[str, rzs.Dataset]:
    """Parsed pages that know every id the selections ask of their dataset (all but `without`), and a few units."""
    specs: dict[str, dict] = {}
    for picked in rzs_db.SELECTIONS.values():
        spec = specs.setdefault(picked["dataset"], {"dims": {}, "indicators": []})
        spec["indicators"] += list(picked["indicators"])
        for dim, ids in picked["dims"].items():
            spec["dims"][dim] = {**spec["dims"].get(dim, {}), **ids}
    out = {}
    for subarea, spec in specs.items():
        dims = {dim: tuple(rzs.Node(i, f"{dim} node {i}", None) for i in ids if i != without)
                for dim, ids in spec["dims"].items()}
        dims["agg-102"] = tuple(rzs.Node(u, territory.name(u), "RS") for u in ("70017", "79022", "90018", "RS"))
        out[subarea] = rzs.Dataset(subarea, dims, {}, tuple(i for i in spec["indicators"] if i != without))
    return out


class FetchTest(RawFolder):
    def test_asks_for_every_selection_under_its_export_s_name(self):
        datasets = fake_datasets()
        with (mock.patch.object(rzs, "load_dataset", side_effect=lambda subarea, **kw: datasets[subarea]) as load,
              mock.patch.object(rzs, "export", return_value=[{"Vrednost": "1"}]) as export):
            rzs_db.RzsDatabase().fetch()
        self.assertEqual([call.args[2] for call in export.call_args_list], [f"{n}.json" for n in rzs_db.SELECTIONS])
        for call, picked in zip(export.call_args_list, rzs_db.SELECTIONS.values()):
            ds, selection, _ = call.args
            self.assertEqual(ds.subarea, picked["dataset"])
            self.assertEqual(selection, {"indicators": list(picked["indicators"]),
                                         **{dim: list(ids) for dim, ids in picked["dims"].items()},
                                         "agg-102": ["70017", "79022"]})  # the units the tree has, without Kosovo
        self.assertEqual([call.args[0] for call in load.call_args_list], [picked["dataset"] for picked in rzs_db.SELECTIONS.values()])
        self.assertTrue(all(call.kwargs == {"force": False} for call in load.call_args_list))
        self.assertTrue(all(call.kwargs == {"force": False} for call in export.call_args_list))

    def test_a_tree_with_belgrade_selects_it(self):
        # Grad Beograd is in none of today's trees; a tree that lists it has a row for it, and that row is wanted.
        datasets = fake_datasets()
        datasets["2403040403"] = rzs.Dataset("2403040403", {**datasets["2403040403"].dims, "agg-102": (rzs.Node("79014", "Grad Beograd", "RS110"), rzs.Node("90018", "Vitina", "RS235"))}, {}, datasets["2403040403"].indicators)
        with mock.patch.object(rzs, "load_dataset", side_effect=lambda subarea, **kw: datasets[subarea]), \
                mock.patch.object(rzs, "export", return_value=[{"Vrednost": "1"}]) as export:
            rzs_db.RzsDatabase().fetch()
        wages = next(call.args[1] for call in export.call_args_list if call.args[2] == "wages.json")
        self.assertEqual(wages["agg-102"], ["79014"])

    def test_refuses_an_id_the_office_no_longer_has(self):
        datasets = fake_datasets(without="199100")
        with mock.patch.object(rzs, "load_dataset", side_effect=lambda subarea, **kw: datasets[subarea]), \
                mock.patch.object(rzs, "export") as export, self.assertRaises(RuntimeError) as caught:
            rzs_db.RzsDatabase().fetch()
        self.assertIn("199100", str(caught.exception))
        export.assert_not_called()


class ProcessTest(RawFolder):
    def setUp(self):
        super().setUp()
        self.write("pop_estimate", [row("70017", rzs_db.POPULATION, "30723", "1991"), row("70017", rzs_db.POPULATION, "21041"),
                                    *[row(p, rzs_db.POPULATION, "1000") for p in BELGRADE]])
        self.write("pop_65", [row("70017", rzs_db.POPULATION, "21041", nStarGrupa="Ukupno")]
                   + [row("70017", rzs_db.POPULATION, v, nStarGrupa=g)
                      for g, v in zip(rzs_db.AGED_65, ("1793", "1803", "1209", "596", "459"))])
        self.write("births_deaths", [row("70017", rzs_db.BIRTHS, "138"), row("70017", rzs_db.DEATHS, "349"),
                                     row("70017", rzs_db.NATURAL_INCREASE, "-10.0"),
                                     row("80284", rzs_db.BIRTHS, "-", status="M")]
                   + [r for p in BELGRADE for r in (row(p, rzs_db.BIRTHS, "10"), row(p, rzs_db.DEATHS, "5"), row(p, rzs_db.NATURAL_INCREASE, "-1.5"))])
        self.write("wages", [row("70017", rzs_db.NET, "81403"), row("70017", rzs_db.GROSS, "112396")]
                   + [r for p in BELGRADE for r in (row(p, rzs_db.NET, "95017"), row(p, rzs_db.GROSS, "131453"))])
        self.write("employment", [row("70017", rzs_db.EMPLOYMENT, "4612", nKD08="Ukupno"), row("70017", rzs_db.EMPLOYMENT, "65", nKD08=nace("A"))]
                   + [r for p in BELGRADE for r in (row(p, rzs_db.EMPLOYMENT, "10", nKD08="Ukupno"), row(p, rzs_db.EMPLOYMENT, "1", nKD08=nace("A")))])
        self.write("life_expectancy", [row("70017", rzs_db.LIFE_EXPECTANCY, "74.53", nPol="Muško"), row("70017", rzs_db.LIFE_EXPECTANCY, "79.77", nPol="Žensko")])

    def test_every_table_over_every_unit(self):
        data = rzs_db.RzsDatabase().process()
        self.assertEqual(sorted(data), ["_files", "births", "deaths", "employment", "life_expectancy", "natural_increase",
                                        "pop", "pop_65", "pop_years", "status", "vintage", "wages"])
        self.assertEqual(data["pop_years"], [1991, 2025])
        self.assertEqual(data["pop"]["70017"], [30723.0, 21041.0])
        self.assertEqual(data["pop"]["79014"], [None, 17000.0])
        self.assertEqual(data["pop_65"], {"year": 2025, "by_unit": data["pop_65"]["by_unit"]})
        self.assertEqual(data["pop_65"]["by_unit"]["70017"], 5860 / 21041)
        self.assertIsNone(data["pop_65"]["by_unit"]["79014"])  # a share is never summed
        self.assertEqual(data["births"]["year"], 2025)
        self.assertEqual((data["births"]["by_unit"]["70017"], data["births"]["by_unit"]["79014"]), (138.0, 170.0))
        self.assertEqual(data["deaths"]["year"], 2025)
        self.assertEqual((data["deaths"]["by_unit"]["70017"], data["deaths"]["by_unit"]["79014"]), (349.0, 85.0))
        self.assertEqual(data["natural_increase"]["year"], 2025)
        self.assertEqual(data["natural_increase"]["by_unit"]["70017"], -10.0)
        self.assertIsNone(data["natural_increase"]["by_unit"]["79014"])  # a rate is never summed
        self.assertEqual(data["wages"]["year"], 2025)
        self.assertEqual((data["wages"]["net"]["70017"], data["wages"]["gross"]["70017"]), (81403.0, 112396.0))
        self.assertEqual((data["wages"]["net"]["79014"], data["wages"]["gross"]["79014"]), (None, None))  # a wage is never summed
        self.assertEqual(data["employment"]["year"], 2025)
        self.assertEqual(data["employment"]["by_unit"]["70017"], {"total": 4612.0, "by_nace": mock.ANY})
        self.assertEqual(data["employment"]["by_unit"]["70017"]["by_nace"]["A"], 65.0)
        self.assertEqual(data["employment"]["by_unit"]["79014"], {"total": 170.0, "by_nace": mock.ANY})
        self.assertEqual(data["employment"]["by_unit"]["79014"]["by_nace"]["A"], 17.0)
        self.assertEqual(data["life_expectancy"]["year"], 2025)
        self.assertEqual(data["life_expectancy"]["by_unit"]["70017"], {"m": 74.53, "f": 79.77})
        self.assertEqual(data["life_expectancy"]["by_unit"]["79014"], {"m": None, "f": None})
        self.assertEqual(data["status"], {"pop_estimate": {}, "births": {"80284": "M"}, "deaths": {}, "natural_increase": {},
                                          "wages": {}, "employment": {}, "life_expectancy": {}})
        self.assertEqual(sorted(data["vintage"]), ["births", "deaths", "employment", "life_expectancy", "natural_increase",
                                                   "pop_estimate", "wages"])
        self.assertIn("1991", data["vintage"]["pop_estimate"])
        self.assertIn("2025", data["vintage"]["wages"])
        self.assertEqual(data["_files"], ["pages/18010602.html", "pages/180304.html", "pages/2403040403.html", "pages/240205.html",
                                          "pages/18050202.html"] + [f"{n}.json" for n in rzs_db.SELECTIONS])

    def test_every_unit_is_a_key_and_kosovo_is_null_everywhere(self):
        data = rzs_db.RzsDatabase().process()
        scalar = [data["pop_65"]["by_unit"], data["births"]["by_unit"], data["deaths"]["by_unit"], data["natural_increase"]["by_unit"],
                  data["wages"]["net"], data["wages"]["gross"]]
        nested = [data["employment"]["by_unit"], data["life_expectancy"]["by_unit"]]
        for table in scalar:
            self.assertEqual(sorted(table), UNITS)
            self.assertTrue(all(table[u] is None for u in KOSOVO))
        for table in nested:
            self.assertEqual(sorted(table), UNITS)
            self.assertTrue(all(v is None for u in KOSOVO for v in leaves(table[u])))
        self.assertEqual(sorted(data["pop"]), UNITS)
        self.assertTrue(all(data["pop"][u] is None for u in KOSOVO))
        for unit in KOSOVO:
            self.assertEqual(sorted(data["employment"]["by_unit"][unit]["by_nace"]), [letter for _, letter, _ in srb.INDUSTRIES])

    def test_a_missing_or_empty_export_says_what_to_do(self):
        self.write("wages", [])
        with self.assertRaisesRegex(RuntimeError, "no records.*wages\\.json"):
            rzs_db.RzsDatabase().process()
        (self.raw / "rzs_db" / "wages.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "fetch rzs_db"):
            rzs_db.RzsDatabase().process()
