"""Mock travel inventory (flights, trains, buses, hotels).

Real flight APIs were not usable for this prototype, so this module plays the role of the
supplier. It exposes the same few calls an API client would (search_transport, search_hotels),
so swapping in a real API later only touches this file.

`sold_out=True` simulates the "Ticket not available" demand spike from the deck.
"""
import zlib
from copy import deepcopy

# depart_in_h = hours from "now" until departure, duration_h = journey time
FLIGHTS = {
    ("DEL", "IDR"): [
        dict(id="F1", name="IndiGo 6E-512", depart_in_h=3, duration_h=1.9, price=4900, seats=4),
        dict(id="F2", name="Air India AI-663", depart_in_h=6, duration_h=2.0, price=5600, seats=2),
        dict(id="F3", name="Akasa QP-1411", depart_in_h=9, duration_h=1.9, price=5200, seats=6),
        dict(id="F4", name="IndiGo 6E-2044", depart_in_h=14, duration_h=2.1, price=4300, seats=9),
        dict(id="F5", name="Air India AI-659 (Business)", depart_in_h=4, duration_h=2.0, price=11800, seats=2),
    ],
    ("DEL", "BOM"): [
        dict(id="F6", name="Vistara UK-951", depart_in_h=2, duration_h=2.2, price=8900, seats=3),
        dict(id="F7", name="IndiGo 6E-6101", depart_in_h=4, duration_h=2.2, price=7400, seats=5),
        dict(id="F8", name="Akasa QP-1103", depart_in_h=7, duration_h=2.3, price=6900, seats=8),
        dict(id="F9", name="Air India AI-887", depart_in_h=11, duration_h=2.2, price=6400, seats=7),
    ],
    ("DEL", "JAI"): [
        dict(id="F10", name="IndiGo 6E-7011", depart_in_h=5, duration_h=1.1, price=3900, seats=4),
        dict(id="F11", name="SpiceJet SG-8194", depart_in_h=10, duration_h=1.1, price=3300, seats=6),
    ],
}

TRAINS = {
    ("UJN", "NDLS"): [
        dict(id="T1", name="Avantika Express 12961", depart_in_h=5, duration_h=15.0, price=1900, seats=12),
        dict(id="T2", name="Malwa Express 12919", depart_in_h=11, duration_h=16.5, price=1700, seats=9),
    ],
    ("INDB", "NDLS"): [
        dict(id="T3", name="Indore-Delhi Intercity 12415", depart_in_h=6, duration_h=14.0, price=1950, seats=20),
        dict(id="T4", name="Shipra Express 22947", depart_in_h=9, duration_h=15.0, price=1750, seats=14),
    ],
    ("DWX", "NDLS"): [
        dict(id="T5", name="Dewas Delhi Link 19320", depart_in_h=8, duration_h=17.0, price=1600, seats=10),
    ],
    ("JP", "NDLS"): [
        dict(id="T6", name="Shatabdi 12016", depart_in_h=4, duration_h=4.5, price=1400, seats=15),
    ],
}

BUSES = {
    ("UJN", "NDLS"): [
        dict(id="B1", name="Volvo Sleeper Ujjain-Delhi", depart_in_h=7, duration_h=18.0, price=1500, seats=14),
    ],
}

# Stations/airports close to a departure point, with the local cab leg to reach them.
NEARBY = {
    "UJN": [
        dict(code="INDB", name="Indore Jn", distance_km=55, cab_cost=750, cab_h=1.5),
        dict(code="DWX", name="Dewas Jn", distance_km=37, cab_cost=550, cab_h=1.0),
    ],
}

# Hotels near a trip's purpose place. distance_km = distance to that place.
HOTELS = {
    "Mahakaleshwar Temple": [
        dict(id="H1", name="Mahakal Residency", area="Temple Area", distance_km=0.3, price=2300, rooms=2),
        dict(id="H2", name="Avantika Grand", area="Temple Area", distance_km=0.6, price=3100, rooms=3),
        dict(id="H3", name="Shipra Palace", area="Shipra Ghat", distance_km=1.8, price=1500, rooms=5),
        dict(id="H4", name="Bus Stand Budget Inn", area="Bus Stand", distance_km=4.5, price=900, rooms=8),
        dict(id="H5", name="Heritage Mahal", area="Temple Area", distance_km=0.2, price=5200, rooms=1),
        dict(id="H6", name="Pilgrim Stay Annex", area="Temple Area", distance_km=0.5, price=1800, rooms=4),
    ],
    "Bandra Kurla Complex": [
        dict(id="H7", name="BKC Grand Suites", area="BKC", distance_km=0.4, price=10500, rooms=2),
        dict(id="H8", name="Kurla Business Inn", area="Kurla", distance_km=2.8, price=5200, rooms=6),
        dict(id="H9", name="Skyline BKC", area="BKC", distance_km=0.7, price=12800, rooms=3),
        dict(id="H10", name="Bandra Executive", area="Bandra", distance_km=1.4, price=9400, rooms=4),
    ],
    "Amber Fort": [
        dict(id="H11", name="Fort View Haveli", area="Amer", distance_km=0.6, price=1700, rooms=2),
        dict(id="H12", name="Amer Road Lodge", area="Amer", distance_km=1.1, price=1300, rooms=4),
        dict(id="H13", name="Railway Station Hotel", area="Station Road", distance_km=11.0, price=800, rooms=9),
        dict(id="H14", name="Pink City Heritage", area="Old City", distance_km=9.0, price=2600, rooms=3),
    ],
}


def _h(*parts) -> int:
    """Stable hash, so the same route always produces the same generated options."""
    return zlib.crc32("|".join(str(p) for p in parts).encode())


_SYN = {
    # kind: (names, depart_in_h, duration_h, price factors vs. the member's own booking)
    "FLIGHT": (["IndiGo 6E-{n}", "Air India AI-{n}", "Akasa QP-{n}", "Vistara UK-{n}", "Air India AI-{n} (Business)"],
               [3, 6, 9, 14, 4], 2.0, [0.9, 1.05, 1.2, 1.45, 2.4]),
    "TRAIN": (["{o} Express {n}", "{d} Superfast {n}", "Intercity {n}", "Rajdhani {n}"],
              [5, 8, 11, 16], 12.0, [0.85, 1.0, 1.15, 1.6]),
    "BUS": (["Volvo Sleeper {o}-{d}", "Semi-sleeper {o}-{d}", "AC Seater {o}-{d}"],
            [4, 7, 12], 11.0, [0.7, 0.85, 1.0]),
}


def _synth_transport(kind: str, origin: str, dest: str, ref_price: float | None) -> list[dict]:
    names, departs, dur, factors = _SYN[kind]
    base = ref_price or {"FLIGHT": 4500, "TRAIN": 1500, "BUS": 1200}[kind]
    out = []
    for i, (nm, dep, f) in enumerate(zip(names, departs, factors)):
        n = 100 + _h(kind, origin, dest, i) % 900
        out.append(dict(
            id=f"S{kind[0]}{i}", name=nm.format(o=origin, d=dest, n=n), depart_in_h=dep,
            duration_h=round(dur + (_h(kind, origin, dest, "d", i) % 6) / 10, 1),
            price=max(100, round(base * f / 50) * 50), seats=2 + _h(kind, origin, dest, "s", i) % 9,
        ))
    return out


def _synth_hotels(place: str, ref_price: float | None, area: str | None) -> list[dict]:
    base = ref_price or 2500
    short = (area or place).strip() or "Centre"
    spec = [("Residency", short, 0.3, 1.15), ("Grand", short, 0.6, 1.5), ("Palace", "Old Town", 1.8, 0.75),
            ("Budget Inn", "Station Road", 4.5, 0.45), ("Heritage", short, 0.2, 2.5), ("Stay Annex", short, 0.5, 0.9)]
    return [dict(id=f"SH{i}", name=f"{place.split()[0]} {nm}", area=ar, distance_km=km,
                 price=max(300, round(base * f / 50) * 50), rooms=1 + _h(place, i) % 6)
            for i, (nm, ar, km, f) in enumerate(spec)]


def _known_route(key) -> bool:
    return any(key in t for t in (FLIGHTS, TRAINS, BUSES))


def _known_origin(origin: str) -> bool:
    return any(origin == k[0] for t in (FLIGHTS, TRAINS, BUSES) for k in t)


def _pick(table, kind, key, sold_out, ref_price):
    if sold_out:
        return []
    if key in table:
        rows = deepcopy(table[key])
    elif _known_route(key):
        rows = []  # a curated demo route that simply has no service of this kind
    else:
        rows = _synth_transport(kind, key[0], key[1], ref_price)  # a route the member entered themselves
    return [o for o in rows if o["seats"] > 0]


def search_transport(kind: str, origin: str, dest: str, sold_out: bool = False, ref_price: float | None = None) -> list[dict]:
    """Known demo routes come from the tables above; any other route gets generated options priced
    around `ref_price` (what the member paid), so trips the member enters themselves also work."""
    table = {"FLIGHT": FLIGHTS, "TRAIN": TRAINS, "BUS": BUSES}[kind]
    return _pick(table, kind, (origin, dest), sold_out, ref_price)


def search_hotels(purpose_place: str, exclude_name: str | None = None,
                  ref_price: float | None = None, area: str | None = None) -> list[dict]:
    hotels = deepcopy(HOTELS[purpose_place]) if purpose_place in HOTELS else _synth_hotels(purpose_place, ref_price, area)
    return [h for h in hotels if h["rooms"] > 0 and h["name"] != exclude_name]


def nearby_points(origin: str) -> list[dict]:
    if origin in NEARBY:
        return deepcopy(NEARBY[origin])
    if _known_origin(origin):
        return []
    return [dict(code=f"{origin} Cantt", name=f"{origin} Cantt", distance_km=30, cab_cost=600, cab_h=1.0),
            dict(code=f"{origin} Jn", name=f"{origin} Junction", distance_km=48, cab_cost=800, cab_h=1.4)]
