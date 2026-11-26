"""Catalog entries for the wonders and resources layers: where their names and figures come from.

Nothing is fetched here. Every figure was read by hand from the page named in docs/SITES.md into
pipeline/data/wonders_sites.csv or pipeline/data/resources_sites.csv, which the two builders read. The entries exist so
that sources.json, the Almanac's bibliography, can name these pages and so the data can cite them by id.
"""

from __future__ import annotations

from ..core.source import Source, SourceInfo

WIKI_SR = "https://sr.wikipedia.org/"
WIKI_EN = "https://en.wikipedia.org/"


class Curated(Source):
    """A source read by hand: nothing to download; an interim, if one is asked for, only names the vintage."""

    vintage: str | None = None
    curated = True

    def fetch(self, force: bool = False) -> None:
        pass

    def process(self) -> dict:
        return {"vintage": self.vintage, "_files": []}


# --- wonders ------------------------------------------------------------------------------------------------------------


class ProtectedAreasWikipedia(Curated):
    vintage = "infokutije proverene novembar 2026; godina proglašenja po aktu koji infokutija navodi"
    info = SourceInfo(
        id="wikipedia_sr_protected_areas",
        title="Zaštićena područja: površina i godina proglašenja",
        publisher="Vikipedija na srpskom jeziku",
        homepage=WIKI_SR,
        license="CC BY-SA 4.0 (tekst Vikipedije)",
        description=(
            "Površina u hektarima i godina akta o proglašenju za nacionalne parkove Đerdap (63.786,48 ha, 1974), "
            "Kopaonik (11.810 ha, 1981), Tara (24.991,82 ha, 1981), Šar-planinu (22.805 ha, 1986) i Frušku goru "
            "(26.672 ha, 1960) i za Uvac (7.543 ha, 1971) i Đavolju varoš (67 ha, 1959), iz infokutija; ručno preneto "
            "u pipeline/data/wonders_sites.csv."
        ),
        used_for=["Nacionalni parkovi i zaštićena područja na karti", "Almanak: čuda"],
    )


class SiteCoordinatesWikipedia(Curated):
    vintage = "koordinate proverene novembar 2026"
    info = SourceInfo(
        id="wikipedia_en_coordinates",
        title="Koordinate lokaliteta i površina Golije",
        publisher="Vikipedija na engleskom jeziku",
        homepage=WIKI_EN,
        license="CC BY-SA 4.0 (tekst); koordinate CC0 preko Vikipodataka",
        description=(
            "Geografske koordinate lokaliteta, dobara sa Liste svetske baštine i parkova, i površina Golije (oko "
            "750 km²); ručno preneto u pipeline/data/wonders_sites.csv."
        ),
        used_for=["Položaj čuda na karti", "Almanak: čuda"],
    )


class UnescoSerbia(Curated):
    vintage = "Lista svetske baštine, provereno novembar 2026"
    info = SourceInfo(
        id="unesco_whc_rs",
        title="Lista svetske baštine: Srbija",
        publisher="UNESCO, Centar za svetsku baštinu",
        homepage="https://whc.unesco.org/en/statesparties/rs",
        license="© UNESCO; citirano uz navođenje izvora",
        description=(
            "Dobra Srbije na Listi svetske baštine i godine upisa: Stari Ras i Sopoćani (1979), Studenica (1986), "
            "Visoki Dečani (2004), Patrijaršija u Peći, Bogorodica Ljeviška i Gračanica (2006), Gamzigrad–Feliks "
            "Romulijana (2007) i stećci (2016; Mramorje u Perućcu, Mramorje u Rastištu i Grčko groblje u Hrtu)."
        ),
        used_for=["Dobra svetske baštine na karti", "Almanak: čuda"],
    )


class EnrolledStudents(Curated):
    vintage = "školska 2024/2025"
    info = SourceInfo(
        id="rzs_G20251236",
        title="Studenti upisani na visokoškolske ustanove 2024/2025",
        publisher="Republički zavod za statistiku",
        homepage="https://publikacije.stat.gov.rs/G2025/HtmlE/G20251236.html",
        license="Slobodno korišćenje uz navođenje izvora (RZS)",
        description=(
            "Saopštenje br. 36 od 29. 8. 2025: Univerzitet u Beogradu 89.299 studenata, u Novom Sadu 42.552, u Nišu "
            "22.756 i u Kragujevcu 13.996; državni univerziteti ukupno 175.789."
        ),
        used_for=["Istraživački univerziteti na karti", "Almanak: čuda"],
    )


class CuratedLandmarks(Curated):
    vintage = "izbor novembar 2026"
    info = SourceInfo(
        id="project_curated_landmarks",
        title="Izbor lokaliteta (urednički izbor projekta)",
        publisher="serbiaciv",
        homepage="https://acailic.github.io/serbiaciv/",
        license="MIT (licenca projekta)",
        description=(
            "Trinaest lokaliteta je urednički izbor spomenika kulture od izuzetnog značaja (tvrđave, arheološka "
            "nalazišta, manastiri); za njih nema brojeva, a položaji su preuzeti iz Vikipedije."
        ),
        used_for=["Znamenitosti na karti", "Almanak: čuda"],
    )


# --- resources ----------------------------------------------------------------------------------------------------------


class EpsTechnicalReport(Curated):
    vintage = "2024"
    info = SourceInfo(
        id="eps_technical_report_2024",
        title="Tehnički godišnjak EPS 2024",
        publisher="Elektroprivreda Srbije",
        homepage="https://www.eps.rs/eng/Documents/technicalreports/TEH_Godisnjak2024_web_en_.pdf",
        license="© Elektroprivreda Srbije; citirano uz navođenje izvora",
        description=(
            "Neto snaga (MW) i proizvodnja (GWh) po elektrani u 2024. godini i proizvodnja uglja po ogranku (MB "
            "Kolubara 22 mil. t, TE-KO Kostolac 9 mil. t, sa grafikona, zaokruženo na ceo milion tona); ručno preneto "
            "u pipeline/data/resources_sites.csv."
        ),
        used_for=["Termoelektrane, hidroelektrane i rudnici lignita na karti", "Almanak: resursi"],
    )


class EpsRenewables(Curated):
    vintage = "2025"
    info = SourceInfo(
        id="eps_renewables",
        title="EPS: obnovljivi izvori energije",
        publisher="Elektroprivreda Srbije",
        homepage="https://www.eps.rs/cir/Poslovanje-EE/Pages/oie.aspx",
        license="© Elektroprivreda Srbije; citirano uz navođenje izvora",
        description="Vetroelektrana Kostolac: instalisana snaga 66 MW.",
        used_for=["Vetroparkovi na karti", "Almanak: resursi"],
    )


class NisTetoPancevo(Curated):
    vintage = "2022"
    info = SourceInfo(
        id="nis_teto_pancevo",
        title="TE-TO Pančevo",
        publisher="Naftna industrija Srbije",
        homepage="https://www.nis.rs/project/te-to-pancevo",
        license="© Naftna industrija Srbije; citirano uz navođenje izvora",
        description="Gasno-parna elektrana-toplana Pančevo: električna snaga do 200 MW, u pogonu od 2022. godine.",
        used_for=["Gasne elektrane na karti", "Almanak: resursi"],
    )


class NisRefineryPancevo(Curated):
    vintage = "2020"
    info = SourceInfo(
        id="nis_refinery_pancevo",
        title="Rafinerija nafte Pančevo",
        publisher="Naftna industrija Srbije",
        homepage="https://www.nis.rs/",
        license="© Naftna industrija Srbije; citirano uz navođenje izvora",
        description="Projektovani kapacitet prerade nafte 4,8 miliona tona godišnje.",
        used_for=["Rafinerija nafte na karti", "Almanak: resursi"],
    )


class WindParksWikipedia(Curated):
    vintage = "2019"
    info = SourceInfo(
        id="wind_parks_wikipedia",
        title="Vetroparkovi Čibuk 1 i Kovačica",
        publisher="Vikipedija na srpskom jeziku",
        homepage=WIKI_SR,
        license="CC BY-SA 4.0 (tekst Vikipedije)",
        description=(
            "Vetropark Čibuk 1 kod Mramorca (158 MW, 57 turbina, u pogonu od oktobra 2019) i Vetropark Kovačica kod "
            "Debeljače (104,5 MW, 38 turbina), iz infokutija."
        ),
        used_for=["Vetroparkovi na karti", "Almanak: resursi"],
    )


class SolarPetka(Curated):
    vintage = "2025"
    info = SourceInfo(
        id="se_petka_2025",
        title="Solarna elektrana Petka u probnom radu",
        publisher="Blic; Vlada Republike Srbije",
        homepage="https://www.srbija.gov.rs/vest/en/253987/",
        license="© izdavači; citirano uz navođenje izvora",
        description="Solarna elektrana Petka na Kostolcu: instalisana snaga 9,75 MW, puštena u probni rad 14. 7. 2025.",
        used_for=["Solarne elektrane na karti", "Almanak: resursi"],
    )


class UsgsMineralsYearbook(Curated):
    vintage = "2024"
    info = SourceInfo(
        id="usgs_minerals_yearbook_2024",
        title="USGS Minerals Yearbook 2024: Srbija",
        publisher="U.S. Geological Survey",
        homepage=(
            "https://www.usgs.gov/centers/national-minerals-information-center/serbia-and-montenegro-minerals-yearbook-2024"
        ),
        license="Javni domen (USGS)",
        description=(
            "Sadržaj bakra u koncentratima po rudniku u 2024. godini, procene USGS (Veliki Krivelj 55.000 t, Majdanpek "
            "52.000 t, Jama 8.000 t, Čukaru Peki 170.000 t), i koncentrati olova i cinka (Rudnik 5.000 t, Veliki "
            "Majdan 4.000 t); za Lece je objavljena samo količina rude."
        ),
        used_for=["Rudnici bakra, olova i cinka na karti", "Almanak: resursi"],
    )
