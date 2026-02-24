"""Static mapping from Swedish municipality names to (latitude, longitude).

Keys use Swedish characters (UTF-8). The helper `get_coords` also does
case-insensitive and accent-tolerant look-ups so callers can pass names like
"Goteborg" instead of "Göteborg".
"""

from __future__ import annotations

import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Core coordinate dictionary – 50 most solar-relevant municipalities
# ---------------------------------------------------------------------------
MUNICIPALITY_COORDS: dict[str, tuple[float, float]] = {
    # Blekinge
    "Karlskrona": (56.1612, 15.5869),
    "Karlshamn": (56.1704, 14.8637),
    "Ronneby": (56.2104, 15.2782),
    "Sölvesborg": (56.0517, 14.5831),
    "Olofström": (56.2784, 14.5303),
    # Skåne (highest solar potential)
    "Malmö": (55.6050, 13.0038),
    "Helsingborg": (56.0465, 12.6945),
    "Kristianstad": (56.0294, 14.1567),
    "Lund": (55.7047, 13.1910),
    "Trelleborg": (55.3752, 13.1573),
    "Ystad": (55.4295, 13.8203),
    "Landskrona": (55.8706, 12.8301),
    "Ängelholm": (56.2428, 12.8616),
    "Simrishamn": (55.5561, 14.3554),
    # Västra Götaland
    "Göteborg": (57.7089, 11.9746),
    "Borås": (57.7210, 12.9401),
    "Trollhättan": (58.2836, 12.2886),
    "Skövde": (58.3908, 13.8453),
    "Uddevalla": (58.3514, 11.9380),
    "Varberg": (57.1057, 12.2504),
    "Falkenberg": (56.9054, 12.4912),
    "Halmstad": (56.6745, 12.8577),
    # Stockholm / Mälardalen
    "Stockholm": (59.3293, 18.0686),
    "Uppsala": (59.8586, 17.6389),
    "Västerås": (59.6099, 16.5448),
    "Örebro": (59.2741, 15.2066),
    "Eskilstuna": (59.3666, 16.5077),
    "Södertälje": (59.1955, 17.6253),
    "Nacka": (59.3112, 18.1638),
    "Huddinge": (59.2373, 17.9812),
    "Täby": (59.4440, 18.0688),
    "Linköping": (58.4108, 15.6214),
    "Norrköping": (58.5877, 16.1924),
    "Jönköping": (57.7826, 14.1618),
    "Växjö": (56.8777, 14.8091),
    "Kalmar": (56.6634, 16.3566),
    # Gotland (sunniest region)
    "Gotland": (57.4684, 18.4867),
    "Visby": (57.6348, 18.2948),
    # Östergötland / Småland
    "Eksjö": (57.6647, 14.9726),
    "Vetlanda": (57.4294, 15.0742),
    # Halland
    "Kungsbacka": (57.4883, 12.0764),
    "Laholm": (56.5102, 13.0432),
    # Mid-Sweden
    "Gävle": (60.6749, 17.1413),
    "Sundsvall": (62.3908, 17.3069),
    "Falun": (60.6065, 15.6355),
    "Borlänge": (60.4858, 15.4369),
    # North Sweden
    "Umeå": (63.8258, 20.2630),
    "Luleå": (65.5848, 22.1567),
    "Östersund": (63.1792, 14.6357),
}


def _normalize(name: str) -> str:
    """Lowercase + remove diacritics for fuzzy matching."""
    nfd = unicodedata.normalize("NFD", name.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


_NORMALIZED_INDEX: dict[str, str] = {
    _normalize(k): k for k in MUNICIPALITY_COORDS
}


def get_coords(municipality_name: str) -> Optional[tuple[float, float]]:
    """Return (lat, lon) for a municipality, or None if not found.

    Handles:
    - Exact match (preserving Swedish characters)
    - Case-insensitive match
    - Diacritic-stripped match (e.g. "Goteborg" → "Göteborg")
    """
    # 1. Exact match
    if municipality_name in MUNICIPALITY_COORDS:
        return MUNICIPALITY_COORDS[municipality_name]

    # 2. Normalize and look up
    normalized = _normalize(municipality_name)
    canonical = _NORMALIZED_INDEX.get(normalized)
    if canonical:
        return MUNICIPALITY_COORDS[canonical]

    return None


def list_municipalities() -> list[str]:
    """Return sorted list of known municipality names."""
    return sorted(MUNICIPALITY_COORDS.keys())
