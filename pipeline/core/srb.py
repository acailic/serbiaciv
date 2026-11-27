"""Serbia: the numbers, codes and vocabulary every source and builder shares.

This module is the single place for values that more than one source or builder needs. Change a constant here and
nowhere else; tests in tests/test_srb.py pin the values that the design spec fixes.
"""

from __future__ import annotations

# --- the map -------------------------------------------------------------------------------------------------------

HEX_RADIUS_KM = 5.0  # centre to vertex; flat-to-flat 8.66 km, area 64.95 km²
MARGIN_KM = 200.0
ALBERS = {"lat1": 42.5, "lat2": 45.5, "lat0": 44.0, "lon0": 21.0}
BBOX_LONLAT = (18.8, 41.8, 23.2, 46.2)  # min lon, min lat, max lon, max lat: the Republic of Serbia incl. Kosovo and Metohija

# Cell owner codes besides the okrug index (>= 0).
WATER, FOREIGN = -1, -2

# Water classes. Serbia is landlocked: upstream's Ocean and Coast ids stay reserved so the art can tell them apart.
LAND, OCEAN, COAST, LAKE = range(4)
LAKE_MIN_KM2 = 40.0  # a lake or reservoir makes water tiles only from this size (in practice the Iron Gates)

# Relief, from the elevation range inside a hex (max − min) and its mean.
FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
RELIEF_HILLS_RANGE_M = 60
RELIEF_MOUNTAINS_RANGE_M = 300
PEAKS_MEAN_M = 1300
URBAN_MIN_PCT = 30
RIVER_MIN_LENGTH_KM = 50

# --- territory (ids come from pipeline/data/rzs_territory.json) ---------------------------------------------------

KIM_REGION = "RS23"
KIM_OBLASTI = ["RS231", "RS232", "RS233", "RS234", "RS235"]
GRAD_BEOGRAD = "79014"

# --- economy -------------------------------------------------------------------------------------------------------

# NACE sections → the site's industry keys, with the names the site shows (Serbian Latin; Cyrillic is generated).
INDUSTRIES = [
    ("agriculture", "A", "Poljoprivreda, šumarstvo i ribarstvo"),
    ("mining", "B", "Rudarstvo i vađenje"),
    ("manufacturing", "C", "Prerađivačka industrija"),
    ("energy", "D", "Snabdevanje električnom energijom, gasom i parom"),
    ("water_waste", "E", "Snabdevanje vodom; uklanjanje i obrada otpada"),
    ("construction", "F", "Građevinarstvo"),
    ("trade", "G", "Trgovina na veliko i na malo"),
    ("transport", "H", "Saobraćaj i skladištenje"),
    ("accommodation", "I", "Ugostiteljstvo"),
    ("information", "J", "Informisanje i komunikacije"),
    ("finance", "K", "Finansijske delatnosti"),
    ("real_estate", "L", "Poslovanje nekretninama"),
    ("professional", "M", "Stručne, naučne i tehničke delatnosti"),
    ("admin", "N", "Administrativne i pomoćne uslužne delatnosti"),
    ("public_admin", "O", "Državna uprava i odbrana; obavezno socijalno osiguranje"),
    ("education", "P", "Obrazovanje"),
    ("health", "Q", "Zdravstvena zaštita i socijalna pomoć"),
    ("arts", "R", "Umetnost, zabava i rekreacija"),
    ("other", "S", "Ostale uslužne delatnosti"),
]
INDUSTRY_KEYS = [key for key, _, _ in INDUSTRIES]
INDUSTRY_NAMES = {key: name for key, _, name in INDUSTRIES}
NACE_TO_KEY = {nace: key for key, nace, _ in INDUSTRIES}
# The English label each Popis 2022 workbook gives the column of a NACE section (matched as a fragment, in the
# order of INDUSTRIES: A–S). Used to read the Republic row of the industry workbook (build/districts.py).
CENSUS_NACE_FRAGMENTS = ("Agriculture, forestry", "Mining and quarrying", "Manufacturing", "Electricity, gas",
                        "Water supply", "Construction", "Wholesale and retail", "Transportation and storage",
                        "Accommodation and food", "Information and communication", "Financial and insurance",
                        "Real estate", "Professional, scientific", "Administrative and support",
                        "Public administration", "Education", "Human health", "Arts, entertainment",
                        "Other service activities")

YIELDS = [
    {
        "key": "food", "icon": "y-food", "emoji": "🌾", "label": "Hrana", "color": "#7fbf3f", "unit": "zaposleni",
        "industries": ["agriculture"],
        "description": "Zaposleni u poljoprivredi, šumarstvu i ribarstvu, prema prebivalištu (Popis 2022, NACE odeljak A).",
    },
    {
        "key": "production", "icon": "y-production", "emoji": "⚙️", "label": "Proizvodnja", "color": "#d9823b", "unit": "zaposleni",
        "industries": ["manufacturing", "construction", "mining"],
        "description": "Zaposleni u prerađivačkoj industriji, građevinarstvu i rudarstvu, prema prebivalištu "
                       "(Popis 2022, NACE odeljci C, F i B).",
    },
    {
        "key": "gold", "icon": "y-gold", "emoji": "💰", "label": "Zlato", "color": "#f2c94c", "unit": "eur",
        "industries": [],
        "description": "Bruto domaći proizvod u tekućim evrima, tamo gde se obavlja rad (Eurostat, BDP po oblastima). "
                       "Za grad je to procena: BDP okruga podeljen prema udelu grada u zaposlenima okruga.",
    },
    {
        "key": "science", "icon": "y-science", "emoji": "🔬", "label": "Nauka", "color": "#4fa3e0", "unit": "zaposleni",
        "industries": ["professional", "information"],
        "description": "Zaposleni u stručnim, naučnim i tehničkim delatnostima i u informisanju, prema prebivalištu "
                       "(Popis 2022, NACE odeljci M i J).",
    },
    {
        "key": "culture", "icon": "y-culture", "emoji": "🎭", "label": "Kultura", "color": "#b07ce0", "unit": "zaposleni",
        "industries": ["arts"],
        "description": "Zaposleni u umetnosti, zabavi i rekreaciji, prema prebivalištu (Popis 2022, NACE odeljak R).",
    },
]
YIELD_KEYS = [y["key"] for y in YIELDS]

# --- cities --------------------------------------------------------------------------------------------------------

CITY_MIN_URBAN_POP = 10000  # a municipality is a city when it holds an urban settlement of this size (Popis 2022)
CITY_MIN_POP = 25000  # … and its territory has at least this many inhabitants (RZS estimate, latest year)
HOME_BANNERS = 25  # banners at the home view: the most populous cities
GROWTH_YEARS = (2022, None)  # population change is measured from the census year to the latest estimate (None = latest):
# RZS rebased its estimate series on Popis 2022 and never revised the years before it, so a 2021 base would carry the
# census correction (a median step of -3.5 % between 2021 and 2022) as if it were a real loss of people.
LENS_CHANGE_YEARS = (2015, None)  # the pop_change lens: a ten-year change, unlike GROWTH_YEARS

# --- web/data: the shapes the checker, the lenses and the municipalities table share ---------------------------------
MAP_MUNICIPALITIES = 197  # the units the map draws: 204 RZS units less Grad Beograd, four grads and Grad Niš (drawn as their parts) and Petrovaradin (no polygon)
STATISTICAL_LENSES = ["density", "pop_change", "natural_increase", "age65", "education", "wages", "unemployment", "manufacturing", "commute", "orthodox", "serbs", "life_expectancy"]
LAND_LENSES = ["elevation", "relief", "land_cover"]  # read hex by hex from world.json
LENS_IDS = STATISTICAL_LENSES + LAND_LENSES  # the fifteen lenses, in the site's order
LENS_GROUPS = ["people", "work", "identity", "life", "land"]  # the lens groups, in the site's order
LENS_FORMATS = ("int", "pct", "float", "rsd", "category")  # how a lens or a table column shows a number
LENS_COLUMN = {"wages": "wage_net"}  # the municipalities table's column behind a lens whose id differs from it
PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]  # world.json "pct", in upstream's order
COVER_KEYS = ["none", "forest_deciduous", "forest_evergreen", "forest_mixed", "scrub", "grassland", "pasture", "cropland", "wetland", "urban", "barren", "ice"]  # world.json cover table, id = index
COVER_GROUP_IDS = {"forest": (1, 2, 3), "crop": (7,), "pasture": (6,), "grass": (5,), "shrub": (4,), "wetland": (8,), "developed": (9,), "barren": (10,)}  # the cover ids a pct group can produce
COUNTY_COLUMNS = ["geoid", "name", "state", "population", "land_km2", "density", "age65", "education", "wage_net", "unemployment", "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "forest", "crop", "pasture", "developed", "city", "cell"]  # counties.json columns, in order
COUNTY_COLUMN_FORMATS = ["text", "text", "text", "int", "km2", "float", "pct", "pct", "rsd", "pct", "pct", "pct", "pct", "pct", "float", "float", "pct", "pct", "pct", "pct", "text", "int"]  # the format of each column

# --- publishers ----------------------------------------------------------------------------------------------------

RZS_RESULT_URL = "https://data.stat.gov.rs/Home/Result/{subarea}?languageCode=sr-Latn"
RZS_EXPORT_URL = "https://data.stat.gov.rs/Home/DisplayResult"
# RZS dissemination database datasets, verified reachable on 2026-11-26. Values are the subAreaId.
RZS_DATASETS = {
    "pop_estimate": "18010602",  # population estimates by municipality, sex and age
    "births": "180304",
    "deaths": "18030504",
    "natural_increase": "18030301",
    "migration_in": "18060401",
    "migration_out": "18060402",
    "net_migration": "18060403",
    "wages": "2403040403",
    "employment_nace": "240205",  # registered employment by municipality of work × NACE section
    "employment_work": "240204",
    "employment_residence": "24021105",
    "life_expectancy": "18050202",
    "land_use": "1300021101",
    "ethnicity": "3104020101",
    "gdp_region": "09020404",
}

CENSUS_BASE = "https://popis2022.stat.gov.rs/media"
CENSUS_INDEX = "https://popis2022.stat.gov.rs/sr-Latn/rezultati/excel/"
# Popis 2022 Excel tables: key → (media id, file name). Keys are what the census source exports.
CENSUS_FILES = {
    "settlement_population": ("31319", "0_ukupan-broj-stanovnika-naselja.xlsx"),
    "settlement_age_sex": ("31320", "1_stanovnistvo-prema-starosti-i-polu.xlsx"),
    "municipality_age_sex": ("31325", "2_stanovnistvo-prema-starosti-i-polu.xlsx"),
    "settlement_households": ("31321", "2_domacinstva-prema-broju-clanova.xlsx"),
    "education": ("31326", "3_stanovnistvo-staro-15-i-vise-godina-prema-skolskoj-spremi-i-polu.xlsx"),
    "illiterate": ("31327", "4_stanovnistvo-staro-10-i-vise-godina-prema-polu-a-nepismeni-i-prema-starosti.xlsx"),
    "ethnicity": ("31324", "1_stanovnistvo-prema-nacionalnoj-pripadnosti-i-polu.xlsx"),
    "religion": ("31329", "6_stanovnistvo-prema-veroispovesti.xlsx"),
    "migration": ("31336", "13_stanovnistvo-prema-migratornim-obelezjima.xlsx"),
    "migrants": ("31337", "14_doseljeno-stanovnistvo-prema-podrucju-sa-kojeg-se-doselilo-periodu-doseljenja-i-polu.xlsx"),
    "municipality_households": ("31334", "11_domacinstva-prema-broju-clanova.xlsx"),
    "activity": ("31405", "17_stanovnistvo-prema-ekonomskoj-aktivnosti-starosti-i-polu.xlsx"),
    "industry": ("31450", "24_ekonomski-aktivno-stanovnistvo-koje-obavlja-zanimanje-prema-delatnosti-i-polu.xlsx"),
    "occupation": ("31451", "25_ekonomski-aktivno-stanovnistvo-koje-obavlja-zanimanje-prema-grupama-zanimanja-i-polu.xlsx"),
    "commute": ("31441", "dnevne_migracije_aktivnog_stanovnistva_koje_obavlja_zanimanje_po_polu_i_tipu_naselja.xlsx"),
}

GISCO_NUTS_URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2024_4326_LEVL_{level}.geojson"
GISCO_LAU_URL = "https://gisco-services.ec.europa.eu/distribution/v2/lau/download/ref-lau-2024-01m.shp.zip"
GEOBOUNDARIES_XKX_ADM2 = (
    "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData/gbOpen/XKX/ADM2/"
    "geoBoundaries-XKX-ADM2.geojson"
)
NATURAL_EARTH = "https://naciscdn.org/naturalearth/10m/{theme}/ne_10m_{name}.zip"
EUROSTAT_GDP_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON&geo={geos}&unit={unit}&time={times}"
COPERNICUS_TILE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}_{ew}_DEM/Copernicus_DSM_COG_10_{ns}_{ew}_DEM.tif"
WORLDCOVER_TILE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
GEOFABRIK_URL = "https://download.geofabrik.de/europe/{region}-latest-free.shp.zip"
USGS_QUAKE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# --- infrastructure (roads, rail, ports, airports) -------------------------------------------------------------------------
AUL_PORTS_URL = "http://www.aul.gov.rs/folder/analiza-aktivnosti-u-lukama-i-pristanishtima-u-2025-godini.pptx"
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
EUROSTAT_AVIA_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoa?format=JSON&lang=EN&freq=A&unit=PAS"
    "&tra_meas=PAS_CRD&schedule=TOTAL&tra_cov=TOTAL&sinceTimePeriod=2018"
)
MORAVA_STATS_URL = "https://kvo.aerodromisrbije.rs/statistika/"
# The airports' names in Serbian Latin, by ICAO code (the map shows the id and this name). The rest of the list comes
# from the data; an airport missing here is written with its ICAO code as its name.
AIRPORT_NAMES = {"LYBE": "Nikola Tesla", "LYNI": "Konstantin Veliki", "LYKV": "Morava", "LYUZ": "Ponikve", "LYBT": "Batajnica"}
AIRPORT_TYPES = ["large_airport", "medium_airport"]  # OurAirports' kinds that are drawn; sports airfields are not
