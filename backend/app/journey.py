"""Deterministic train journey simulator and budget ranker for Waypoint."""
from datetime import datetime
import hashlib
import random
from typing import Any, Dict, List

CLASSES = ["1A", "2A", "3A", "SL", "CC"]

STATION_NAMES = {
    "NDLS": "New Delhi",
    "DEL": "Delhi",
    "DLI": "Old Delhi",
    "NZM": "Hazrat Nizamuddin",
    "UJN": "Ujjain",
    "INDB": "Indore",
    "BOM": "Mumbai",
    "MMCT": "Mumbai Central",
    "BDTS": "Bandra Terminus",
    "HWH": "Howrah",
    "SBC": "Bengaluru",
    "MAS": "Chennai",
    "JP": "Jaipur",
    "DWX": "Dewas",
    "BSB": "Varanasi",
    "LKO": "Lucknow",
    "PUNE": "Pune",
    "ADI": "Ahmedabad",
    "CNB": "Kanpur",
    "AGC": "Agra Cantt",
}

TRAIN_TEMPLATES = [
    "{dest} Superfast Express",
    "{orig} - {dest} SF Express",
    "{dest} Rajdhani Express",
    "{dest} Shatabdi Express",
    "{dest} Intercity Express",
    "{orig} - {dest} Vande Bharat",
    "{dest} Garib Rath Express",
    "{dest} Duronto Express",
    "{dest} Mail",
    "{orig} - {dest} Express",
]


def _station_title(code: str) -> str:
    cleaned = code.strip().upper()
    return STATION_NAMES.get(cleaned, cleaned)


def _make_rng(origin: str, destination: str, date_str: str) -> random.Random:
    key = f"{origin.strip().upper()}|{destination.strip().upper()}|{date_str.strip()}".encode("utf-8")
    seed_int = int(hashlib.sha256(key).hexdigest(), 16) % (2**32)
    return random.Random(seed_int)


def simulate_trains(origin: str, destination: str, date_str: str) -> List[Dict[str, Any]]:
    """Deterministic train simulator.

    Given origin, destination, and date, returns 3 to 5 trains with:
    train_no, name, departure, arrival, duration, and classes 1A, 2A, 3A, SL, CC.
    Guarantees realistic fare ordering: SL < 3A < 2A < 1A, with CC between SL and 2A.
    """
    orig_code = origin.strip().upper()
    dest_code = destination.strip().upper()
    orig_name = _station_title(orig_code)
    dest_name = _station_title(dest_code)

    rng = _make_rng(orig_code, dest_code, date_str)

    num_trains = rng.randint(3, 5)
    train_numbers = rng.sample(range(12001, 22999), num_trains)
    name_templates = rng.sample(TRAIN_TEMPLATES, num_trains)

    base_dur_mins = 360 + rng.randint(0, 8) * 45  # 6h to 12h base

    trains = []
    for i in range(num_trains):
        t_no = str(train_numbers[i])
        t_name = name_templates[i].format(orig=orig_name, dest=dest_name)

        dep_hour = rng.randint(5, 22)
        dep_min = rng.choice([0, 10, 15, 20, 30, 40, 45, 50])
        departure = f"{dep_hour:02d}:{dep_min:02d}"

        # Vary duration across trains
        train_dur_mins = base_dur_mins + (i * 35) + rng.randint(-15, 20)
        dur_h = max(3, train_dur_mins // 60)
        dur_m = train_dur_mins % 60
        duration = f"{dur_h}h {dur_m}m"

        arr_total = (dep_hour * 60 + dep_min + train_dur_mins) % (24 * 60)
        arrival = f"{arr_total // 60:02d}:{arr_total % 60:02d}"

        # Fares: realistic fare order SL < 3A < 2A < 1A, with CC between SL and 2A
        sl_fare = int(round((220 + dur_h * 24 + rng.randint(-10, 15)) / 10) * 10)
        cc_fare = int(round((sl_fare * 1.65 + rng.randint(0, 20)) / 10) * 10)
        a3_fare = int(round((sl_fare * 2.30 + rng.randint(0, 30)) / 10) * 10)
        a2_fare = int(round((sl_fare * 3.30 + rng.randint(0, 40)) / 10) * 10)
        a1_fare = int(round((sl_fare * 5.10 + rng.randint(0, 50)) / 10) * 10)

        # Enforce strict hierarchy: SL < CC < 3A < 2A < 1A
        if cc_fare <= sl_fare:
            cc_fare = sl_fare + 150
        if a3_fare <= cc_fare:
            a3_fare = cc_fare + 200
        if a2_fare <= a3_fare:
            a2_fare = a3_fare + 350
        if a1_fare <= a2_fare:
            a1_fare = a2_fare + 600

        fare_map = {
            "1A": a1_fare,
            "2A": a2_fare,
            "3A": a3_fare,
            "SL": sl_fare,
            "CC": cc_fare,
        }

        # Availability generation
        classes_data = []
        for cls_name in CLASSES:
            r = rng.random()
            if r < 0.65:
                seats = rng.randint(2, 48)
                avail = f"AVL {seats}"
                is_available = True
            elif r < 0.82:
                seats = rng.randint(1, 12)
                avail = f"RAC {seats}"
                is_available = True
            else:
                seats = rng.randint(1, 24)
                avail = f"WL {seats}"
                is_available = False

            classes_data.append({
                "cls": cls_name,
                "fare": fare_map[cls_name],
                "availability": avail,
                "available": is_available,
            })

        # Ensure at least one class on this train is AVL so options exist
        if not any(c["availability"].startswith("AVL") for c in classes_data):
            classes_data[2]["availability"] = f"AVL {rng.randint(5, 20)}"
            classes_data[2]["available"] = True

        trains.append({
            "train_no": t_no,
            "name": t_name,
            "from": orig_code,
            "to": dest_code,
            "date": date_str,
            "departure": departure,
            "arrival": arrival,
            "duration": duration,
            "duration_minutes": train_dur_mins,
            "classes": classes_data,
            "badge": None,
            "badge_reason": None,
        })

    return trains


def rank_and_annotate(trains: List[Dict[str, Any]], budget: float) -> Dict[str, Any]:
    """Annotates each class with budget verdict and ranks top options:

    - 'Best value'
    - 'Fastest'
    - 'Most comfortable'
    with one-line reasons.
    """
    all_options = []
    for t in trains:
        for c in t["classes"]:
            within = c["fare"] <= budget
            c["within_budget"] = within
            c["verdict"] = "within budget" if within else "over budget, needs your approval"
            c["badge"] = None
            c["badge_reason"] = None

            all_options.append({
                "train_no": t["train_no"],
                "train_name": t["name"],
                "cls": c["cls"],
                "fare": c["fare"],
                "availability": c["availability"],
                "available": c["available"],
                "within_budget": within,
                "duration_minutes": t["duration_minutes"],
                "duration": t["duration"],
                "train_ref": t,
                "class_ref": c,
            })

    # 1. Fastest option: lowest duration_minutes, preferring available class
    fastest_train = min(trains, key=lambda tr: tr["duration_minutes"])
    fastest_cls = next(
        (cl for cl in fastest_train["classes"] if cl["available"] and not cl["availability"].startswith("WL") and cl["cls"] in ("3A", "CC", "2A")),
        None,
    )
    if not fastest_cls:
        fastest_cls = next(
            (cl for cl in fastest_train["classes"] if cl["available"] and not cl["availability"].startswith("WL")),
            fastest_train["classes"][0],
        )
    fastest_reason = f"Fastest transit at {fastest_train['duration']} between {fastest_train['from']} and {fastest_train['to']}."

    # 2. Most comfortable: highest class tier with available berth (1A > 2A > 3A > CC > SL)
    comfort_priority = ["1A", "2A", "3A", "CC", "SL"]
    most_comf_opt = None
    for cp in comfort_priority:
        matching = [
            opt for opt in all_options
            if opt["cls"] == cp and opt["available"] and not opt["availability"].startswith("WL")
        ]
        if matching:
            # Pick the fastest/cheapest among highest tier
            most_comf_opt = min(matching, key=lambda o: (o["duration_minutes"], o["fare"]))
            break

    if not most_comf_opt:
        most_comf_opt = min(all_options, key=lambda o: (comfort_priority.index(o["cls"]), o["fare"]))

    comf_cls = most_comf_opt["cls"]
    if comf_cls == "1A":
        comf_reason = "First Class AC (1A) coupe with maximum privacy, wide berths, and bedding."
    elif comf_cls == "2A":
        comf_reason = "Two-tier AC (2A) with generous legroom, curtains, and reading lights."
    else:
        comf_reason = f"Air-conditioned {comf_cls} class travel with reliable onboard comfort."

    # 3. Best value: optimal trade-off of comfort, price within budget, and availability
    def value_score(opt: Dict[str, Any]) -> float:
        tier_weight = {"1A": 38, "2A": 34, "3A": 28, "CC": 24, "SL": 14}.get(opt["cls"], 15)
        avail_weight = 25 if opt["availability"].startswith("AVL") else (10 if opt["availability"].startswith("RAC") else -100)
        budget_weight = 40 if opt["within_budget"] else -25
        economy_weight = max(0.0, 30.0 - (opt["fare"] / max(budget, 800) * 20.0))
        duration_weight = max(0.0, 15.0 - (opt["duration_minutes"] / 60.0))
        return tier_weight + avail_weight + budget_weight + economy_weight + duration_weight

    # Filter candidates: prioritize within_budget and not WL
    viable_value = [o for o in all_options if o["available"] and o["within_budget"]]
    if not viable_value:
        viable_value = [o for o in all_options if o["available"]]
    if not viable_value:
        viable_value = all_options

    # Sort descending by value score
    sorted_value = sorted(viable_value, key=value_score, reverse=True)

    # Avoid picking the exact same (train_no, cls) as Fastest or Most comfortable if alternatives exist
    best_val_opt = sorted_value[0]
    for cand in sorted_value:
        is_same_as_fastest = (cand["train_no"] == fastest_train["train_no"] and cand["cls"] == fastest_cls["cls"])
        is_same_as_comf = (cand["train_no"] == most_comf_opt["train_no"] and cand["cls"] == most_comf_opt["cls"])
        if not is_same_as_fastest and not is_same_as_comf:
            best_val_opt = cand
            break

    best_val_reason = (
        f"Optimal balance of {best_val_opt['cls']} comfort at INR {best_val_opt['fare']} within your budget."
        if best_val_opt["within_budget"]
        else f"Top value {best_val_opt['cls']} option at INR {best_val_opt['fare']} with confirmed booking."
    )

    # Assign badges to class references
    fastest_cls["badge"] = "Fastest"
    fastest_cls["badge_reason"] = fastest_reason
    if not fastest_train["badge"]:
        fastest_train["badge"] = "Fastest"
        fastest_train["badge_reason"] = fastest_reason

    most_comf_opt["class_ref"]["badge"] = "Most comfortable"
    most_comf_opt["class_ref"]["badge_reason"] = comf_reason
    if not most_comf_opt["train_ref"]["badge"]:
        most_comf_opt["train_ref"]["badge"] = "Most comfortable"
        most_comf_opt["train_ref"]["badge_reason"] = comf_reason

    best_val_opt["class_ref"]["badge"] = "Best value"
    best_val_opt["class_ref"]["badge_reason"] = best_val_reason
    if not best_val_opt["train_ref"]["badge"]:
        best_val_opt["train_ref"]["badge"] = "Best value"
        best_val_opt["train_ref"]["badge_reason"] = best_val_reason

    recommendations = {
        "best_value": {
            "train_no": best_val_opt["train_no"],
            "train_name": best_val_opt["train_name"],
            "cls": best_val_opt["cls"],
            "fare": best_val_opt["fare"],
            "reason": best_val_reason,
        },
        "fastest": {
            "train_no": fastest_train["train_no"],
            "train_name": fastest_train["name"],
            "cls": fastest_cls["cls"],
            "fare": fastest_cls["fare"],
            "reason": fastest_reason,
        },
        "most_comfortable": {
            "train_no": most_comf_opt["train_no"],
            "train_name": most_comf_opt["train_name"],
            "cls": most_comf_opt["cls"],
            "fare": most_comf_opt["fare"],
            "reason": comf_reason,
        },
    }

    return {
        "trains": trains,
        "recommendations": recommendations,
    }


def search_journey(origin: str, destination: str, date_str: str, budget: float) -> Dict[str, Any]:
    """Top-level search combining simulator and budget ranker."""
    trains = simulate_trains(origin, destination, date_str)
    ranked = rank_and_annotate(trains, budget)
    return {
        "from": origin.strip().upper(),
        "to": destination.strip().upper(),
        "date": date_str.strip(),
        "budget": float(budget),
        "trains": ranked["trains"],
        "recommendations": ranked["recommendations"],
    }

