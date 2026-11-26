"""pipeline/build/districts.py against synthetic NACE section counts: the location quotient, the rule, the null
fields, the badge, the opštine and the Serbian Latin strings. No network, no raw workbooks."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from pipeline.build import districts as D
from pipeline.core import srb

CYRILLIC = re.compile("[\u0400-\u04ff]")

# A national mix of jobs by NACE section (Serbia without KiM); shares chosen so the quotients are easy to read.
NATIONAL = {"A": 1000, "B": 100, "C": 2000, "D": 100, "E": 100, "F": 500, "G": 1500, "H": 400, "I": 400, "J": 300,
            "K": 300, "L": 50, "M": 600, "N": 300, "O": 700, "P": 1000, "Q": 1400, "R": 200, "S": 300, "total": 11950}


def city(total, **sections):
    """A city's jobs: the given sections; the rest is spread over the other sections in the national proportions
    (so an unnamed section keeps the national share and a quotient of 1) so that the total holds."""
    jobs = {k: 0 for _, k, _ in srb.INDUSTRIES}
    jobs.update(sections)
    rest = total - sum(sections.values())
    others = [n for n in jobs if n not in sections]
    weight = sum(NATIONAL[n] for n in others)
    acc = 0
    for i, n in enumerate(others):
        jobs[n] = round(rest * NATIONAL[n] / weight) if i < len(others) - 1 else rest - acc
        acc += jobs[n]
    jobs["total"] = total
    return jobs


class QuotientTests(unittest.TestCase):
    def test_lq_is_the_share_over_the_national_share_and_null_without_data(self):
        self.assertAlmostEqual(D.lq(400, 4000, 800, 8000), 1.0)
        self.assertAlmostEqual(D.lq(400, 4000, 400, 8000), 2.0)
        self.assertIsNone(D.lq(0, 4000, 100, 1000))
        self.assertIsNone(D.lq(10, 0, 100, 1000))
        self.assertIsNone(D.lq(10, 100, None, 1000))

    def test_excess_counts_the_jobs_above_the_norm(self):
        self.assertEqual(D.excess(400, 2.0), 200.0)
        self.assertEqual(D.excess(400, 1.0), 0.0)
        self.assertEqual(D.excess(400, 0.5), 0.0)
        self.assertEqual(D.excess(400, None), 0.0)


class RuleTests(unittest.TestCase):
    def test_a_district_needs_the_quotient_and_the_jobs_or_the_share(self):
        # 5 000 jobs: manufacturing 2 000 (40 % against 17.6 % nationally → ×2.28) and finance + real estate 200
        # (4 % against 2.9 % → ×1.4: below 500 jobs, but above the 1 % share)
        jobs = city(5000, C=2000, B=0, K=0, L=200)
        dists = D.evaluate(jobs, NATIONAL)
        self.assertEqual([d["id"] for d in dists], ["industrial_zone", "commercial_hub"])
        ind = dists[0]
        self.assertEqual(ind["emp"], 2000)
        self.assertEqual(ind["share"], 0.4)
        self.assertAlmostEqual(ind["lq"], 2.28, places=2)
        self.assertEqual(ind["strength"], round(D.excess(2000, 0.4 / (2100 / 11950))))
        self.assertEqual(ind["via"], "broad")
        # 50 000 jobs: 400 in finance and real estate = 0.8 % → ×1.4 but neither 500 jobs nor 1 % → no district
        jobs = city(50000, C=5000, B=0, K=0, L=400)
        self.assertEqual(D.evaluate(jobs, NATIONAL), [])

    def test_the_national_norm_makes_a_city_with_the_national_mix_have_no_district(self):
        jobs = {k: (v * 2 if k != "total" else v * 2) for k, v in NATIONAL.items()}
        self.assertEqual(D.evaluate(jobs, NATIONAL), [])

    def test_at_most_five_districts_ranked_by_strength(self):
        jobs = city(20000, C=6000, A=4000, F=2000, O=2000, P=2500, Q=1500, H=1000, D=300, E=300)
        dists = D.evaluate(jobs, NATIONAL)
        self.assertEqual(len(dists), 5)
        # manufacturing (+ the national remainder) leads, then agriculture ×2.4, construction, administration and
        # transport; energy and water (600 jobs, ×1.8) are sixth and drop off
        self.assertEqual([d["id"] for d in dists], ["industrial_zone", "agriculture", "construction", "government_plaza", "harbor"])
        strengths = [d["strength"] for d in dists]
        self.assertEqual(strengths, sorted(strengths, reverse=True))
        self.assertTrue(all(d["lq"] >= D.MIN_LQ for d in dists))

    def test_a_district_without_sections_is_never_evaluated(self):
        jobs = city(20000, H=4000, O=3000, M=3000, P=3000, J=2000)
        ids = [d["id"] for d in D.evaluate(jobs, NATIONAL)]
        self.assertIn("harbor", ids)
        self.assertNotIn("aerodrome", ids)
        self.assertNotIn("encampment", ids)
        self.assertEqual(D.evaluate(None, NATIONAL), [])
        self.assertEqual(D.evaluate({"total": 0}, NATIONAL), [])
        self.assertEqual(D.evaluate({"total": None}, NATIONAL), [])

    def test_unpublished_fields_are_null_never_zero(self):
        jobs = city(5000, C=2000, B=0)
        d = D.evaluate(jobs, NATIONAL)[0]
        for k in ("avg_pay", "sub", "sub_lq", "sub_emp", "sub_lower_bound", "suppressed", "lower_bound"):
            self.assertIsNone(d[k], k)
        for t in D.top_industries(jobs, NATIONAL):
            for k in ("avg_pay", "oty_pct", "suppressed", "lower_bound"):
                self.assertIsNone(t[k], k)
        self.assertIsNone(D.SPECIALTY_LQ)
        self.assertIsNone(D.COLLEGE_SHARE)


class BadgeTests(unittest.TestCase):
    def test_the_badge_district_is_the_extreme_one_else_the_strongest(self):
        dists = [{"id": "construction", "lq": 2.0, "share": 0.2, "strength": 100},
                 {"id": "industrial_zone", "lq": 6.5, "share": 0.35, "strength": 80},
                 {"id": "campus", "lq": 1.3, "share": 0.3, "strength": 120}]
        self.assertEqual(D.badge_district(dists)["id"], "industrial_zone")
        dists[1]["share"] = 0.02
        self.assertEqual(D.badge_district(dists)["id"], "campus")
        self.assertIsNone(D.badge_district([]))

    def test_badge_labels(self):
        ind = {"id": "industrial_zone", "lq": 2.4, "share": 0.3, "strength": 1}
        b = D.badge_for(ind, capital=False)
        self.assertEqual(b["label"], "Industrijski grad")
        self.assertEqual(b["district"], "industrial_zone")
        self.assertIn("rudarstvo i vađenje", b["text"])
        self.assertIn("×2,4", b["text"])
        self.assertEqual(D.badge_for({"id": "harbor", "lq": 2, "share": 0.1, "strength": 1}, False)["label"], "Logistički čvor")
        gov = {"id": "government_plaza", "lq": 2, "share": 0.1, "strength": 1}
        self.assertEqual(D.badge_for(gov, capital=True)["label"], "Prestonica")
        self.assertEqual(D.badge_for(gov, capital=False)["label"], "Grad uprave")
        d = D.badge_for(None, capital=True)
        self.assertEqual(d["label"], "Raznovrsna privreda")
        self.assertIsNone(d["district"])


class RecordTests(unittest.TestCase):
    def test_section_jobs_needs_every_section(self):
        row = {k: v for k, v in NATIONAL.items() if k != "total"}
        row["total"] = NATIONAL["total"]
        self.assertEqual(D.section_jobs(row)["C"], 2000)
        self.assertEqual(D.section_jobs(row)["total"], 11950)
        del row["S"]
        self.assertIsNone(D.section_jobs(row))
        self.assertIsNone(D.section_jobs(None))
        self.assertIsNone(D.section_jobs({"total": None, "A": 1}))

    def test_top_industries_are_the_most_specialised_above_the_threshold(self):
        jobs = city(50000, C=10000, B=0, L=2000, K=0)
        top = D.top_industries(jobs, NATIONAL)
        self.assertEqual(top[0]["naics"], "L")
        self.assertEqual(top[0]["emp"], 2000)
        self.assertEqual(len(top), D.TOP_INDUSTRIES)
        self.assertEqual([t["naics"] for t in top][:2], ["L", "C"])
        self.assertTrue(all(t["emp"] >= D.MIN_JOBS for t in top))  # 0 mining jobs is no "most specialised" industry
        self.assertEqual(D.top_industries(None, NATIONAL), [])

    def test_city_record_and_the_null_city(self):
        jobs = city(5000, C=2000, B=0)
        rec = D.city_record(jobs, ["10001", "10002"], NATIONAL, capital=False)
        self.assertEqual(rec["emp"], 5000)
        self.assertIsNone(rec["avg_pay"])
        self.assertEqual(rec["counties"], [2, 2])
        self.assertEqual(rec["badge"]["label"], "Industrijski grad")
        self.assertIsNone(D.city_record(None, ["25001"], NATIONAL, capital=False))


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = Path(self.tmp.name)
        cities = [{"id": "A", "counties": ["10001"], "capital": True}, {"id": "K", "counties": ["25001"]}]
        (self.web / "cities.json").write_text(json.dumps(cities), encoding="utf-8")
        recs = {"A": D.city_record(city(5000, C=2000, B=0, O=1500), ["10001"], NATIONAL, capital=True), "K": None}
        counties = {"10001": {"emp": 5000, "districts": [["industrial_zone", 2.39, 2000]]}}
        self.doc = D.make_doc(NATIONAL, recs, counties)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, doc):
        (self.web / "districts.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def test_document_shape_and_serbian_latin(self):
        doc = self.doc
        self.assertEqual(list(doc), ["version", "vintage", "year", "sources", "rule", "catalog", "industries", "national", "cities", "counties"])
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["year"], 2022)
        self.assertEqual(doc["sources"], ["census"])
        self.assertEqual(doc["national"], {"emp": 11950, "avg_pay": None})
        self.assertEqual(doc["rule"]["max_per_city"], 5)
        self.assertEqual(doc["rule"]["min_lq"], 1.25)
        self.assertIsNone(doc["rule"]["specialty_lq"])
        self.assertFalse(doc["rule"]["harbor_needs_water"])
        self.assertEqual(doc["cities"]["A"]["badge"]["label"], "Prestonica")  # the capital with an administration district
        self.assertIsNone(doc["cities"]["K"])
        self.assertEqual(doc["counties"]["10001"]["districts"], [["industrial_zone", 2.39, 2000]])
        ids = [c["id"] for c in doc["catalog"]]
        self.assertEqual(ids[:9], ["campus", "commercial_hub", "industrial_zone", "harbor", "theater_square", "entertainment_complex",
                                   "aerodrome", "government_plaza", "encampment"])
        self.assertEqual(ids[9:], ["aqueduct", "agriculture", "construction"])
        for c in doc["catalog"]:
            for k in ("id", "name", "icon", "color", "naics", "own", "sub", "badge", "description", "caveat"):
                self.assertIn(k, c)
            self.assertIsNone(c["own"])
            self.assertIsNone(c["sub"])
            self.assertFalse(CYRILLIC.search(c["name"] + c["description"] + (c["caveat"] or "")), c["id"])
            if c["naics"]:
                self.assertTrue(set(c["naics"]) <= {n for _, n, _ in srb.INDUSTRIES})
        self.assertEqual({c["icon"] for c in doc["catalog"]}, {c["icon"] for c in D.CATALOG})
        self.assertEqual(len(doc["industries"]), 19)
        self.assertEqual(doc["industries"]["C"], {"title": srb.INDUSTRY_NAMES["manufacturing"], "us_emp": 2000})
        for t in (doc["vintage"], doc["rule"]["text"], doc["rule"]["county_note"]):
            self.assertFalse(CYRILLIC.search(t), t)
        self.assertIn("Popis 2022", doc["rule"]["text"])
        self.assertNotIn(" the ", doc["rule"]["text"])

    def test_check_passes_and_fails_on_a_broken_file(self):
        self.write(self.doc)
        levels = D.check(self.web)
        self.assertEqual([l for l, _ in levels], ["PASS", "NOTE"])
        self.assertIn("2 cities", levels[0][1])
        self.write({**copy.deepcopy(self.doc), "version": 2})
        self.assertEqual(D.check(self.web)[0][0], "FAIL")
        doc = copy.deepcopy(self.doc)
        doc["cities"]["A"]["districts"] = doc["cities"]["A"]["districts"] * 6
        self.write(doc)
        self.assertEqual(D.check(self.web)[0][0], "FAIL")
        doc = copy.deepcopy(self.doc)
        doc["cities"]["ZZ"] = doc["cities"]["A"]
        self.write(doc)
        self.assertTrue(any(l == "FAIL" and "ZZ" in m for l, m in D.check(self.web)))
        (self.web / "districts.json").write_text("{", encoding="utf-8")
        self.assertEqual(D.check(self.web)[0][0], "FAIL")
        self.assertEqual(D.check(Path(self.tmp.name) / "nowhere")[0][0], "NOTE")  # not built yet: a note, not a failure


class SharedConstants(unittest.TestCase):
    def test_every_section_has_its_own_census_label(self):
        self.assertEqual(len(srb.CENSUS_NACE_FRAGMENTS), len(srb.INDUSTRIES))
        self.assertEqual(len(set(srb.CENSUS_NACE_FRAGMENTS)), len(srb.INDUSTRIES))
        self.assertEqual([n for _, n, _ in srb.INDUSTRIES], list("ABCDEFGHIJKLMNOPQRS"))


if __name__ == "__main__":
    unittest.main()
