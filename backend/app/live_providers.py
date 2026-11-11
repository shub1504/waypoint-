"""Real-time data providers for trains (RailRadar) and flights (HasData).

Provides:
- Station and airport code resolution with multi-station city support and fuzzy matching
- search_trains_live(origin, destination, date): Multi-station parallel search, real RailRadar field mapping
- search_flights_live(origin, destination, date): HasData Google Flights with INR pricing
- train_live_status(train_number): Live running status, delay, and current station
- extract_travel_date(text): Asia/Kolkata date resolution (tomorrow, friday, etc.)
- extract_travel_entities(text): Route, mode, and date extraction
"""
import concurrent.futures
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import difflib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from app import config

log = logging.getLogger("waypoint.live_providers")

RAILRADAR_BASE_URL = "https://api.railradar.in/v1"
HASDATA_FLIGHTS_URL = "https://api.hasdata.com/scrape/google/flights"

CACHE_TTL_SECONDS = 90  # 60-120s TTL
_CACHE: Dict[str, tuple[float, Any]] = {}

# Major Indian cities with multiple railway stations
CITY_STATIONS: dict[str, list[str]] = {
    "mumbai": ["CSMT", "BCT", "DR", "LTT", "BDTS", "MMCT"],
    "bombay": ["CSMT", "BCT", "DR", "LTT", "BDTS", "MMCT"],
    "delhi": ["NDLS", "DLI", "NZM", "ANVT", "DEE"],
    "dilli": ["NDLS", "DLI", "NZM", "ANVT", "DEE"],
    "new delhi": ["NDLS", "DLI", "NZM", "ANVT", "DEE"],
    "kolkata": ["HWH", "SDAH", "KOAA", "SHM"],
    "calcutta": ["HWH", "SDAH", "KOAA", "SHM"],
    "chennai": ["MAS", "MS", "TBM"],
    "madras": ["MAS", "MS", "TBM"],
    "bengaluru": ["SBC", "YPR", "SMVB"],
    "bangalore": ["SBC", "YPR", "SMVB"],
    "hyderabad": ["HYB", "SC", "KCG"],
    "secunderabad": ["SC", "HYB", "KCG"],
    "pune": ["PUNE", "SVJR", "HDP"],
    "ahmedabad": ["ADI", "SBT"],
    "lucknow": ["LKO", "LJN", "ASH"],
    "indore": ["INDB"],
    "ujjain": ["UJN"],
    "jaipur": ["JP", "GADJ", "DPA"],
    "bhopal": ["BPL", "RKMP"],
    "goa": ["MAO", "KRMI", "THVM"],
    "varanasi": ["BSB", "DDU"],
    "banaras": ["BSB", "DDU"],
    "agra": ["AGC", "AF"],
    "patna": ["PNBE", "RJPB", "DNR"],
    "chandigarh": ["CDG"],
    "amritsar": ["ASR"],
    "ludhiana": ["LDH"],
    "jalandhar": ["JUC", "JRC"],
    "bathinda": ["BTI"],
    "patiala": ["PTA"],
    "punjab": ["LDH", "ASR", "JUC", "BTI"],
    "kerala": ["ERS", "TVC", "CLT"],
    "rajasthan": ["JP", "JU", "UDZ", "AII", "KOTA"],
    "gujarat": ["ADI", "ST", "BRC", "RJT"],
    "bihar": ["PNBE", "DNR", "GAYA"],
    "kashmir": ["JAT", "SVDK"],
    "jammu": ["JAT", "SVDK"],
    "uttarakhand": ["DDN", "HW", "KGM"],
    "himachal": ["KLK", "SML", "CDG"],
    "himachal pradesh": ["KLK", "SML", "CDG"],
    "up": ["LKO", "CNB", "BSB", "PRYJ", "AGC"],
    "uttar pradesh": ["LKO", "CNB", "BSB", "PRYJ", "AGC"],
    "mp": ["BPL", "INDB", "GWL", "JBP", "UJN"],
    "madhya pradesh": ["BPL", "INDB", "GWL", "JBP", "UJN"],
    "maharashtra": ["CSMT", "PUNE", "NGP", "NK"],
    "tamil nadu": ["MAS", "CBE", "MDU"],
    "karnataka": ["SBC", "MYS", "UBL", "MAQ"],
    "west bengal": ["HWH", "SDAH", "NJP"],
    "bengal": ["HWH", "SDAH", "NJP"],
    "odisha": ["BBS", "PURI", "CTC"],
    "orissa": ["BBS", "PURI", "CTC"],
    "assam": ["GHY"],
    "haryana": ["UMB", "CDG"],
}

# Individual specific station names that mean a single specific station (do NOT expand to whole city)
SPECIFIC_STATIONS: dict[str, str] = {
    "csmt": "CSMT",
    "cst": "CSMT",
    "chhatrapati shivaji": "CSMT",
    "bct": "BCT",
    "mumbai central": "MMCT",
    "mmct": "MMCT",
    "bandra": "BDTS",
    "bandra terminus": "BDTS",
    "bdts": "BDTS",
    "lokmanya tilak": "LTT",
    "ltt": "LTT",
    "dadar": "DR",
    "dr": "DR",
    "ndls": "NDLS",
    "new delhi station": "NDLS",
    "old delhi": "DLI",
    "dli": "DLI",
    "delhi junction": "DLI",
    "nizamuddin": "NZM",
    "hazrat nizamuddin": "NZM",
    "nzm": "NZM",
    "anand vihar": "ANVT",
    "anvt": "ANVT",
    "sarai rohilla": "DEE",
    "delhi sarai rohilla": "DEE",
    "dee": "DEE",
    "howrah": "HWH",
    "hwh": "HWH",
    "sealdah": "SDAH",
    "sdah": "SDAH",
    "shalimar": "SHM",
    "shm": "SHM",
    "kolkata station": "KOAA",
    "koaa": "KOAA",
    "chennai central": "MAS",
    "mas": "MAS",
    "chennai egmore": "MS",
    "ms": "MS",
    "tambaram": "TBM",
    "tbm": "TBM",
    "ksr bengaluru": "SBC",
    "sbc": "SBC",
    "yesvantpur": "YPR",
    "ypr": "YPR",
    "smvb": "SMVB",
    "sir m visvesvaraya": "SMVB",
    "secunderabad station": "SC",
    "sc": "SC",
    "hyderabad deccan": "HYB",
    "hyb": "HYB",
    "kachiguda": "KCG",
    "kcg": "KCG",
    "rani kamlapati": "RKMP",
    "rkmp": "RKMP",
    "habibganj": "RKMP",
    "indb": "INDB",
    "indore jn": "INDB",
    "ujn": "UJN",
    "ujjain jn": "UJN",
}

STATION_MAP = {
    "delhi": "NDLS",
    "dilli": "NDLS",
    "new delhi": "NDLS",
    "ndls": "NDLS",
    "old delhi": "DLI",
    "hazrat nizamuddin": "NZM",
    "nizamuddin": "NZM",
    "mumbai": "CSMT",
    "bombay": "CSMT",
    "csmt": "CSMT",
    "mumbai central": "MMCT",
    "indore": "INDB",
    "indb": "INDB",
    "ujjain": "UJN",
    "ujn": "UJN",
    "jaipur": "JP",
    "jp": "JP",
    "bhopal": "BPL",
    "bpl": "BPL",
    "habibganj": "RKMP",
    "rani kamlapati": "RKMP",
    "goa": "MAO",
    "madgaon": "MAO",
    "margao": "MAO",
    "bangalore": "SBC",
    "bengaluru": "SBC",
    "sbc": "SBC",
    "chennai": "MAS",
    "madras": "MAS",
    "mas": "MAS",
    "kolkata": "HWH",
    "calcutta": "HWH",
    "howrah": "HWH",
    "sealdah": "SDAH",
    "varanasi": "BSB",
    "banaras": "BSB",
    "kashi": "BSB",
    "bsb": "BSB",
    "agra": "AGC",
    "agc": "AGC",
    "ahmedabad": "ADI",
    "adi": "ADI",
    "pune": "PUNE",
    "hyderabad": "HYB",
    "secunderabad": "SC",
    "chandigarh": "CDG",
    "amritsar": "ASR",
    "dewas": "DWX",
    "dwx": "DWX",
    "lucknow": "LKO",
    "lko": "LKO",
    "patna": "PNBE",
    "pnbe": "PNBE",
    "surat": "ST",
    "nagpur": "NGP",
    "kanpur": "CNB",
    "gwalior": "GWL",
    "mathura": "MTJ",
    "haridwar": "HW",
    "rishikesh": "RKSH",
    "dehradun": "DDN",
    "shimla": "SML",
    "ayodhya": "AY",
    "manali": "CDG",
    "punjab": "LDH",
    "ludhiana": "LDH",
    "ldh": "LDH",
    "jalandhar": "JUC",
    "juc": "JUC",
    "jalandhar cantt": "JRC",
    "jrc": "JRC",
    "bathinda": "BTI",
    "bti": "BTI",
    "patiala": "PTA",
    "pta": "PTA",
    "pathankot": "PTK",
    "ptk": "PTK",
    "mohali": "SASN",
    "sasn": "SASN",
    "ambala": "UMB",
    "umb": "UMB",
    "ambala cantt": "UMB",
    "panipat": "PNP",
    "pnp": "PNP",
    "kurukshetra": "KKDE",
    "kkde": "KKDE",
    "kalka": "KLK",
    "klk": "KLK",
    "jodhpur": "JU",
    "ju": "JU",
    "udaipur": "UDZ",
    "udz": "UDZ",
    "ajmer": "AII",
    "aii": "AII",
    "kota": "KOTA",
    "bikaner": "BKN",
    "bkn": "BKN",
    "vadodara": "BRC",
    "brc": "BRC",
    "baroda": "BRC",
    "rajkot": "RJT",
    "rjt": "RJT",
    "bhavnagar": "BVC",
    "bvc": "BVC",
    "jamnagar": "JAM",
    "jam": "JAM",
    "jabalpur": "JBP",
    "jbp": "JBP",
    "allahabad": "PRYJ",
    "prayagraj": "PRYJ",
    "pryj": "PRYJ",
    "gorakhpur": "GKP",
    "gkp": "GKP",
    "jhansi": "VGLJ",
    "vglj": "VGLJ",
    "virangana lakshmibai": "VGLJ",
    "moradabad": "MB",
    "mb": "MB",
    "bareilly": "BE",
    "be": "BE",
    "aligarh": "ALJN",
    "aljn": "ALJN",
    "meerut": "MTC",
    "mtc": "MTC",
    "kathgodam": "KGM",
    "kgm": "KGM",
    "haldwani": "HDW",
    "hdw": "HDW",
    "roorkee": "RK",
    "rk": "RK",
    "kerala": "ERS",
    "ernakulam": "ERS",
    "ers": "ERS",
    "kochi": "ERS",
    "cochin": "ERS",
    "trivandrum": "TVC",
    "thiruvananthapuram": "TVC",
    "tvc": "TVC",
    "calicut": "CLT",
    "kozhikode": "CLT",
    "clt": "CLT",
    "thrissur": "TCR",
    "tcr": "TCR",
    "kollam": "QLN",
    "qln": "QLN",
    "palakkad": "PGT",
    "pgt": "PGT",
    "alappuzha": "ALLP",
    "allp": "ALLP",
    "kottayam": "KTYM",
    "ktym": "KTYM",
    "kannur": "CAN",
    "can": "CAN",
    "coimbatore": "CBE",
    "cbe": "CBE",
    "madurai": "MDU",
    "mdu": "MDU",
    "tiruchirappalli": "TPJ",
    "trichy": "TPJ",
    "tpj": "TPJ",
    "salem": "SA",
    "sa": "SA",
    "tirunelveli": "TEN",
    "ten": "TEN",
    "erode": "ED",
    "ed": "ED",
    "vellore": "KPD",
    "katpadi": "KPD",
    "kpd": "KPD",
    "mysore": "MYS",
    "mysuru": "MYS",
    "mys": "MYS",
    "hubli": "UBL",
    "hubballi": "UBL",
    "ubl": "UBL",
    "mangalore": "MAQ",
    "mangaluru": "MAQ",
    "maq": "MAQ",
    "belgaum": "BGM",
    "belagavi": "BGM",
    "bgm": "BGM",
    "gulbarga": "KLBG",
    "kalaburagi": "KLBG",
    "klbg": "KLBG",
    "bhubaneswar": "BBS",
    "bbs": "BBS",
    "puri": "PURI",
    "cuttack": "CTC",
    "ctc": "CTC",
    "rourkela": "ROU",
    "rou": "ROU",
    "berhampur": "BAM",
    "bam": "BAM",
    "ranchi": "RNC",
    "rnc": "RNC",
    "dhanbad": "DHN",
    "dhn": "DHN",
    "tatanagar": "TATA",
    "tata": "TATA",
    "jamshedpur": "TATA",
    "bokaro": "BKSC",
    "bksc": "BKSC",
    "guwahati": "GHY",
    "ghy": "GHY",
    "siliguri": "NJP",
    "new jalpaiguri": "NJP",
    "njp": "NJP",
    "jammu": "JAT",
    "jammu tawi": "JAT",
    "jat": "JAT",
    "katra": "SVDK",
    "svdk": "SVDK",
    "vaishno devi": "SVDK",
    "udhampur": "UHP",
    "uhp": "UHP",
    "shirdi": "SNSI",
    "sainagar shirdi": "SNSI",
    "snsi": "SNSI",
    "tirupati": "TPTY",
    "tpty": "TPTY",
    "vijayawada": "BZA",
    "bza": "BZA",
    "visakhapatnam": "VSKP",
    "vizag": "VSKP",
    "vskp": "VSKP",
    "warangal": "WL",
    "wl": "WL",
    "raipur": "R",
    "bilaspur": "BSP",
    "bsp": "BSP",
    "durg": "DURG",
    "nashik": "NK",
    "nasik": "NK",
    "nk": "NK",
    "aurangabad": "AWB",
    "chhatrapati sambhajinagar": "AWB",
    "awb": "AWB",
    "solapur": "SUR",
    "sur": "SUR",
    "kolhapur": "KOP",
    "kop": "KOP",
}

AIRPORT_MAP = {
    "delhi": "DEL",
    "dilli": "DEL",
    "new delhi": "DEL",
    "del": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bom": "BOM",
    "indore": "IDR",
    "idr": "IDR",
    "ujjain": "IDR",
    "jaipur": "JAI",
    "jai": "JAI",
    "bhopal": "BHO",
    "bho": "BHO",
    "goa": "GOI",
    "goi": "GOI",
    "mopa": "GOX",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "blr": "BLR",
    "chennai": "MAA",
    "madras": "MAA",
    "maa": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "ccu": "CCU",
    "hyderabad": "HYD",
    "hyd": "HYD",
    "pune": "PNQ",
    "pnq": "PNQ",
    "ahmedabad": "AMD",
    "amd": "AMD",
    "chandigarh": "IXC",
    "ixc": "IXC",
    "amritsar": "ATQ",
    "atq": "ATQ",
    "varanasi": "VNS",
    "vns": "VNS",
    "lucknow": "LKO",
    "patna": "PAT",
    "surat": "STV",
    "nagpur": "NAG",
    "dehradun": "DED",
    "kochi": "COK",
    "cochin": "COK",
    "srinagar": "SXR",
    "manali": "KUU",
    "kullu": "KUU",
    "punjab": "ATQ",
    "ludhiana": "LUH",
    "mohali": "IXC",
    "kerala": "COK",
    "rajasthan": "JAI",
    "gujarat": "AMD",
    "jammu": "IXJ",
    "kashmir": "SXR",
    "madhya pradesh": "BHO",
    "bihar": "PAT",
    "uttarakhand": "DED",
    "himachal": "KUU",
}


def _cache_get(key: str) -> Optional[Any]:
    now = time.time()
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts <= CACHE_TTL_SECONDS:
            return deepcopy(val)
        _CACHE.pop(key, None)
    return None


def _cache_set(key: str, val: Any) -> None:
    _CACHE[key] = (time.time(), deepcopy(val))


def clear_cache() -> None:
    _CACHE.clear()


def _http_get_with_retry(url: str, headers: dict, params: dict, timeout: float = 8.0) -> httpx.Response:
    """GET request with timeout <= 8s and 1 retry."""
    last_exc = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(1.2)
                    continue
                return resp
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.3)
                continue
    raise last_exc or RuntimeError("HTTP request failed after retry")


def _lookup_station_railradar(query: str) -> List[str]:
    """Query RailRadar autocomplete API for unmapped station names or smaller towns."""
    q = query.strip()
    if not q or len(q) < 2:
        return []

    cache_key = f"railradar_station_search:{q.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    key = config.RAILRADAR_API_KEY
    if not key:
        return []

    url = f"{RAILRADAR_BASE_URL}/lookup/search/stations"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    params = {"q": q, "limit": 5}

    try:
        resp = _http_get_with_retry(url, headers=headers, params=params, timeout=5.0)
        if resp.status_code != 200:
            return []
        data = resp.json()
        stations = []
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, list):
                stations = inner
            elif isinstance(inner, dict):
                stations = inner.get("stations") or inner.get("results") or []
            elif "stations" in data:
                stations = data.get("stations") or []
        elif isinstance(data, list):
            stations = data

        codes = []
        for s in stations:
            if isinstance(s, dict):
                code = s.get("code") or s.get("stationCode") or s.get("station_code")
                if code and isinstance(code, str):
                    c = code.upper().strip()
                    if c not in codes:
                        codes.append(c)
        if codes:
            _cache_set(cache_key, codes)
            return codes
    except Exception as exc:
        log.warning("RailRadar station search failed for '%s': %s", q, exc)

    return []


def _clean_query(q: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", q).strip().lower()
    clean = re.sub(r"\s+", " ", clean)
    stopwords = {"se", "to", "city", "jn", "junction", "station", "cantt", "the"}
    tokens = [w for w in clean.split() if w not in stopwords]
    return " ".join(tokens) if tokens else clean


def resolve_station_code(query: str) -> Optional[str]:
    """Resolve query to a single primary station code."""
    codes = resolve_station_codes(query)
    return codes[0] if codes else None


def resolve_station_codes(query: str) -> List[str]:
    """Resolve a city, state, or station name to station code(s).
    If the user names a specific station (e.g. BDTS, Nizamuddin), returns only [that_code].
    If the user names a multi-station city/state (e.g. Mumbai, Delhi, Punjab, Kerala), returns ALL major station codes.
    Falls back to fuzzy matching and live RailRadar autocomplete search.
    """
    if not query or not query.strip():
        return []
    raw = query.strip()
    clean = _clean_query(raw)
    upper = raw.upper()

    # 1. Exact specific code match (e.g. "BDTS", "NDLS", "CSMT", "LTT", "LDH")
    if re.match(r"^[A-Za-z]{2,5}$", raw):
        if upper in SPECIFIC_STATIONS.values() or upper in STATION_MAP.values():
            return [upper]

    # 2. Specific station name (e.g. "nizamuddin", "bandra terminus", "mumbai central")
    if clean in SPECIFIC_STATIONS:
        return [SPECIFIC_STATIONS[clean]]
    if raw.lower() in SPECIFIC_STATIONS:
        return [SPECIFIC_STATIONS[raw.lower()]]

    # 3. Multi-station city/state exact match (e.g. "mumbai", "delhi", "punjab", "kerala")
    if clean in CITY_STATIONS:
        return CITY_STATIONS[clean]
    if raw.lower() in CITY_STATIONS:
        return CITY_STATIONS[raw.lower()]

    # 4. Fallback STATION_MAP exact match
    if clean in STATION_MAP:
        return [STATION_MAP[clean]]
    if raw.lower() in STATION_MAP:
        return [STATION_MAP[raw.lower()]]

    # 5. Fuzzy match against CITY_STATIONS keys
    city_matches = difflib.get_close_matches(clean, list(CITY_STATIONS.keys()), n=1, cutoff=0.7)
    if city_matches:
        return CITY_STATIONS[city_matches[0]]

    # 6. Fuzzy match against SPECIFIC_STATIONS keys
    spec_matches = difflib.get_close_matches(clean, list(SPECIFIC_STATIONS.keys()), n=1, cutoff=0.75)
    if spec_matches:
        return [SPECIFIC_STATIONS[spec_matches[0]]]

    # 7. Fuzzy match against STATION_MAP keys
    map_matches = difflib.get_close_matches(clean, list(STATION_MAP.keys()), n=1, cutoff=0.7)
    if map_matches:
        return [STATION_MAP[map_matches[0]]]

    # 8. Substring match for compound names (e.g. "ludhiana junction", "amritsar cantt")
    for k, v in CITY_STATIONS.items():
        if len(k) >= 4 and (k in clean or clean in k):
            return v
    for k, v in STATION_MAP.items():
        if len(k) >= 4 and (k in clean or clean in k):
            return [v]

    # 9. Dynamic live RailRadar station autocomplete search
    api_codes = _lookup_station_railradar(raw)
    if api_codes:
        return api_codes

    # 10. Fallback to uppercase if it looks like a valid station code
    if re.match(r"^[A-Za-z]{2,5}$", raw):
        return [upper]

    return []


def lookup_station_candidates(query: str) -> List[Dict[str, Any]]:
    if not query:
        return []
    codes = resolve_station_codes(query)
    if codes:
        return [{"code": c, "name": query.title(), "type": "station"} for c in codes]
    return []


def resolve_airport_code(query: str) -> Optional[str]:
    """Resolve city name or input to a 3-letter IATA airport code."""
    if not query or not query.strip():
        return None
    q = query.strip()
    clean = _clean_query(q)

    if clean in AIRPORT_MAP:
        return AIRPORT_MAP[clean]
    if q.lower() in AIRPORT_MAP:
        return AIRPORT_MAP[q.lower()]

    for key, code in AIRPORT_MAP.items():
        if key in clean or clean in key:
            return code

    matches = difflib.get_close_matches(clean, list(AIRPORT_MAP.keys()), n=1, cutoff=0.7)
    if matches:
        return AIRPORT_MAP[matches[0]]

    if re.match(r"^[A-Za-z]{3}$", q):
        return q.upper()

    return None


def lookup_airport_candidates(query: str) -> List[Dict[str, Any]]:
    if not query:
        return []
    code = resolve_airport_code(query)
    if code:
        return [{"code": code, "name": query.title(), "type": "airport"}]
    return []


def extract_travel_date(text: str) -> Tuple[str, str]:
    """Extract and resolve relative date from text into (YYYY-MM-DD, Display String) in Asia/Kolkata."""
    try:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now = datetime.now()

    t = text.lower()

    if any(w in t for w in ["tomorrow", "tmrw", "tomorow", "kal"]):
        d = now + timedelta(days=1)
        return d.strftime("%Y-%m-%d"), d.strftime("%d %b")

    if any(w in t for w in ["parso", "day after tomorrow"]):
        d = now + timedelta(days=2)
        return d.strftime("%Y-%m-%d"), d.strftime("%d %b")

    if any(w in t for w in ["today", "aaj"]):
        return now.strftime("%Y-%m-%d"), now.strftime("%d %b")

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for idx, day in enumerate(days):
        if day in t:
            curr_day = now.weekday()
            diff = (idx - curr_day) % 7
            if diff == 0:
                diff = 7  # Upcoming day next week
            d = now + timedelta(days=diff)
            return d.strftime("%Y-%m-%d"), d.strftime("%d %b")

    # Match explicit date like "2026-11-15"
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m_iso:
        dt = datetime.strptime(m_iso.group(1), "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d"), dt.strftime("%d %b")

    # Match explicit date like "15 nov" or "15 november"
    m_date = re.search(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t)
    if m_date:
        day_num = int(m_date.group(1))
        mon_str = m_date.group(2).title()
        try:
            dt = datetime.strptime(f"{day_num} {mon_str} {now.year}", "%d %b %Y")
            if dt < now:
                dt = dt.replace(year=now.year + 1)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%d %b")
        except ValueError:
            pass

    return "", ""


def extract_travel_entities(text: str) -> Dict[str, Any]:
    """Extract origin, destination, travel mode, date, and train number from free-form prompt."""
    t = text.strip()
    mode = "flight" if any(w in t.lower() for w in ["flight", "airline", "fly", "flihgt", "plane", "air"]) else "train"
    date_iso, date_display = extract_travel_date(t)

    m_train = re.search(r"\b(\d{5})\b", t)
    train_number = m_train.group(1) if m_train else None

    # Clean sentence for origin/destination extraction
    cleaned = t
    # 1. Strip mode phrases e.g. "train se", "flight se", "by train" so "se" isn't left behind as an ablative marker
    cleaned = re.sub(
        r"\b(train\s+se|flight\s+se|plane\s+se|gadi\s+se|by\s+train|by\s+flight|by\s+air|by\s+plane)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 2. Strip Hinglish pronouns & polite filler
    cleaned = re.sub(
        r"\b(mujhe|hume|humko|mera|meri|mere|aap|kripya|please)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 3. Strip intent verbs & suffixes
    cleaned = re.sub(
        r"\b(jana\s+hai|jaana\s+hai|nikalna\s+hai|aana\s+hai|aaana\s+hai|pahunchna\s+hai|chahiye|travel\s+karna\s+hai|batao|bataiye|dekhna\s+hai)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 4. Strip English lead-ins
    cleaned = re.sub(
        r"\b(tell me about|i wanna go|i want to go|i need to go|search|show me|find|look for)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 5. Strip date tokens (already extracted)
    cleaned = re.sub(
        r"\b(today|tomorrow|tmrw|kal|parso|aaj|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 6. Strip bare transport words & typos
    cleaned = re.sub(
        r"\b(trains?|flights?|flihgt|cheapest|airline)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    orig, dest = "", ""
    m_route = re.search(r"(?:from\s+)?([a-zA-Z\s]+?)\s+(?:to|se)\s+([a-zA-Z\s]+)", cleaned, re.IGNORECASE)
    if m_route:
        orig = m_route.group(1).strip()
        dest = m_route.group(2).strip()
    elif " - " in cleaned or " -> " in cleaned:
        delim = " - " if " - " in cleaned else " -> "
        parts = cleaned.split(delim)
        orig, dest = parts[0].strip(), parts[1].strip()

    # Clean any residual trailing words from destination or origin
    if dest:
        dest = re.sub(r"\b(jana\s+hai|jaana\s+hai|hai|se)\b", "", dest, flags=re.IGNORECASE).strip()
    if orig:
        orig = re.sub(r"\b(hai|se|from)\b", "", orig, flags=re.IGNORECASE).strip()

    return {
        "mode": mode,
        "origin": orig,
        "destination": dest,
        "date": date_iso,
        "date_display": date_display,
        "train_number": train_number,
    }


def _fetch_single_station_pair(
    orig_code: str,
    dest_code: str,
    date: str,
    headers: dict,
) -> Dict[str, Any]:
    """Query RailRadar for trains between one specific pair of stations."""
    pair_cache_key = f"railradar_single:{orig_code}:{dest_code}:{date}"
    cached = _cache_get(pair_cache_key)
    if cached is not None:
        return cached

    url = f"{RAILRADAR_BASE_URL}/trains/between/{orig_code}/{dest_code}"
    params = {}
    if date:
        params["date"] = date

    try:
        resp = _http_get_with_retry(url, headers=headers, params=params, timeout=8.0)
        status_code = resp.status_code
        if status_code != 200:
            err_detail = None
            try:
                err_detail = resp.json().get("error", {}).get("message")
            except Exception:
                pass
            return {"status_code": status_code, "trains": [], "error": err_detail}

        body = resp.json()
        data_block = body.get("data") if isinstance(body, dict) else {}
        train_list = []
        if isinstance(data_block, dict):
            train_list = data_block.get("trains") or []
        elif isinstance(data_block, list):
            train_list = data_block
        elif isinstance(body, dict) and "trains" in body:
            train_list = body.get("trains") or []

        parsed = []
        for item in train_list:
            if not isinstance(item, dict):
                continue
            t_obj = item.get("train") if isinstance(item.get("train"), dict) else item
            t_num = str(
                t_obj.get("number")
                or t_obj.get("trainNumber")
                or t_obj.get("train_number")
                or item.get("number")
                or item.get("trainNumber")
                or item.get("train_number")
                or ""
            )
            t_name = str(
                t_obj.get("name")
                or t_obj.get("trainName")
                or t_obj.get("train_name")
                or item.get("name")
                or item.get("trainName")
                or item.get("train_name")
                or f"Express ({t_num})"
            )

            from_info = item.get("from") if isinstance(item.get("from"), dict) else {}
            to_info = item.get("to") if isinstance(item.get("to"), dict) else {}

            dep_time = from_info.get("departure") or item.get("departure_time") or item.get("departure") or "N/A"
            arr_time = to_info.get("arrival") or item.get("arrival_time") or item.get("arrival") or "N/A"
            dep_st = from_info.get("code") or orig_code
            arr_st = to_info.get("code") or dest_code

            dep_day = from_info.get("day")
            arr_day = to_info.get("day")
            day_diff = 0
            if isinstance(arr_day, int) and isinstance(dep_day, int) and arr_day > dep_day:
                day_diff = arr_day - dep_day
            elif arr_time != "N/A" and dep_time != "N/A" and arr_time < dep_time:
                day_diff = 1

            day_str = f" (+{day_diff} day)" if day_diff == 1 else (f" (+{day_diff} days)" if day_diff > 1 else "")

            # Duration in minutes -> formatted as Xh Ym
            raw_dur = item.get("duration")
            dur_str = "N/A"
            duration_min = None
            if isinstance(raw_dur, (int, float)):
                duration_min = int(raw_dur)
                h = duration_min // 60
                m = duration_min % 60
                dur_str = f"{h}h {m}m" if m else f"{h}h"
            elif isinstance(raw_dur, str) and raw_dur.isdigit():
                duration_min = int(raw_dur)
                h = duration_min // 60
                m = duration_min % 60
                dur_str = f"{h}h {m}m" if m else f"{h}h"
            elif isinstance(raw_dur, str) and raw_dur:
                dur_str = raw_dur

            raw_dist = item.get("distance")
            dist_km = round(float(raw_dist)) if raw_dist is not None else None
            dist_label = f"{dist_km} km" if dist_km is not None else ""

            # Clean line per train: Punjab Mail (12138): departs 16:35, arrives 12:10 (+1 day), 19h 35m
            summary_line = f"{t_name} ({t_num}): departs {dep_time} from {dep_st}, arrives {arr_time}{day_str} at {arr_st}, {dur_str}"
            if dist_label:
                summary_line += f" ({dist_label})"

            parsed.append({
                "option_id": t_num or f"train-{len(parsed)+1}",
                "id": t_num or f"T-{len(parsed)+1}",
                "train_number": t_num,
                "name": t_name,
                "title": f"{t_name} ({t_num})" if t_num and t_num not in t_name else t_name,
                "provider": "Indian Railways",
                "origin": dep_st,
                "destination": arr_st,
                "departure": dep_time,
                "departure_time": dep_time,
                "arrival": arr_time,
                "arrival_time": arr_time,
                "day_diff": day_diff,
                "day_str": day_str,
                "duration": dur_str,
                "duration_min": duration_min,
                "distance": dist_km,
                "distance_label": dist_label,
                "running_days": t_obj.get("runDays") or item.get("runDays") or [],
                "price": None,
                "price_inr": None,
                "price_known": False,
                "seats": None,
                "seats_known": False,
                "source": "railradar",
                "summary_line": summary_line,
                "fare_note": "Fares and seat availability must be verified on IRCTC.",
            })

        out = {"status_code": 200, "trains": parsed}
        _cache_set(pair_cache_key, out)
        return out

    except Exception as exc:
        log.warning("RailRadar single pair error %s->%s: %s", orig_code, dest_code, exc)
        return {"status_code": 500, "trains": [], "error": str(exc)}


def search_trains_live(origin: str, destination: str, date: str = "") -> dict:
    """Search live train schedule and running info between stations/cities using RailRadar.

    Multi-station city search in parallel (Mumbai: CSMT, BCT, DR, LTT, BDTS; Delhi: NDLS, DLI, NZM, etc.).
    De-duplicates by train number, sorts soonest first, and limits display up to 8 trains.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    orig_stations = resolve_station_codes(origin)
    dest_stations = resolve_station_codes(destination)

    if not orig_stations or not dest_stations:
        return {
            "source": "railradar",
            "fetched_at": fetched_at,
            "origin": origin,
            "destination": destination,
            "trains": [],
            "error": f"Could not resolve station codes for '{origin}' or '{destination}'",
            "note": "Please specify recognized station names or cities.",
        }

    date_str = date.strip() if date else ""
    cache_key = f"trains_multi:{'-'.join(sorted(orig_stations))}:{'-'.join(sorted(dest_stations))}:{date_str}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    key = config.RAILRADAR_API_KEY
    if not key:
        return {
            "source": "railradar",
            "fetched_at": fetched_at,
            "origin": origin,
            "destination": destination,
            "date": date_str,
            "trains": [],
            "error": "RAILRADAR_API_KEY is not configured",
            "note": "Train schedules cannot be fetched live without an API key. Check IRCTC directly.",
        }

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    
    # Prioritize primary terminal combinations (up to 6 pairs to respect RailRadar 10 req/min rate limit)
    indexed_pairs = []
    for o_idx, o in enumerate(orig_stations):
        for d_idx, d in enumerate(dest_stations):
            if o != d:
                indexed_pairs.append((o_idx + d_idx, o, d))
    indexed_pairs.sort(key=lambda x: x[0])
    pairs = [(o, d) for _, o, d in indexed_pairs[:4]]

    all_trains: List[Dict[str, Any]] = []
    had_404 = False
    had_429 = False
    pair_errors = []

    # Run station pairs in parallel with 3 workers to prevent rate limit bursts
    workers = min(3, max(1, len(pairs)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_fetch_single_station_pair, o, d, date_str, headers): (o, d)
            for o, d in pairs
        }
        for fut in concurrent.futures.as_completed(future_map):
            res = fut.result()
            sc = res.get("status_code")
            if sc == 404:
                had_404 = True
            elif sc == 429:
                had_429 = True
            if res.get("error"):
                pair_errors.append(res["error"])
            all_trains.extend(res.get("trains", []))

    # De-duplicate by train number (keep unique trains)
    seen_trains = set()
    unique_trains = []
    for t in all_trains:
        num = t.get("train_number")
        if num and num in seen_trains:
            continue
        if num:
            seen_trains.add(num)
        unique_trains.append(t)

    # Sort soonest first by departure time
    def _dep_time_key(t):
        val = t.get("departure_time") or "99:99"
        if val == "N/A":
            return "99:99"
        return val

    unique_trains.sort(key=_dep_time_key)

    result = {
        "source": "railradar",
        "fetched_at": fetched_at,
        "origin": origin,
        "destination": destination,
        "origin_stations": orig_stations,
        "destination_stations": dest_stations,
        "date": date_str,
        "total_found": len(unique_trains),
        "trains": unique_trains,
        "had_404": had_404 and len(unique_trains) == 0,
        "note": "RailRadar provides live schedules and delays. Real-time fares and seat availability must be checked on IRCTC.",
    }
    if not unique_trains and had_429:
        result["error"] = "RailRadar rate limit reached (max 10 req/min). Please check IRCTC directly."
    elif not unique_trains and pair_errors:
        result["error"] = f"Failed to connect to RailRadar: {pair_errors[0]}"
    _cache_set(cache_key, result)
    return result


def train_live_status(train_number: str) -> dict:
    """Get live running status, delay, and current station for a train number via RailRadar."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    t_clean = re.sub(r"\D", "", str(train_number).strip())
    if not t_clean:
        return {
            "source": "railradar",
            "fetched_at": fetched_at,
            "train_number": train_number,
            "error": "A valid train number is required (e.g. 12919).",
        }

    cache_key = f"train_live:{t_clean}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    key = config.RAILRADAR_API_KEY
    if not key:
        return {
            "source": "railradar",
            "fetched_at": fetched_at,
            "train_number": t_clean,
            "error": "RAILRADAR_API_KEY is not configured",
            "status": "Unknown",
            "delay_min": 0,
            "note": "Live running status cannot be fetched without an API key. Check NTES/IRCTC.",
        }

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    url = f"{RAILRADAR_BASE_URL}/trains/{t_clean}/live"

    try:
        resp = _http_get_with_retry(url, headers=headers, params={}, timeout=8.0)
        if resp.status_code != 200:
            err_detail = None
            try:
                err_detail = resp.json().get("error", {}).get("message")
            except Exception:
                pass
            err_msg = err_detail or f"RailRadar returned status {resp.status_code}"
            res = {
                "source": "railradar",
                "fetched_at": fetched_at,
                "train_number": t_clean,
                "error": err_msg,
                "status": "Unavailable",
                "delay_min": 0,
            }
            if resp.status_code != 429:
                _cache_set(cache_key, res)
            return res

        body = resp.json()
        d = body.get("data") if isinstance(body, dict) else {}
        if not isinstance(d, dict):
            d = {}

        delay = d.get("delayMinutes") or d.get("delay") or d.get("delay_minutes") or 0
        curr_loc = d.get("currentLocation") or {}
        current_station = (
            curr_loc.get("stationName")
            or curr_loc.get("stationCode")
            or d.get("current_station_name")
            or d.get("current_station")
            or "In transit"
        )
        status_text = d.get("status") or d.get("running_status") or ("On Time" if delay == 0 else f"Late by {delay} min")
        delay_summary = "running on time" if delay == 0 else f"running late by {delay} min"

        t_name = d.get("trainName") or d.get("train_name") or f"Train {t_clean}"

        result = {
            "source": "railradar",
            "fetched_at": fetched_at,
            "train_number": t_clean,
            "train_name": t_name,
            "status": status_text,
            "delay_min": delay,
            "delay_summary": delay_summary,
            "current_station": current_station,
            "eta": d.get("eta") or d.get("expected_arrival") or "N/A",
            "updated_at": d.get("lastUpdatedAt") or fetched_at,
        }
        _cache_set(cache_key, result, )
        return result

    except Exception as exc:
        log.warning("RailRadar live status error for %s: %s", t_clean, exc)
        return {
            "source": "railradar",
            "fetched_at": fetched_at,
            "train_number": t_clean,
            "error": f"Failed to retrieve live status: {exc}",
            "status": "Unavailable",
            "delay_min": 0,
            "delay_summary": "Status unavailable",
        }


def search_flights_live(origin: str, destination: str, date: str = "") -> dict:
    """Search live flights via HasData Google Flights scraper API with INR currency."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    orig_code = resolve_airport_code(origin)
    dest_code = resolve_airport_code(destination)

    if not orig_code or not dest_code:
        return {
            "source": "hasdata",
            "fetched_at": fetched_at,
            "origin": origin,
            "destination": destination,
            "origin_code": orig_code,
            "destination_code": dest_code,
            "flights": [],
            "error": f"Could not resolve 3-letter IATA airport codes for '{origin}' or '{destination}'",
            "note": "Please specify major airport codes or city names (e.g. DEL, BOM, BLR).",
        }

    cache_key = f"flights:{orig_code}:{dest_code}:{date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    key = config.HASDATA_API_KEY
    if not key:
        return {
            "source": "hasdata",
            "fetched_at": fetched_at,
            "origin": orig_code,
            "destination": dest_code,
            "date": date,
            "flights": [],
            "error": "HASDATA_API_KEY is not configured",
            "note": "Live flight data cannot be fetched without an API key.",
        }

    if not date:
        try:
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        except Exception:
            now_ist = datetime.now()
        date = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "departureId": orig_code,
        "arrivalId": dest_code,
        "outboundDate": date,
        "type": "oneWay",
        "currency": "INR",
    }

    headers = {"x-api-key": key, "Accept": "application/json"}

    try:
        resp = _http_get_with_retry(HASDATA_FLIGHTS_URL, headers=headers, params=params, timeout=10.0)
        if resp.status_code != 200:
            log.warning("HasData flights returned %s: %s", resp.status_code, resp.text[:200])
            res = {
                "source": "hasdata",
                "fetched_at": fetched_at,
                "origin": orig_code,
                "destination": dest_code,
                "flights": [],
                "error": f"HasData API returned status {resp.status_code}",
            }
            _cache_set(cache_key, res)
            return res

        data = resp.json()
        raw_options = []
        if isinstance(data, dict):
            raw_options.extend(data.get("bestFlights") or [])
            raw_options.extend(data.get("otherFlights") or [])
        elif isinstance(data, list):
            raw_options = data

        normalized_flights: List[Dict[str, Any]] = []
        for idx, option in enumerate(raw_options):
            if not isinstance(option, dict):
                continue

            price = option.get("price")
            legs = option.get("flights") or []
            layovers = option.get("layovers") or []
            stops = len(layovers) if layovers else max(0, len(legs) - 1)
            total_dur = option.get("totalDuration")

            first_leg = legs[0] if (legs and isinstance(legs[0], dict)) else {}
            last_leg = legs[-1] if (legs and isinstance(legs[-1], dict)) else first_leg

            airline = first_leg.get("airline") or option.get("airline") or "Airline"
            flight_num = first_leg.get("flightNumber") or option.get("flightNumber") or f"FL-{idx+1}"

            dep_info = first_leg.get("departureAirport") if isinstance(first_leg.get("departureAirport"), dict) else {}
            arr_info = last_leg.get("arrivalAirport") if isinstance(last_leg.get("arrivalAirport"), dict) else {}

            dep_time = dep_info.get("time") or option.get("departure_time") or "N/A"
            arr_time = arr_info.get("time") or option.get("arrival_time") or "N/A"

            duration_h = round(total_dur / 60.0, 1) if isinstance(total_dur, (int, float)) else None
            dur_label = f"{duration_h}h" if duration_h else str(total_dur or "")

            normalized_flights.append({
                "option_id": flight_num or f"flight-{idx+1}",
                "id": flight_num,
                "airline": airline,
                "flight_number": flight_num,
                "name": f"{airline} {flight_num}",
                "title": f"{airline} {flight_num}",
                "provider": airline,
                "origin": orig_code,
                "destination": dest_code,
                "departure": dep_time,
                "departure_time": dep_time,
                "arrival": arr_time,
                "arrival_time": arr_time,
                "duration": dur_label,
                "duration_min": total_dur,
                "duration_h": duration_h,
                "stops": stops,
                "stops_label": "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}",
                "price": float(price) if price is not None else None,
                "price_inr": float(price) if price is not None else None,
                "price_known": price is not None,
                "source": "hasdata",
            })

        result = {
            "source": "hasdata",
            "fetched_at": fetched_at,
            "origin": orig_code,
            "destination": dest_code,
            "date": date or "any",
            "total_found": len(normalized_flights),
            "flights": normalized_flights,
        }
        _cache_set(cache_key, result)
        return result

    except Exception as exc:
        log.warning("HasData flights request failed: %s", exc)
        return {
            "source": "hasdata",
            "fetched_at": fetched_at,
            "origin": orig_code,
            "destination": dest_code,
            "flights": [],
            "error": f"Failed to retrieve flights: {exc}",
        }
