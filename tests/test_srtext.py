import re
import unittest
from pathlib import Path

from pipeline.core import srtext

WEB_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "i18n" / "transliterate.js"

GLOSSARY = {
    "prinos": "принос", "sočivo": "сочиво", "heks": "хекс", "građani": "грађани", "kvart": "кварт",
    "čudo": "чудо", "savetnik": "саветник", "Almanah": "Алманах", "resurs": "ресурс", "poboljšanje": "побољшање",
    "okrug": "округ", "opština": "општина", "naselje": "насеље", "nema podataka": "нема података",
    "izvor": "извор", "prestonica": "престоница", "Proizvodnja": "Производња", "Nauka": "Наука",
    "Kultura": "Култура", "Zlato": "Злато", "Hrana": "Храна",
}
HARD_CASES = {
    "Ljubljana": "Љубљана", "injekcija": "ињекција", "Njujork": "Њујорк", "gde": "где", "đerdap": "ђердап",
    "Đerdap": "Ђердап", "džamija": "џамија", "LJUBAV": "ЉУБАВ", "Novi Sad": "Нови Сад", "Niš": "Ниш",
    "Beograd": "Београд", "Šumadija": "Шумадија", "Vojvodina": "Војводина", "Mađarska": "Мађарска",
    "Hrvatska": "Хрватска", "Zvečan": "Звечан", "Kosovsko-mitrovačka": "Косовско-митровачка", "Severna Makedonija": "Северна Македонија",
}


class ToCyrillic(unittest.TestCase):
    def test_glossary_terms(self):
        for latin, cyrillic in GLOSSARY.items():
            with self.subTest(latin):
                self.assertEqual(srtext.to_cyrillic(latin), cyrillic)

    def test_digraphs_and_hard_cases(self):
        for latin, cyrillic in HARD_CASES.items():
            with self.subTest(latin):
                self.assertEqual(srtext.to_cyrillic(latin), cyrillic)

    def test_protected_names_stay_latin(self):
        self.assertEqual(srtext.to_cyrillic("Izvor: Eurostat, NACE i OpenStreetMap."), "Извор: Eurostat, NACE и OpenStreetMap.")
        self.assertEqual(srtext.to_cyrillic("Podaci ESA WorldCover 2021"), "Подаци ESA WorldCover 2021")
        self.assertEqual(srtext.to_cyrillic("MESA"), "МЕСА")  # "ESA" inside a word is not the agency

    def test_serbian_acronyms_follow_the_script(self):
        self.assertEqual(srtext.to_cyrillic("RZS i BDP"), "РЗС и БДП")

    def test_digits_and_punctuation_untouched(self):
        self.assertEqual(srtext.to_cyrillic("123 € (5 km)"), "123 € (5 км)")  # only letters change

    def test_empty(self):
        self.assertEqual(srtext.to_cyrillic(""), "")
        self.assertIsNone(srtext.to_cyrillic(None))


class ToLatin(unittest.TestCase):
    def test_round_trip(self):
        for latin in {**GLOSSARY, **HARD_CASES}:
            with self.subTest(latin):
                self.assertEqual(srtext.to_latin(srtext.to_cyrillic(latin)), latin)

    def test_capital_digraphs_in_all_caps_words(self):
        self.assertEqual(srtext.to_latin("ЉУБАВ"), "LJUBAV")
        self.assertEqual(srtext.to_latin("ЊЕГОШ"), "NJEGOŠ")
        self.assertEqual(srtext.to_latin("ЏАЗ"), "DŽAZ")

    def test_census_names(self):
        self.assertEqual(srtext.to_latin("Нишавска област"), "Nišavska oblast")
        self.assertEqual(srtext.to_latin("Косовско-митровачка област"), "Kosovsko-mitrovačka oblast")
        self.assertEqual(srtext.to_latin("Вражegrбац"), "Vražegrbac")


class FoldKey(unittest.TestCase):
    def test_both_scripts_and_missing_diacritics_fold_together(self):
        keys = {srtext.fold_key(s) for s in ("Niš", "nis", "NIS", "Ниш", "НИШ", "  nis ", "nisch")}
        self.assertEqual(keys, {"nis", "nisch"})

    def test_examples(self):
        self.assertEqual(srtext.fold_key("Niš"), "nis")
        self.assertEqual(srtext.fold_key("Kosovsko-mitrovačka"), "kosovsko mitrovacka")
        self.assertEqual(srtext.fold_key("Đerdap"), "djerdap")
        self.assertEqual(srtext.fold_key("Nišavski okrug"), "nisavski okrug")

    def test_none(self):
        self.assertEqual(srtext.fold_key(None), "")


class OkrugName(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(srtext.okrug_name("Nišavska oblast"), "Nišavski okrug")
        self.assertEqual(srtext.okrug_name("Beogradska oblast"), "Beogradski okrug")
        self.assertEqual(srtext.okrug_name("Kosovsko-mitrovačka oblast"), "Kosovsko-mitrovački okrug")
        self.assertEqual(srtext.okrug_name("Pećka oblast"), "Pećki okrug")


class MirrorWithWeb(unittest.TestCase):
    """web/js/i18n/transliterate.js must protect exactly the names the pipeline protects."""

    def test_protected_lists_agree(self):
        if not WEB_JS.exists():
            self.skipTest("web/js/i18n/transliterate.js not written yet")
        text = WEB_JS.read_text(encoding="utf-8")
        m = re.search(r"PROTECTED\s*=\s*\[((?:\s*\"[^\"]+\"\s*,?)+)\s*\]\s*;", text)
        self.assertIsNotNone(m, "PROTECTED array not found in transliterate.js")
        js = set(re.findall(r"\"([^\"]+)\"", m.group(1)))
        self.assertEqual(js, set(srtext.PROTECTED))


if __name__ == "__main__":
    unittest.main()
