# Sites: wonders.json and resources.json

The two site layers of the Serbian build are driven by two curated CSV files in `pipeline/data/`. Each row is one
real site with the figure a public source publishes for it; the builders (`pipeline/build/resources.py`,
`pipeline/build/wonders.py`, placement shared in `pipeline/build/sites.py`) only project the coordinates onto the
map's hexes, move a site whose point falls on a foreign or water hex to the nearest Serbian land hex (preferring the
okrug named in the `okrug` column, else the okrug that owns the hex the point fell in) and publish the rules inside the
JSON (`types[].description`, `summary.note`, `rules[].text`).

Rules for both files:

* Serbian Latin only (the app generates Cyrillic); the builders refuse a Cyrillic cell.
* A figure nobody publishes is **empty**, never 0 – "null means no data".
* Every non-empty `value` has a `year` and a `source` id that appears in the tables below.
* Kosovo and Metohija (okruzi RS231–RS235) is in the frame: sites there have real coordinates and their okrug as
  `state`; `state_note` says that no statistics are published for them.
* `state` is the okrug id (`RS110`), `cbsa` the id of the city whose opštine contain the hex (what the frontend's
  `it.cbsa === city.id` reads), `county` the opština code.

## pipeline/data/resources_sites.csv → web/data/resources.json

Columns: `id, name, type, lon, lat, value, unit, year, detail, source, okrug`. 29 rows, 10 types.

What is mapped (the rule text in `types[].description`): EPS power plants of 100 MW and more (net output capacity of
the EPS Technical Report 2024), plants outside EPS (operator's installed capacity), wind farms from 50 MW, solar plants
from 5 MW, lignite mines and copper / lead-zinc mines with a published yearly quantity, and the Pančevo refinery.

| source id          | what                                                            | where from (URL)                                                 | year of figure | licence / note |
|--------------------|-----------------------------------------------------------------|------------------------------------------------------------------|----------------|----------------|
| EPS-TR2024         | net output capacity (MW) and production (GWh) per EPS plant      | https://www.eps.rs/eng/Documents/technicalreports/TEH_Godisnjak2024_web_en_.pdf (Tehnički godišnjak EPS 2024, "EPS installed capacities") | 2024 | public company report; EPS page https://www.eps.rs/cir/Pages/Kapaciteti-ElEn.aspx gives the installed (gross) totals |
| EPS-TR2024-COAL    | coal production per EPS branch (MB Kolubara 22 Mt, TE-KO Kostolac 9 Mt) | same PDF, "Coal production" chart (the last year of the series is 2024) | 2024 | chart labels; rounded to whole Mt |
| EPS-OIE            | VE Kostolac 66 MW installed, 7.2 GWh                            | https://www.eps.rs/cir/Poslovanje-EE/Pages/oie.aspx             | 2025 | EPS, "Obnovljivi izvori energije" |
| NIS-TETO           | TE-TO Pančevo: electric capacity up to 200 MW, in operation 2022 | https://www.nis.rs/project/te-to-pancevo ; https://www.geh-serbia.rs/sr-lat/te-to-pancevo/ | 2022 | Gazprom energoholding Srbija / NIS project pages |
| BLIC-PETKA         | SE Petka: installed capacity 9.75 MW, trial operation 14. 7. 2025 | https://www.blic.rs/biznis/privreda/pustena-u-probni-rad-solarna-elektrana-petka-u-kostolc ; https://www.srbija.gov.rs/vest/en/253987/ | 2025 | press (quoting EPS); EPS page gives 10 MW for Petka + Zaovine together |
| SR-WP-CIBUK        | Vetropark Čibuk 1: 158 MW, 57 turbines, Mramorak (Kovin), in operation Oct 2019 | https://sr.wikipedia.org/sr-el/Ветропарк_Чибук_I | 2019 | Wikipedia (CC BY-SA); coordinates from the infobox |
| SR-WP-KOVACICA     | Vetropark Kovačica: 104.5 MW, 38 turbines, Debeljača (Kovačica) | https://sr.wikipedia.org/sr-el/Ветропарк_Ковачица | 2019 | Wikipedia (CC BY-SA); coordinates from the infobox |
| USGS-MYB2024       | copper content of concentrates per mine (Veliki Krivelj 55,000 t, Majdanpek 52,000 t, Jama 8,000 t e, Čukaru Peki 170,000 t e); lead-zinc concentrates (Rudnik 5,000 t e, Veliki Majdan 4,000 t e); Lece ore 350,000 t e | https://www.usgs.gov/centers/national-minerals-information-center/serbia-and-montenegro-minerals-yearbook-2024 (Minerals Yearbook 2024, country report, tables of mineral facilities) | 2024 | USGS public domain; "e" = estimated |
| NIS-RNP            | Rafinerija nafte Pančevo: designed capacity 4.8 million t/yr; "Duboka prerada" opened Nov 2020 | https://www.nis.rs/ (Rafinerija nafte Pančevo) ; n1info / NIS press releases on the bottom-of-the-barrel project | 2020 | company information |
| NONE               | no published yearly figure (Ibarski rudnici) – value left empty | —                                                                | 2024 | PE za podzemno rudarstvo Resavica; only the 100-year total (15 Mt) is published |

Coordinates: EPS plants are placed at the plant site next to their town (Obrenovac, Veliki Crljeni, Svilajnac,
Kostolac, Novi Sad, Perućac, Mali Zvornik, Vlasina) – approximate to a few km, within the right opština; Đerdap 1 and 2
and the Kolubara basin use the English Wikipedia `geo` coordinates (CC0 via Wikidata); Čibuk 1 and Kovačica use the
Serbian Wikipedia infobox coordinates. The mines are placed at the mine (Bor complex: Krivelj, Majdanpek, Jama,
Čukaru Peki; Rudnik; Veliki Majdan; Lece; Baljevac; Drmno; Vreoci) – approximate to a few km.

## pipeline/data/wonders_sites.csv → web/data/wonders.json

Columns: `id, name, short, kind, rule, lon, lat, value, unit, year, listed_as, note, okrug`. 34 rows in five rules.

| rule id           | rows | ranked by                               | figures from |
|-------------------|------|-----------------------------------------|--------------|
| national_park     | 5    | area of the founding act (km²)          | wikipedia_sr_protected_areas |
| park_unit         | 4    | area (km²); a blank area ranks last     | wikipedia_sr_protected_areas, Golija from the English Wikipedia |
| research_university | 4  | students enrolled in 2024/25            | rzs_G20251236 |
| unesco_site       | 8    | alphabetical (curated)                  | unesco_whc_rs |
| landmark          | 13   | alphabetical (curated)                  | project_curated_landmarks |

| source id                      | what                                                        | where from (URL)                                              | licence / note |
|--------------------------------|-------------------------------------------------------------|---------------------------------------------------------------|----------------|
| wikipedia_sr_protected_areas   | area (ha) and year of proclamation of Đerdap (63,786.48 ha, 1974), Kopaonik (11,810 ha, 1981), Tara (24,991.82 ha, 1981), Šar-planina (22,805 ha, 1986), Fruška gora (26,672 ha, 1960), Uvac (7,543 ha, 1971), Đavolja varoš (67 ha, 1959) – each infobox cites the founding act | https://sr.wikipedia.org/sr-el/Nacionalni_park_Đerdap, …/Nacionalni_park_Kopaonik, …/Nacionalni_park_Tara, …/Nacionalni_park_Šar-planina, …/Nacionalni_park_Fruška_gora, …/Specijalni_rezervat_prirode_Uvac, …/Đavolja_varoš | Wikipedia, CC BY-SA 4.0; areas to be replaced by the Zavod za zaštitu prirode Srbije registers when fetched by a source module |
| wikipedia_en_coordinates       | Golija-Studenica "about 750 km²"; coordinates of all landmarks and UNESCO sites (`geo` spans) | https://en.wikipedia.org/wiki/Golija-Studenica and the pages named by the ids (Kalemegdan/Belgrade Fortress, Petrovaradin Fortress, Lepenski Vir, Vinča-Belo Brdo, Viminacium, Smederevo Fortress, Golubac Fortress, Bač Fortress, Manasija, Žiča, Mileševa, Ćele Kula, Gamzigrad, Stari Ras, Sopoćani, Studenica, Visoki Dečani, Patriarchate of Peć, Our Lady of Ljeviša, Gračanica, Đurđevi Stupovi (Ras), Stećci, Deliblatska Peščara, Kopaonik, Tara, Šar Mountains, Fruška Gora) | Wikipedia; coordinates CC0 via Wikidata |
| unesco_whc_rs                  | the five properties of Serbia on the World Heritage List and their inscription years (Stari Ras and Sopoćani 1979; Studenica 1986; Dečani 2004; Patriarchate of Peć, Ljeviška, Gračanica 2006; Gamzigrad-Romuliana 2007; Stećci 2016 – components 1504-026 Mramorje Perućac, 1504-027 Mramorje Rastište, 1504-028 Grčko groblje Hrta) | https://whc.unesco.org/en/statesparties/rs ; https://whc.unesco.org/en/list/ & https://whc.unesco.org/en/list/1504 | UNESCO WHC; names quoted as inscribed |
| rzs_G20251236                  | students enrolled in higher education 2024/25: University of Belgrade 89,299; Novi Sad 42,552; Niš 22,756; Kragujevac 13,996 (state universities 175,789 in total) | Republički zavod za statistiku, saopštenje br. 36, 29. 8. 2025 (G20251236): https://publikacije.stat.gov.rs/G2025/HtmlE/G20251236.html (PDF G20256005) | RZS open data; fetched here by hand, to be moved behind a source module |
| project_curated_landmarks     | the 13 landmarks are an editorial pick of monuments of exceptional importance (fortresses, archaeological sites, monasteries), no figures | this file | curated; positions from the English Wikipedia coordinates above |

Placement notes: Golubačka tvrđava, Kalemegdan (which would share Belgrade's city hex with the University of
Belgrade) and Ćele kula (Niš, the university's hex) stand on the next free hex; the University of Belgrade keeps
the city hex. Đurđevi stupovi near Novi Pazar is **not** a World Heritage site (the inscribed monastery of that name
is in Berane, Montenegro) – it is a landmark here, noted as being on UNESCO's tentative list. Deliblatska peščara has
no area in the source read, so its area is empty.

## Almanac texts

The Almanac page (`web/js/ui/pedia.js`) is owned by another agent. The Serbian Latin texts ready for it are the
`summary.note` of resources.json (what the totals mean), each `types[].description` (the rule of a resource type) and
each `rules[].text` of wonders.json (the rule of a wonder group); the tooltips in `web/js/ext/layers/tips.js` print the
same rule text under every site.

## Gaps

* Visitor numbers per national park are not published on one open page (only scattered press items), so
  `metrics.visits` is empty and parks rank by area.
* Research spending per university is not published; `rd_usd` is empty.
* The two lignite figures come from a chart of the EPS Technical Report (rounded to Mt); the per-mine figure for
  Kop Drmno is the whole TE-KO Kostolac branch, Ibarski rudnici has none.
* Čukaru Peki's 170,000 t (USGS, estimated) is far above the other Bor mines; kept as published, flagged here.
* Private solar plants and the NIS oil fields (Kikinda) have no published per-site capacity in the sources read.
* Golija-Studenica's area is approximate ("about 750 km²"); Deliblatska peščara's is empty.
* Mine and plant coordinates are approximate to a few km (the right opština, not the exact gate).
