"""Heuristics for deciding whether a posting is in the US, and which locations are preferred."""
from __future__ import annotations

import re
from typing import Iterable, Optional

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
    "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
}
US_CITY_HINTS = {
    "nyc", "sf", "la", "new york", "san francisco", "seattle", "bellevue", "redmond", "kirkland",
    "san jose", "sunnyvale", "mountain view", "palo alto", "menlo park", "cupertino", "santa clara",
    "los angeles", "san diego", "irvine", "austin", "chicago", "boston", "cambridge, ma", "atlanta",
    "denver", "boulder", "portland", "pittsburgh", "philadelphia", "washington, dc", "arlington",
    "reston", "mclean", "dallas", "houston", "phoenix", "salt lake", "miami", "raleigh", "durham",
    "minneapolis", "detroit", "ann arbor", "st. louis", "columbus", "nashville", "charlotte",
    "san mateo", "foster city", "redwood city", "oakland", "berkeley", "fremont", "los gatos",
    "santa monica", "playa vista", "culver city", "bentonville", "bellevue", "new york city",
    "jersey city", "stamford", "greenwich", "madison", "santa barbara", "pasadena", "burbank",
}
NON_US_HINTS = {
    "canada", "toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo", "markham",
    "uk", "united kingdom", "london", "england", "scotland", "ireland", "dublin", "germany",
    "berlin", "munich", "france", "paris", "netherlands", "amsterdam", "spain", "madrid",
    "barcelona", "italy", "milan", "poland", "warsaw", "sweden", "stockholm", "switzerland",
    "zurich", "israel", "tel aviv", "india", "bangalore", "bengaluru", "hyderabad", "pune",
    "chennai", "mumbai", "gurgaon", "noida", "singapore", "japan", "tokyo", "china", "beijing",
    "shanghai", "shenzhen", "hangzhou", "hong kong", "taiwan", "taipei", "korea", "seoul",
    "australia", "sydney", "melbourne", "brazil", "sao paulo", "mexico", "argentina", "chile",
    "colombia", "philippines", "manila", "vietnam", "indonesia", "malaysia", "thailand",
    "uae", "dubai", "abu dhabi", "saudi", "egypt", "nigeria", "kenya", "south africa",
    "czech", "prague", "hungary", "budapest", "romania", "portugal", "lisbon", "belgium",
    "denmark", "copenhagen", "norway", "oslo", "finland", "helsinki", "austria", "vienna",
    "new zealand", "auckland", "remote in canada", "remote in uk", "remote in europe", "emea", "apac",
    "armenia", "yerevan", "gurugram", "gurgaon", "kolkata", "ahmedabad", "kochi", "jaipur", "lithuania",
    "vilnius", "latvia", "estonia", "tallinn", "ukraine", "kyiv", "serbia", "belgrade", "croatia", "zagreb",
    "bulgaria", "sofia", "greece", "athens", "turkey", "istanbul", "ankara", "pakistan", "bangladesh",
    "sri lanka", "nepal", "peru", "lima", "costa rica", "guatemala", "uruguay", "ecuador", "morocco",
    "tunisia", "ghana", "ethiopia", "qatar", "doha", "bahrain", "kuwait", "oman", "jordan", "lebanon",
    "luxembourg", "slovakia", "bratislava", "slovenia", "ljubljana", "iceland", "reykjavik", "malta",
    "cyprus", "georgia, tbilisi", "tbilisi", "kazakhstan", "almaty", "uzbekistan", "tashkent",
    "cambodia", "laos", "myanmar", "mongolia", "macau", "puerto rico",
}
NON_US_COUNTRY_CODES = {
    "can", "gbr", "uk", "ind", "irl", "deu", "fra", "nld", "esp", "ita", "pol", "swe", "che", "isr",
    "sgp", "jpn", "chn", "hkg", "twn", "kor", "aus", "bra", "mex", "arg", "chl", "col", "phl", "vnm",
    "idn", "mys", "tha", "are", "sau", "egy", "nga", "ken", "zaf", "cze", "hun", "rou", "prt", "bel",
    "dnk", "nor", "fin", "aut", "nzl", "arm", "ltu", "lva", "est", "ukr", "srb", "hrv", "bgr", "grc",
    "tur", "pak", "bgd", "lka", "per", "cri", "ury", "ecu", "mar", "lux", "svk", "svn", "isl", "mlt",
    "cyp", "geo", "kaz", "uzb", "khm", "mng", "mac", "pri",
}


def is_us(location: str) -> Optional[bool]:
    """True/False when confident, None when unknown."""
    if not location:
        return None
    t = location.strip()
    tl = t.lower()
    if any(h in tl for h in ("usa", "united states", "u.s.", "us -", "us,", "- us", ", us", "remote in us", "us remote")):
        return True
    if re.match(r"^us\b", tl):
        return True
    for h in NON_US_HINTS:
        if re.search(r"\b" + re.escape(h) + r"\b", tl):
            return False
    m3 = re.search(r",\s*([A-Za-z]{3})\.?$", t)
    if m3 and m3.group(1).lower() in NON_US_COUNTRY_CODES:
        return False
    m = re.search(r",\s*([A-Za-z]{2})\.?$", t)
    if m and m.group(1).upper() in US_STATES:
        return True
    if tl in US_STATE_NAMES or any(tl.endswith(", " + n) or tl == n for n in US_STATE_NAMES):
        return True
    for h in US_CITY_HINTS:
        if tl == h or tl.startswith(h + ",") or tl.startswith(h + " ") or (", " + h) in tl:
            return True
    if tl in ("remote", "remote - anywhere", "anywhere"):
        return None
    return None


def us_status(locations: Iterable[str]) -> Optional[bool]:
    """True if any location is US; False if all are known non-US; None if undetermined."""
    verdicts = [is_us(l) for l in locations]
    if any(v is True for v in verdicts):
        return True
    if verdicts and all(v is False for v in verdicts):
        return False
    return None


def matches_any(location: str, patterns: Iterable[str]) -> bool:
    tl = location.lower()
    return any(p.lower() in tl for p in patterns)


def only_in(locations: list[str], patterns: Iterable[str]) -> bool:
    """True when every location matches one of the patterns (e.g. Pittsburgh-only)."""
    locs = [l for l in locations if l]
    return bool(locs) and all(matches_any(l, patterns) for l in locs)


def any_preferred(locations: list[str], patterns: Iterable[str]) -> bool:
    return any(matches_any(l, patterns) for l in locations)
