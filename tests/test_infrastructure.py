"""Tile improvements: hex-line sampling, the Serbian-land link rule, road classes and rail tiers, site placement,
the null rule and the Serbian Latin rule text — all on a tiny synthetic map, no network."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from pipeline.build import infrastructure as infra
from pipeline.core.hexgrid import HexGrid

R = 10.0  # km; the synthetic map's map units are km, so the "projection" is the identity
GRID = HexGrid(R, 12, 10)
WATER_ROW, FOREIGN_ROW = 5, 6  # rows 0-4 are Serbian land, row 5 water, rows 6-9 foreign land
CYRILLIC = re.compile(r"[А-Яа-яЂђЈјЉљЊњЋћЏџ]")


def proj(lon, lat):
    return lon, lat


def cell(col, row):
    return GRID.index(col, row)


def row_y(row):
    return GRID.center(0, row)[1]


def river_point():
    """A point on the river hex (3, WATER_ROW), nudged towards its upper-left land neighbour (3, 4) so the nearest
    land hex is unambiguous (the hex centre is equidistant from (3, 4) and (4, 4))."""
    x, y = GRID.center(3, WATER_ROW)
    return x - 4.0, y


def make_world():
    """Land rows 0-4 split into two municipalities (col < 6 → "70017", else "70033") of one okrug."""
    owner, county = [], []
    for c in range(GRID.size):
        col, row = GRID.col_row(c)
        if row < WATER_ROW:
            owner.append(0)
            county.append(0 if col < 6 else 1)
        else:
            owner.append(-1 if row == WATER_ROW else -2)
            county.append(-1)
    return {"grid": GRID.to_dict(), "owner": owner, "county": county, "counties": ["70017", "70033"], "states": ["RS216"]}


# "70017" is a city of its own; "70033" belongs to two cities, the more populous one (not the lower id) represents it
CITIES = [
    {"id": "79014", "name": "Beograd", "counties": ["70033"], "population": 1000},
    {"id": "79022", "name": "Niš", "counties": ["70033"], "population": 5000},
    {"id": "70017", "name": "Aleksandrovac", "counties": ["70017"], "population": 20000},
    {"id": "80284", "name": "Novi Sad", "counties": ["80284"], "population": 300000, "x": GRID.center(5, 2)[0], "y": row_y(2)},
]


def road(pts, *, label=None, label2=None, name=None, sr=5, expressway=0, level="E", kind="Major Highway"):
    return {"lines": [pts], "label": label, "label2": label2, "name": name, "scalerank": sr, "expressway": expressway,
            "level": level, "type": kind}


def rail(pts, sr):
    return {"lines": [pts], "scalerank": sr}


def horizontal(row, c0, c1):
    y = row_y(row)
    return [(GRID.center(c0, row)[0], y), (GRID.center(c1, row)[0], y)]


def locator():
    return infra.Locator(make_world(), GRID, proj, CITIES)


class HexLineTest(unittest.TestCase):
    def test_hex_walk_stays_on_neighbours(self):
        a, b = cell(1, 1), cell(5, 3)
        path = infra.hex_walk(GRID, a, b)
        self.assertEqual((path[0], path[-1]), (a, b))
        self.assertEqual(len(path) - 1, infra.hex_distance(GRID, a, b))
        for u, v in zip(path, path[1:]):
            self.assertIn(v, GRID.neighbours(u))

    def test_horizontal_line_has_no_zigzag(self):
        runs = infra.sample_cells(GRID, horizontal(2, 1, 8))
        self.assertEqual(runs, [[cell(c, 2) for c in range(1, 9)]])
        links = infra.links_of(GRID, runs[0])
        self.assertEqual(links, [(cell(c, 2), cell(c + 1, 2)) for c in range(1, 8)])

    def test_keep_breaks_runs(self):
        runs = infra.sample_cells(GRID, horizontal(2, 1, 8), keep=lambda x, y: x < 60.0 or x > 90.0)
        self.assertEqual([[GRID.col_row(c) for c in r] for r in runs],
                         [[(1, 2), (2, 2), (3, 2)], [(5, 2), (6, 2), (7, 2), (8, 2)]])

    def test_straighten_clips_corners(self):
        zigzag = [cell(2, 2), cell(3, 1), cell(3, 2)]  # a line that only clipped the corner of (3, 1)
        self.assertEqual(infra.straighten(GRID, zigzag), [cell(2, 2), cell(3, 2)])
        self.assertIn(cell(3, 2), GRID.neighbours(cell(2, 2)))


class LinkRuleTest(unittest.TestCase):
    def setUp(self):
        self.world = make_world()
        self.owner = self.world["owner"]

    def test_links_need_serbian_land_and_never_foreign(self):
        # a road from Serbian land (row 4) across the river (row 5) into foreign land (row 6): only the first link stays
        crossing = road([(55.0, row_y(4)), (55.0, row_y(6))], label="E75", sr=5)
        links = infra.build_roads(GRID, proj, self.owner, {"roads": [crossing], "rail": []})
        self.assertEqual([(a, b) for a, b, *_ in links], [(cell(3, 4), cell(3, 5))])
        self.assertEqual(links[0][2:], [1, "E75"])

    def test_links_in_water_or_foreign_land_alone_are_dropped(self):
        features = {"roads": [road(horizontal(WATER_ROW, 1, 8), label="E75"), road(horizontal(FOREIGN_ROW, 1, 8), label="E75")],
                    "rail": [rail(horizontal(WATER_ROW, 1, 8), 4), rail(horizontal(FOREIGN_ROW, 1, 8), 4)]}
        self.assertEqual(infra.build_roads(GRID, proj, self.owner, features), [])
        self.assertEqual(infra.build_rail(GRID, proj, self.owner, features), [])

    def test_every_link_is_between_neighbours_with_serbian_land(self):
        features = {"roads": [road(horizontal(3, 0, 11), label="E70", sr=6),
                             road([(0.0, 0.0), (180.0, 75.0)], label="E75", sr=5, expressway=1),
                             road([(0.0, 75.0), (180.0, 0.0)], label="E763", sr=6)],
                    "rail": [rail([(0.0, 45.0), (180.0, 90.0)], 4), rail(horizontal(7, 0, 11), 7)]}
        for links, ncls in ((infra.build_roads(GRID, proj, self.owner, features), 2), (infra.build_rail(GRID, proj, self.owner, features), 2)):
            self.assertTrue(links)
            for link in links:
                a, b, cls = link[:3]
                self.assertIn(b, GRID.neighbours(a))
                self.assertLess(a, b)
                self.assertTrue(infra.link_ok(self.owner, a, b))
                self.assertTrue(0 <= cls < ncls)
                self.assertFalse(self.owner[a] < 0 and self.owner[b] < 0)


class ClassTest(unittest.TestCase):
    def test_road_classes(self):
        self.assertEqual(infra.road_class({"expressway": 1, "scalerank": 3, "level": "E"}), 0)  # auto-put
        self.assertEqual(infra.road_class({"expressway": 1, "scalerank": 6, "level": "E"}), 1)  # an E-road flagged beyond the motorway ranks
        self.assertEqual(infra.road_class({"expressway": 0, "scalerank": 6, "level": "E"}), 1)  # magistralni put
        self.assertIsNone(infra.road_class({"expressway": 1, "scalerank": 7, "level": "E"}))  # local E-roads are left out
        self.assertIsNone(infra.road_class({"expressway": 0, "scalerank": 7, "level": "E"}))
        self.assertIsNone(infra.road_class({"expressway": 0, "scalerank": 4, "level": "Other", "type": "Secondary Highway"}))
        self.assertIsNone(infra.road_class({"expressway": 0, "scalerank": None, "level": "E"}))  # unknown rank: left out, not guessed
        self.assertEqual([c["name"] for c in infra.ROAD_CLASSES], ["Auto-put", "Magistralni put"])

    def test_rail_tiers(self):
        self.assertEqual([infra.rail_tier(sr) for sr in (4, 5, 6, 7, 8, None)], [0, 0, 1, 1, None, None])
        self.assertEqual([t["name"] for t in infra.RAIL_TIERS], ["Glavna pruga", "Sporedna pruga"])

    def test_motorway_wins_a_shared_link_and_names_are_latin(self):
        owner = make_world()["owner"]
        features = {"roads": [
            road(horizontal(2, 1, 6), label="E75", sr=6),  # the E-road on its own
            road(horizontal(2, 1, 6), label="E75", label2="1", sr=5, expressway=1),  # the motorway along the same hexes
            road(horizontal(2, 1, 6), label="E761", label2="5", sr=6),  # a second E-road sharing the link
            road(horizontal(2, 1, 6), label="Ауто-пут", sr=5, expressway=1),  # Cyrillic label
        ], "rail": []}
        links = infra.build_roads(GRID, proj, owner, features)
        self.assertTrue(links)
        self.assertTrue(all(l[2] == 0 for l in links))
        self.assertEqual({l[3] for l in links}, {"E75 / 1"})  # lowest class, then the shortest E number
        self.assertFalse(any(CYRILLIC.search(l[3] or "") for l in links))

    def test_lowest_european_number_names_a_shared_main_road(self):
        owner = make_world()["owner"]
        features = {"roads": [road(horizontal(3, 1, 6), label="E761", label2="5", sr=6), road(horizontal(3, 1, 6), label="E75", label2="M1", sr=6)],
                    "rail": []}
        self.assertEqual({l[3] for l in infra.build_roads(GRID, proj, owner, features)}, {"E75 / M1"})

    def test_rail_tiers_in_links(self):
        owner = make_world()["owner"]
        features = {"roads": [], "rail": [rail(horizontal(2, 1, 6), 4), rail(horizontal(3, 1, 6), 6), rail(horizontal(4, 1, 6), 8)]}
        tiers = {tuple(l[:2]): l[2] for l in infra.build_rail(GRID, proj, owner, features)}
        self.assertEqual({(cell(c, 2), cell(c + 1, 2)) for c in range(1, 6)} - set(tiers), set())
        self.assertTrue(all(tiers[cell(c, 2), cell(c + 1, 2)] == 0 for c in range(1, 6)))
        self.assertTrue(all(tiers[cell(c, 3), cell(c + 1, 3)] == 1 for c in range(1, 6)))
        row4 = {cell(c, 4) for c in range(GRID.cols)}
        self.assertFalse(any(row4 & set(t) for t in tiers))  # rank 8 is left out


class SiteTest(unittest.TestCase):
    def setUp(self):
        self.loc = locator()

    def test_land_point_is_placed_on_its_own_hex(self):
        x, y = GRID.center(2, 3)
        at = self.loc.place(x, y)
        assert at is not None
        self.assertEqual((at["cell"], at["county"], at["cbsa"], at["state"]), (cell(2, 3), "70017", "70017", "RS216"))
        self.assertEqual((at["x"], at["y"]), (round(x, 1), round(y, 1)))
        self.assertEqual(self.loc.city_name(at), "Aleksandrovac")

    def test_county_without_its_own_city_takes_the_most_populous_one(self):
        x, y = GRID.center(8, 3)  # col >= 6: municipality "70033"
        at = self.loc.place(x, y)
        self.assertEqual((at["county"], at["cbsa"]), ("70033", "79022"))
        self.assertEqual(self.loc.city_name(at), "Niš")

    def test_water_point_takes_the_nearest_land_hex_within_two_rings(self):
        x, y = river_point()  # a river hex
        at = self.loc.place(x, y)
        assert at is not None
        self.assertEqual(at["cell"], cell(3, 4))
        self.assertEqual((at["x"], at["y"]), (round(x, 1), round(y, 1)))  # the marker stays where the port is
        self.assertGreaterEqual(self.loc.owner[at["cell"]], 0)
        far = self.loc.place(x, row_y(WATER_ROW + 1))  # a foreign hex two rings away from land
        assert far is not None
        self.assertEqual(far["cell"], cell(3, 4))
        self.assertIsNone(self.loc.place(x, row_y(WATER_ROW + 2)))  # three rings: no placement
        self.assertEqual(self.loc.land_cell(-500.0, -500.0), -1)

    def test_ports_rank_tonnage_and_nulls(self):
        places = [{"name": "Лука А", "name_lat": "Luka A", "fclass": "village", "population": 10, "lon": GRID.center(2, 3)[0], "lat": row_y(3)},
                  {"name": "Luka A", "name_lat": "Luka A", "fclass": "town", "population": 500, "lon": GRID.center(4, 2)[0], "lat": row_y(2)},
                  {"name": "Luka B", "name_lat": "Luka B", "fclass": "town", "population": 500, "lon": river_point()[0], "lat": row_y(WATER_ROW)}]
        ports = infra.build_ports(self.loc, {"year": 2025, "ports": [
            {"name": "Luka B", "tons": 30}, {"name": "Luka A", "tons": 50}, {"name": "Nigde", "tons": 10}]}, places)
        by_id = {p["id"]: p for p in ports}
        self.assertEqual(set(by_id), {"RS-luka-a", "RS-luka-b"})  # a port nothing places is left out, not invented
        a, b = by_id["RS-luka-a"], by_id["RS-luka-b"]
        self.assertEqual((a["rank"], b["rank"]), (1, 2))
        self.assertEqual((a["tons"], a["year"], a["type"]), (50, 2025, "inland"))
        self.assertEqual((a["cell"], b["cell"]), (cell(4, 2), cell(3, 4)))  # the town point wins over the village; the river point moves to land
        for p in ports:
            for k in ("domestic", "foreign", "imports", "exports"):
                self.assertIsNone(p[k])  # not published: null, never 0
            self.assertEqual(p["state"], "RS216")
            self.assertIn(p["county"], ("70017", "70033"))

    def test_port_falls_back_to_the_city_marker(self):
        ports = infra.build_ports(self.loc, {"year": 2025, "ports": [{"name": "Novi Sad", "tons": 5}]}, [])
        x, y = GRID.center(5, 2)
        self.assertEqual(((ports[0]["x"], ports[0]["y"]), ports[0]["cell"], ports[0]["cbsa"]), ((round(x, 1), round(y, 1)), cell(5, 2), "70017"))

    def test_airports_hubs_and_nulls(self):
        airports = {"airports": [{"icao": "LYBE", "lon": GRID.center(2, 3)[0], "lat": row_y(3)},
                                 {"icao": "LYKV", "lon": GRID.center(8, 3)[0], "lat": row_y(3)},
                                 {"icao": "LYUZ", "lon": river_point()[0], "lat": row_y(WATER_ROW)},
                                 {"icao": "LYBT", "lon": GRID.center(2, 1)[0], "lat": row_y(1)}]}
        traffic = {"LYBE": {"2025": 8913522, "2024": 8367395}, "LYKV": {"2025": 14713}, "LYUZ": {"2025": None, "2024": None}}
        out = infra.build_airports(self.loc, airports, traffic, latest_year=2025)
        self.assertEqual([a["id"] for a in out], ["LYBE", "LYKV", "LYUZ", "LYBT"])  # busiest first, nulls last
        be, kv, uz, bt = out
        self.assertEqual((be["hub"], be["enplanements"], be["enplanements_prev"], be["year"], be["city"], be["cbsa"]),
                         ("L", 8913522, 8367395, 2025, "Aleksandrovac", "70017"))
        self.assertEqual((kv["hub"], kv["enplanements"], kv["enplanements_prev"]), ("S", 14713, None))
        self.assertEqual((kv["county"], kv["cbsa"], kv["city"], kv["state"]), ("70033", "79022", "Niš", "RS216"))
        self.assertEqual((uz["hub"], uz["enplanements"], uz["enplanements_prev"], uz["year"]), ("N", None, None, 2025))
        self.assertEqual((bt["hub"], bt["enplanements"]), ("N", None))
        self.assertEqual(uz["cell"], cell(3, 4))  # a point on water takes the nearest land hex
        for a in out:
            self.assertIsNone(a["cargo_lbs"])  # cargo is not published as data: null, never 0

    def test_hub_thresholds(self):
        self.assertEqual([infra.hub_of(n) for n in (1_000_000, 999_999, 100_000, 99_999, 1, 0, None)], ["L", "M", "M", "S", "S", "N", "N"])


class RulesTest(unittest.TestCase):
    def test_rule_text_is_serbian_latin_and_names_the_nulls(self):
        texts = list(infra.RULES.values()) + [c["name"] for c in infra.ROAD_CLASSES + infra.RAIL_TIERS] + list(infra.HUBS.values())
        for t in texts:
            self.assertFalse(CYRILLIC.search(t), t)
        self.assertIn("null", infra.RULES["ports"])
        self.assertIn("null", infra.RULES["airports"])
        self.assertEqual(set(infra.RULES), {"roads", "rail", "ports", "airports"})


class CheckTest(unittest.TestCase):
    def write(self, web, doc, owner):
        (web / "world.json").write_text(json.dumps({"grid": GRID.to_dict(), "owner": owner, "counties": [{"geoid": "70017"}]}), encoding="utf-8")
        if doc is not None:
            (web / "infrastructure.json").write_text(json.dumps(doc), encoding="utf-8")

    def good_doc(self):
        world = make_world()
        features = {"roads": [road(horizontal(2, 1, 6), label="E75", sr=5, expressway=1)], "rail": [rail(horizontal(3, 1, 6), 4)]}
        loc = infra.Locator(world, GRID, proj, CITIES)
        return {"version": 1, "vintage": {}, "sources": ["natural_earth_roads"], "road_classes": infra.ROAD_CLASSES,
                "rail_tiers": infra.RAIL_TIERS, "hubs": infra.HUBS, "rules": infra.RULES,
                "roads": infra.build_roads(GRID, proj, world["owner"], features),
                "rail": infra.build_rail(GRID, proj, world["owner"], features),
                "ports": infra.build_ports(loc, {"year": 2025, "ports": [{"name": "Luka A", "tons": 50}]},
                                           [{"name": "Luka A", "name_lat": "Luka A", "fclass": "town", "lon": GRID.center(4, 2)[0], "lat": row_y(2)}]),
                "airports": infra.build_airports(loc, {"airports": [{"icao": "LYBE", "lon": GRID.center(2, 3)[0], "lat": row_y(3)}]},
                                                 {"LYBE": {"2025": 8913522}}, latest_year=2025)}

    def levels(self, results):
        return {level for level, _ in results}

    def test_missing_file_is_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(infra.check(Path(tmp))[0][0], "NOTE")

    def test_good_document_passes(self):
        doc = self.good_doc()
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), doc, make_world()["owner"])
            results = infra.check(Path(tmp))
            self.assertFalse(self.levels(results) & {"FAIL", "WARN"}, results)
            self.assertEqual(sum(1 for lv, _ in results if lv == "PASS"), 4)

    def test_violations_fail(self):
        doc = self.good_doc()
        doc["roads"].append([cell(1, 1), cell(1, 3), 0, "E75"])  # not neighbours
        doc["rail"].append([cell(1, 1), cell(1, 2), 5])  # no such tier
        doc["roads"].append([cell(7, 5), cell(8, 5), 0, "E75"])  # water only
        doc["ports"][0]["tons"] = 0  # an invented zero where nothing was published
        doc["airports"][0]["cbsa"] = "00000"
        doc["airports"].append(dict(doc["airports"][0]))  # duplicate id
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), doc, make_world()["owner"])
            failed = [msg for lv, msg in infra.check(Path(tmp)) if lv == "FAIL"]
            self.assertTrue(any("roads" in m for m in failed), failed)
            self.assertTrue(any("rail" in m for m in failed), failed)
            self.assertTrue(any("airports" in m for m in failed), failed)

    def test_site_on_foreign_land_fails(self):
        doc = self.good_doc()
        doc["ports"][0]["cell"] = cell(1, FOREIGN_ROW)
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), doc, make_world()["owner"])
            self.assertTrue(any(lv == "FAIL" and "ports" in msg for lv, msg in infra.check(Path(tmp))))


if __name__ == "__main__":
    unittest.main()
