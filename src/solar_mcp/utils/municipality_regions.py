"""Swedish electricity pricing region (elområde) mapping.

Sweden is divided into four day-ahead price areas by Svenska Kraftnät:
  SE1 (Luleå)    – Norrbotten + most of Västerbotten
  SE2 (Sundsvall) – Jämtland, Västernorrland, northern Gävleborg/Dalarna
  SE3 (Stockholm) – Central Sweden (biggest consumption zone)
  SE4 (Malmö)    – Southern Sweden (Skåne, Blekinge, Kronoberg, southern Halland/Kalmar/Jönköping)

Source: Svenska Kraftnät (svk.se) and Energimarknadsbyrån (energimarknadsbyran.se).
The zone boundary does not follow county borders exactly — ~25 municipalities span two zones.
"""

from __future__ import annotations

import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Municipality → SE region mapping
# ---------------------------------------------------------------------------
# Coverage: all 50 municipalities in municipality_coords.py plus major additions.
# For split counties, individual municipalities are assigned to their primary zone.
# ---------------------------------------------------------------------------
MUNICIPALITY_REGION: dict[str, str] = {
    # --- SE1: Norrbotten (all) + Västerbotten (all) ---
    "Luleå": "SE1",
    "Boden": "SE1",
    "Piteå": "SE1",
    "Kiruna": "SE1",
    "Gällivare": "SE1",
    "Jokkmokk": "SE1",
    "Haparanda": "SE1",
    "Kalix": "SE1",
    "Älvsbyn": "SE1",
    "Arjeplog": "SE1",
    "Arvidsjaur": "SE1",
    "Skellefteå": "SE1",
    "Umeå": "SE1",
    "Lycksele": "SE1",
    "Storuman": "SE1",
    "Vindeln": "SE1",
    "Vännäs": "SE1",
    "Nordmaling": "SE1",
    "Bjurholm": "SE1",
    "Robertsfors": "SE1",
    "Norsjö": "SE1",
    "Malå": "SE1",
    "Sorsele": "SE1",
    "Dorotea": "SE1",
    "Vilhelmina": "SE1",
    "Åsele": "SE1",

    # --- SE2: Jämtland + Västernorrland + northern Gävleborg + northern Dalarna ---
    "Östersund": "SE2",
    "Åre": "SE2",
    "Krokom": "SE2",
    "Strömsund": "SE2",
    "Bräcke": "SE2",
    "Ragunda": "SE2",
    "Berg": "SE2",
    "Härjedalen": "SE2",
    "Sundsvall": "SE2",
    "Härnösand": "SE2",
    "Örnsköldsvik": "SE2",
    "Kramfors": "SE2",
    "Timrå": "SE2",
    "Ånge": "SE2",
    "Sollefteå": "SE2",
    "Hudiksvall": "SE2",   # northern Gävleborg
    "Ljusdal": "SE2",      # northern Gävleborg
    "Söderhamn": "SE2",    # central Gävleborg — on SE2/SE3 border, classified SE2
    "Bollnäs": "SE2",      # central Gävleborg — on SE2/SE3 border, classified SE2
    "Ovanåker": "SE2",     # northern Gävleborg
    "Mora": "SE2",         # northern Dalarna
    "Orsa": "SE2",         # northern Dalarna
    "Älvdalen": "SE2",     # northern Dalarna
    "Malung-Sälen": "SE2", # northern Dalarna
    "Vansbro": "SE2",      # northern Dalarna

    # --- SE3: Central Sweden ---
    # Gävleborg (southern)
    "Gävle": "SE3",
    "Sandviken": "SE3",
    "Hofors": "SE3",
    "Ockelbo": "SE3",
    "Nordanstig": "SE3",
    # Dalarna (central/southern)
    "Falun": "SE3",
    "Borlänge": "SE3",
    "Säter": "SE3",
    "Hedemora": "SE3",
    "Avesta": "SE3",
    "Ludvika": "SE3",
    "Gagnef": "SE3",
    "Leksand": "SE3",
    "Rättvik": "SE3",
    "Smedjebacken": "SE3",
    # Värmland
    "Karlstad": "SE3",
    "Kristinehamn": "SE3",
    "Filipstad": "SE3",
    "Hagfors": "SE3",
    "Arvika": "SE3",
    "Säffle": "SE3",
    # Örebro county
    "Örebro": "SE3",
    "Kumla": "SE3",
    "Hallsberg": "SE3",
    "Lekeberg": "SE3",
    "Laxå": "SE3",
    "Karlskoga": "SE3",
    "Degerfors": "SE3",
    "Hällefors": "SE3",
    "Lindesberg": "SE3",
    "Nora": "SE3",
    "Ljusnarsberg": "SE3",
    "Askersund": "SE3",
    # Västmanland
    "Västerås": "SE3",
    "Köping": "SE3",
    "Arboga": "SE3",
    "Kungsör": "SE3",
    "Hallstahammar": "SE3",
    "Sala": "SE3",
    "Fagersta": "SE3",
    "Norberg": "SE3",
    "Skinnskatteberg": "SE3",
    "Surahammar": "SE3",
    # Uppsala county
    "Uppsala": "SE3",
    "Enköping": "SE3",
    "Östhammar": "SE3",
    "Tierp": "SE3",
    "Håbo": "SE3",
    "Knivsta": "SE3",
    "Heby": "SE3",
    "Älvkarleby": "SE3",
    # Stockholm county
    "Stockholm": "SE3",
    "Nacka": "SE3",
    "Huddinge": "SE3",
    "Täby": "SE3",
    "Södertälje": "SE3",
    "Solna": "SE3",
    "Sundbyberg": "SE3",
    "Järfälla": "SE3",
    "Botkyrka": "SE3",
    "Haninge": "SE3",
    "Tyresö": "SE3",
    "Lidingö": "SE3",
    "Danderyd": "SE3",
    "Sollentuna": "SE3",
    "Värmdö": "SE3",
    "Upplands Väsby": "SE3",
    "Sigtuna": "SE3",
    "Norrtälje": "SE3",
    "Nynäshamn": "SE3",
    "Ekerö": "SE3",
    # Södermanland
    "Eskilstuna": "SE3",
    "Nyköping": "SE3",
    "Oxelösund": "SE3",
    "Strängnäs": "SE3",
    "Katrineholm": "SE3",
    "Flen": "SE3",
    "Vingåker": "SE3",
    "Gnesta": "SE3",
    "Trosa": "SE3",
    # Östergötland
    "Linköping": "SE3",
    "Norrköping": "SE3",
    "Motala": "SE3",
    "Mjölby": "SE3",
    "Finspång": "SE3",
    "Vadstena": "SE3",
    "Åtvidaberg": "SE3",
    "Boxholm": "SE3",
    "Kinda": "SE3",
    "Ydre": "SE3",
    "Söderköping": "SE3",
    "Valdemarsvik": "SE3",
    "Ödeshög": "SE3",
    # Gotland
    "Gotland": "SE3",
    "Visby": "SE3",
    # Västra Götaland (mostly SE3; small SE4 corner excluded)
    "Göteborg": "SE3",
    "Borås": "SE3",
    "Trollhättan": "SE3",
    "Skövde": "SE3",
    "Uddevalla": "SE3",
    "Lidköping": "SE3",
    "Alingsås": "SE3",
    "Mölndal": "SE3",
    "Kungälv": "SE3",
    "Stenungsund": "SE3",
    "Lerum": "SE3",
    "Partille": "SE3",
    "Kungsbacka": "SE3",   # northern Halland → SE3
    "Varberg": "SE3",      # northern Halland → SE3
    # Jönköping county (northern/central = SE3; southern border = SE4 side)
    "Jönköping": "SE3",
    "Eksjö": "SE3",
    "Värnamo": "SE4",      # southern Jönköping → SE4
    "Vetlanda": "SE4",     # southern Jönköping → SE4
    "Nässjö": "SE3",
    "Sävsjö": "SE4",       # southern Jönköping → SE4
    "Gnosjö": "SE4",       # southern Jönköping → SE4
    "Vaggeryd": "SE3",
    "Aneby": "SE3",
    "Tranås": "SE3",
    "Habo": "SE3",
    "Mullsjö": "SE3",
    # Kalmar county (northern = SE3; southern = SE4)
    "Västervik": "SE3",    # northern Kalmar → SE3
    "Oskarshamn": "SE3",   # central Kalmar → on border, classified SE3
    "Mönsterås": "SE3",    # central Kalmar → SE3
    "Emmaboda": "SE4",     # southern Kalmar → SE4
    "Torsås": "SE4",       # southern Kalmar → SE4
    "Borgholm": "SE3",
    "Högsby": "SE3",
    "Hultsfred": "SE3",
    "Vimmerby": "SE3",
    "Kalmar": "SE4",       # southern Kalmar city → SE4

    # --- SE4: Southern Sweden ---
    # Blekinge (all)
    "Karlskrona": "SE4",
    "Karlshamn": "SE4",
    "Ronneby": "SE4",
    "Sölvesborg": "SE4",
    "Olofström": "SE4",
    # Kronoberg (all)
    "Växjö": "SE4",
    "Älmhult": "SE4",
    "Markaryd": "SE4",
    "Ljungby": "SE4",
    "Tingsryd": "SE4",
    "Alvesta": "SE4",
    "Uppvidinge": "SE4",
    "Lessebo": "SE4",
    # Skåne (all 33)
    "Malmö": "SE4",
    "Helsingborg": "SE4",
    "Kristianstad": "SE4",
    "Lund": "SE4",
    "Trelleborg": "SE4",
    "Ystad": "SE4",
    "Landskrona": "SE4",
    "Ängelholm": "SE4",
    "Simrishamn": "SE4",
    "Hässleholm": "SE4",
    "Eslöv": "SE4",
    "Höganäs": "SE4",
    "Vellinge": "SE4",
    "Burlöv": "SE4",
    "Staffanstorp": "SE4",
    "Svedala": "SE4",
    "Skurup": "SE4",
    "Sjöbo": "SE4",
    "Tomelilla": "SE4",
    "Bromölla": "SE4",
    "Östra Göinge": "SE4",
    "Osby": "SE4",
    "Perstorp": "SE4",
    "Klippan": "SE4",
    "Åstorp": "SE4",
    "Bjuv": "SE4",
    "Kävlinge": "SE4",
    "Lomma": "SE4",
    "Svalöv": "SE4",
    "Örkelljunga": "SE4",
    "Båstad": "SE4",
    "Hörby": "SE4",
    "Höör": "SE4",
    # Southern Halland
    "Halmstad": "SE4",
    "Falkenberg": "SE4",   # near SE3/SE4 border; primary zone SE4
    "Laholm": "SE4",
}


# ---------------------------------------------------------------------------
# Border municipalities — span two pricing zones
# ---------------------------------------------------------------------------
# These municipalities lie on or very close to a zone boundary. In some cases
# the municipal boundary literally crosses the transmission system zone line,
# meaning customers in the same municipality may be in different price areas.
# ---------------------------------------------------------------------------
BORDER_MUNICIPALITIES: list[dict] = [
    # SE2/SE3 border — Gävleborg county split
    {
        "municipality": "Hudiksvall",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Gävleborg",
        "note": "Gävleborg county is split; Hudiksvall is in the northern (SE2) part",
    },
    {
        "municipality": "Ljusdal",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Gävleborg",
        "note": "Northern Gävleborg, close to SE2/SE3 boundary",
    },
    {
        "municipality": "Söderhamn",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Gävleborg",
        "note": "Central Gävleborg — right on the SE2/SE3 border",
    },
    {
        "municipality": "Bollnäs",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Gävleborg",
        "note": "Central Gävleborg — right on the SE2/SE3 border",
    },
    # SE2/SE3 border — Dalarna county split
    {
        "municipality": "Mora",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Dalarna",
        "note": "Northern Dalarna; Dalarna county is split between SE2 (north) and SE3 (south)",
    },
    {
        "municipality": "Malung-Sälen",
        "primary_region": "SE2",
        "adjacent_region": "SE3",
        "border_type": "SE2/SE3",
        "county": "Dalarna",
        "note": "Northwestern Dalarna; close to the SE2/SE3 boundary",
    },
    # SE3/SE4 border — Halland county split
    {
        "municipality": "Varberg",
        "primary_region": "SE3",
        "adjacent_region": "SE4",
        "border_type": "SE3/SE4",
        "county": "Halland",
        "note": "Northern Halland; Halland county is split — Varberg/Kungsbacka in SE3, Halmstad/Laholm in SE4",
    },
    {
        "municipality": "Falkenberg",
        "primary_region": "SE4",
        "adjacent_region": "SE3",
        "border_type": "SE3/SE4",
        "county": "Halland",
        "note": "Central Halland; sits directly on the SE3/SE4 zonal boundary",
    },
    # SE3/SE4 border — Jönköping county split
    {
        "municipality": "Jönköping",
        "primary_region": "SE3",
        "adjacent_region": "SE4",
        "border_type": "SE3/SE4",
        "county": "Jönköping",
        "note": "Jönköping county is split; the city itself is near the SE3/SE4 boundary",
    },
    {
        "municipality": "Värnamo",
        "primary_region": "SE4",
        "adjacent_region": "SE3",
        "border_type": "SE3/SE4",
        "county": "Jönköping",
        "note": "Southern Jönköping county; in SE4 but close to the SE3 border",
    },
    {
        "municipality": "Vetlanda",
        "primary_region": "SE4",
        "adjacent_region": "SE3",
        "border_type": "SE3/SE4",
        "county": "Jönköping",
        "note": "Southern Jönköping county; in SE4 near the SE3 border",
    },
    # SE3/SE4 border — Kalmar county split
    {
        "municipality": "Oskarshamn",
        "primary_region": "SE3",
        "adjacent_region": "SE4",
        "border_type": "SE3/SE4",
        "county": "Kalmar",
        "note": "Central Kalmar county; Kalmar county is split between SE3 (north) and SE4 (south/city)",
    },
    {
        "municipality": "Kalmar",
        "primary_region": "SE4",
        "adjacent_region": "SE3",
        "border_type": "SE3/SE4",
        "county": "Kalmar",
        "note": "Kalmar city is in SE4; Kalmar county straddles the SE3/SE4 boundary",
    },
    # SE3/SE4 border — small Västra Götaland corner
    {
        "municipality": "Tranemo",
        "primary_region": "SE3",
        "adjacent_region": "SE4",
        "border_type": "SE3/SE4",
        "county": "Västra Götaland",
        "note": "Far southeastern corner of Västra Götaland; very close to SE4 boundary",
    },
]


# ---------------------------------------------------------------------------
# Fuzzy lookup helpers (same normalization pattern as municipality_coords.py)
# ---------------------------------------------------------------------------
def _normalize(name: str) -> str:
    """Lowercase + strip diacritics for fuzzy matching."""
    nfd = unicodedata.normalize("NFD", name.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


_REGION_INDEX: dict[str, str] = {_normalize(k): k for k in MUNICIPALITY_REGION}

_BORDER_INDEX: dict[str, dict] = {
    _normalize(entry["municipality"]): entry for entry in BORDER_MUNICIPALITIES
}


def get_region(municipality_name: str) -> str | None:
    """Return SE region (SE1/SE2/SE3/SE4) for a municipality, or None if unknown.

    Handles exact matches, case-insensitive matches, and diacritic-stripped
    matches (e.g. 'Goteborg' → 'Göteborg').
    """
    # Exact match
    if municipality_name in MUNICIPALITY_REGION:
        return MUNICIPALITY_REGION[municipality_name]

    # Normalised match
    norm = _normalize(municipality_name)
    canonical = _REGION_INDEX.get(norm)
    if canonical:
        return MUNICIPALITY_REGION[canonical]

    return None


def get_border_info(municipality_name: str) -> Optional[dict]:
    """Return border municipality info dict if this is a border municipality, else None."""
    norm = _normalize(municipality_name)
    return _BORDER_INDEX.get(norm)


def is_border_municipality(municipality_name: str) -> bool:
    """Return True if this municipality sits on a zone boundary."""
    return get_border_info(municipality_name) is not None


def get_border_municipalities() -> list[dict]:
    """Return the full border municipalities table."""
    return BORDER_MUNICIPALITIES


def list_regions() -> list[str]:
    """Return the four SE region codes."""
    return ["SE1", "SE2", "SE3", "SE4"]
