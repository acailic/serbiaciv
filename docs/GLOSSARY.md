# Rečnik / Glossary

Binding vocabulary for everything a user sees. Serbian Latin is what code and data are written in; Cyrillic is
generated from it by `web/js/i18n/transliterate.js` (mirrored by `pipeline/core/srtext.py`), so nobody translates
twice. Change a term here first, then in the code.

Civ vocabulary stays Civ vocabulary: a yield is a "prinos", a lens is a "sočivo". Administrative words follow the
Statistical Office of Serbia (RZS).

## Game concepts

| English (upstream) | Serbian Latin | Serbian Cyrillic | Note |
|---|---|---|---|
| yield | prinos | принос | plural: prinosi |
| Food | Hrana | Храна | |
| Production | Proizvodnja | Производња | |
| Gold | Zlato | Злато | it is GDP |
| Science | Nauka | Наука | |
| Culture | Kultura | Култура | |
| lens | sočivo | сочиво | plural: sočiva |
| tile, hex | heks | хекс | plural: heksovi |
| terrain | teren | терен | |
| flat | ravnica | равница | |
| hills | brdovit teren | брдовит терен | adjective form "brdoviti" |
| mountains | planine | планине | |
| peaks | vrhovi | врхови | |
| forest | šuma | шума | |
| cropland | njive | њиве | |
| pasture, meadow | livade i pašnjaci | ливаде и пашњаци | one class |
| shrubland | žbunje | жбуње | |
| wetland | močvare | мочваре | |
| urban | gradsko | градско | "gradsko zemljište" |
| river | reka | река | |
| lake | jezero | језеро | |
| resource | resurs | ресурс | |
| improvement | poboljšanje | побољшање | |
| road | put | пут | |
| railway | pruga | пруга | |
| airport | aerodrom | аеродром | |
| port | luka | лука | |
| power plant | elektrana | електрана | |
| mine | rudnik | рудник | |
| wonder | čudo | чудо | plural: čuda |
| national park | nacionalni park | национални парк | |
| wonder of the world | čudo sveta | чудо света | |
| citizens | građani | грађани | |
| district (of a city) | kvart | кварт | deliberately not "okrug" |
| City View | Pregled grada | Преглед града | |
| advisor | savetnik | саветник | |
| Explorer | Istraživač | Истраживач | |
| Almanac | Almanah | Алманах | |
| trade route | trgovinski put | трговински пут | not in M1 |

## Administrative units (RZS terms)

| English (upstream) | Serbian Latin | Serbian Cyrillic | Note |
|---|---|---|---|
| nation, country | Republika Srbija | Република Србија | top bar short form: Srbija |
| state | okrug | округ | RZS and Eurostat call the same 30 areas "oblast"; the UI says okrug, the Almanac says they are the same |
| county | opština | општина | a unit RZS calls "grad" is shown as "grad" |
| city | grad | град | |
| settlement | naselje | насеље | |
| capital | prestonica | престоница | |
| region | region | регион | NUTS-2 |

## Data words

| English (upstream) | Serbian Latin | Serbian Cyrillic | Note |
|---|---|---|---|
| population | stanovništvo | становништво | a number: "broj stanovnika" |
| GDP | BDP | БДП | spelled out: bruto domaći proizvod |
| average net wage | prosečna neto zarada | просечна нето зарада | |
| unemployment rate | stopa nezaposlenosti | стопа незапослености | |
| employed | zaposleni | запослени | |
| estimate | procena | процена | marked with ≈ |
| share | udeo | удео | |
| source | izvor | извор | |
| no data | nema podataka | нема података | |
| Turn (top bar) | Godina | Година | the top bar shows the year, not a turn |
| vintage | izdanje podataka | издање података | e.g. "Popis 2022" |

## Controls and chrome

| English (upstream) | Serbian Latin | Serbian Cyrillic |
|---|---|---|
| Search | Pretraga | Претрага |
| Share | Podeli | Подели |
| Help | Pomoć | Помоћ |
| Map | Mapa | Мапа |
| Resources | Resursi | Ресурси |
| Terrain | Teren | Терен |
| Legend | Legenda | Легенда |
| Close | Zatvori | Затвори |
| Open the Almanac | Otvori Almanah | Отвори Алманах |

## Names that stay Latin in both scripts

Foreign publishers, products and acronyms: Eurostat, Copernicus, ESA, ESA WorldCover, GISCO, Natural Earth,
OpenStreetMap, geoBoundaries, OurAirports, Overpass, USGS, Wikidata, WRI, UNESCO, NACE, GitHub, GLO-30, COG,
GeoJSON, AWS. Acronyms of Serbian names follow the script: RZS → РЗС, BDP → БДП, NBS → НБС.

## Numbers

Decimal comma, dot as thousands separator (`1.234.567,89`), a space before `%` and a space before a currency
symbol that follows the number (`82 mlrd €`, `109.462 RSD`). Compact: `hilj.` (10³), `mil.` (10⁶), `mlrd` (10⁹),
`bil.` (10¹²).
