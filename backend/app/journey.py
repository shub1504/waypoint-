"""Real-time train journey engine, IRCTC fare calculator, and budget ranker for Waypoint."""
from datetime import datetime
import hashlib
import logging
import random
from typing import Any, Dict, List

log = logging.getLogger("waypoint.journey")

CLASSES = ["1A", "2A", "3A", "SL", "CC"]

STATION_NAMES = {
    # Delhi NCR
    "NDLS": "New Delhi (NDLS)",
    "DEL": "Delhi (DEL)",
    "DLI": "Old Delhi Junction (DLI)",
    "NZM": "Hazrat Nizamuddin (NZM)",
    "ANVT": "Anand Vihar Terminus (ANVT)",
    "DEE": "Delhi Sarai Rohilla (DEE)",
    # Mumbai & Maharashtra
    "CSMT": "Mumbai CSMT (CSMT)",
    "BCT": "Mumbai Central (BCT)",
    "MMCT": "Mumbai Central (MMCT)",
    "BDTS": "Bandra Terminus (BDTS)",
    "LTT": "Lokmanya Tilak Terminus (LTT)",
    "DR": "Dadar (DR)",
    "BOM": "Mumbai (BOM)",
    "PUNE": "Pune Junction (PUNE)",
    "NGP": "Nagpur Junction (NGP)",
    "NK": "Nashik Road (NK)",
    "BSL": "Bhusaval Junction (BSL)",
    "KOP": "Kolhapur (KOP)",
    # South India
    "SBC": "KSR Bengaluru (SBC)",
    "YPR": "Yesvantpur Junction (YPR)",
    "SMVB": "SMVT Bengaluru (SMVB)",
    "MAS": "Chennai Central (MAS)",
    "MS": "Chennai Egmore (MS)",
    "TBM": "Tambaram (TBM)",
    "HYB": "Hyderabad Deccan (HYB)",
    "SC": "Secunderabad Junction (SC)",
    "KCG": "Kacheguda (KCG)",
    "ERS": "Ernakulam Junction (ERS)",
    "TVC": "Thiruvananthapuram Central (TVC)",
    "CLT": "Kozhikode Main (CLT)",
    "CBE": "Coimbatore Junction (CBE)",
    "MDU": "Madurai Junction (MDU)",
    "TPJ": "Tiruchchirappalli (TPJ)",
    "MAQ": "Mangaluru Central (MAQ)",
    "MYS": "Mysuru Junction (MYS)",
    "UBL": "Hubballi Junction (UBL)",
    "BZA": "Vijayawada Junction (BZA)",
    "VSKP": "Visakhapatnam (VSKP)",
    # West & Central
    "ADI": "Ahmedabad Junction (ADI)",
    "ST": "Surat (ST)",
    "BRC": "Vadodara Junction (BRC)",
    "RJT": "Rajkot Junction (RJT)",
    "BVC": "Bhavnagar Terminus (BVC)",
    "INDB": "Indore Junction (INDB)",
    "UJN": "Ujjain Junction (UJN)",
    "DWX": "Dewas (DWX)",
    "BPL": "Bhopal Junction (BPL)",
    "RKMP": "Rani Kamlapati / Habibganj (RKMP)",
    "GWL": "Gwalior Junction (GWL)",
    "JBP": "Jabalpur Junction (JBP)",
    "MAO": "Madgaon Junction - Goa (MAO)",
    "KRMI": "Karmali - Goa (KRMI)",
    # North & Rajasthan
    "JP": "Jaipur Junction (JP)",
    "JU": "Jodhpur Junction (JU)",
    "UDZ": "Udaipur City (UDZ)",
    "AII": "Ajmer Junction (AII)",
    "KOTA": "Kota Junction (KOTA)",
    "BKN": "Bikaner Junction (BKN)",
    "AGC": "Agra Cantt (AGC)",
    "AF": "Agra Fort (AF)",
    "MTJ": "Mathura Junction (MTJ)",
    "CNB": "Kanpur Central (CNB)",
    "LKO": "Lucknow Charbagh (LKO)",
    "LJN": "Lucknow Junction (LJN)",
    "BSB": "Varanasi Junction (BSB)",
    "DDU": "Pt. Deen Dayal Upadhyaya (DDU)",
    "PRYJ": "Prayagraj / Allahabad (PRYJ)",
    "GKP": "Gorakhpur Junction (GKP)",
    "CDG": "Chandigarh (CDG)",
    "ASR": "Amritsar Junction (ASR)",
    "LDH": "Ludhiana Junction (LDH)",
    "JUC": "Jalandhar City (JUC)",
    "BTI": "Bathinda Junction (BTI)",
    "UMB": "Ambala Cantt (UMB)",
    "HW": "Haridwar (HW)",
    "DDN": "Dehradun (DDN)",
    "KLK": "Kalka (KLK)",
    "JAT": "Jammu Tawi (JAT)",
    "SVDK": "Shri Mata Vaishno Devi Katra (SVDK)",
    # East & Northeast
    "HWH": "Howrah Junction - Kolkata (HWH)",
    "SDAH": "Sealdah - Kolkata (SDAH)",
    "KOAA": "Kolkata Station (KOAA)",
    "SHM": "Shalimar - Kolkata (SHM)",
    "PNBE": "Patna Junction (PNBE)",
    "DNR": "Danapur (DNR)",
    "GAYA": "Gaya Junction (GAYA)",
    "BBS": "Bhubaneswar (BBS)",
    "PURI": "Puri (PURI)",
    "CTC": "Cuttack (CTC)",
    "TATA": "Tatanagar / Jamshedpur (TATA)",
    "DHN": "Dhanbad Junction (DHN)",
    "ASN": "Asansol Junction (ASN)",
    "GHY": "Guwahati (GHY)",
    "NJP": "New Jalpaiguri (NJP)",
}

AIRPORT_NAMES = {
    # Major Metros & Hubs
    "DEL": "Delhi - Indira Gandhi Intl (DEL)",
    "BOM": "Mumbai - Chhatrapati Shivaji Maharaj Intl (BOM)",
    "BLR": "Bengaluru - Kempegowda Intl (BLR)",
    "HYD": "Hyderabad - Rajiv Gandhi Intl (HYD)",
    "MAA": "Chennai - Chennai Intl (MAA)",
    "CCU": "Kolkata - Netaji Subhash Chandra Bose Intl (CCU)",
    "AMD": "Ahmedabad - Sardar Vallabhbhai Patel Intl (AMD)",
    "PNQ": "Pune - Pune Intl (PNQ)",
    # Leisure & Regional Hubs
    "GOI": "Goa - Dabolim Airport (GOI)",
    "GOX": "Goa - Manohar Intl, Mopa (GOX)",
    "JAI": "Jaipur - Jaipur Intl (JAI)",
    "LKO": "Lucknow - Chaudhary Charan Singh Intl (LKO)",
    "IXC": "Chandigarh - Shaheed Bhagat Singh Intl (IXC)",
    "ATQ": "Amritsar - Sri Guru Ram Dass Jee Intl (ATQ)",
    "SXR": "Srinagar - Sheikh ul-Alam Intl (SXR)",
    "IXL": "Leh - Kushok Bakula Rimpochee (IXL)",
    "IDR": "Indore - Devi Ahilyabai Holkar (IDR)",
    "BHO": "Bhopal - Raja Bhoj Airport (BHO)",
    "VNS": "Varanasi - Lal Bahadur Shastri Intl (VNS)",
    "PAT": "Patna - Jay Prakash Narayan (PAT)",
    "COK": "Kochi - Cochin Intl (COK)",
    "TRV": "Thiruvananthapuram - Trivandrum Intl (TRV)",
    "CCJ": "Kozhikode - Calicut Intl (CCJ)",
    "CNN": "Kannur - Kannur Intl (CNN)",
    "NAG": "Nagpur - Dr. Babasaheb Ambedkar Intl (NAG)",
    "IXB": "Bagdogra / Siliguri (IXB)",
    "GHY": "Guwahati - Lokpriya Gopinath Bordoloi Intl (GHY)",
    "BBI": "Bhubaneswar - Biju Patnaik Intl (BBI)",
    "IXR": "Ranchi - Birsa Munda (IXR)",
    "VTZ": "Visakhapatnam Intl (VTZ)",
    "VGA": "Vijayawada Intl (VGA)",
    "DED": "Dehradun - Jolly Grant (DED)",
    "UDR": "Udaipur - Maharana Pratap (UDR)",
    "JDH": "Jodhpur Airport (JDH)",
    "STV": "Surat Airport (STV)",
    "BDQ": "Vadodara Airport (BDQ)",
    "RPR": "Raipur - Swami Vivekananda (RPR)",
    "IXZ": "Port Blair - Veer Savarkar Intl (IXZ)",
    "AYJ": "Ayodhya - Maharishi Valmiki Intl (AYJ)",
    "GWL": "Gwalior - Rajmata Vijaya Raje Scindia (GWL)",
    "IXA": "Agartala - Maharaja Bir Bikram (IXA)",
    "DMU": "Dimapur Airport (DMU)",
    "IMF": "Imphal - Bir Tikendrajit Intl (IMF)",
    # Popular International from India
    "DXB": "Dubai - Dubai Intl (DXB)",
    "SIN": "Singapore - Changi Airport (SIN)",
    "BKK": "Bangkok - Suvarnabhumi (BKK)",
    "DOH": "Doha - Hamad Intl (DOH)",
    "LHR": "London - Heathrow (LHR)",
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
    "{dest} Tejas Express",
    "{orig} - {dest} Humsafar Express",
    "{dest} Sampark Kranti",
    "{dest} Jan Shatabdi",
    "{dest} Double Decker Express",
    "{dest} Antyodaya Express",
    "{orig} - {dest} Mahamana Express",
    "{dest} Yuva Express",
    "{dest} AC Superfast",
    "{orig} - {dest} Super Deluxe",
    "{dest} Overnight Express",
    "{dest} Premium Special",
]


def _station_title(code: str) -> str:
    cleaned = code.strip().upper()
    return STATION_NAMES.get(cleaned, cleaned)


def _airport_title(code: str) -> str:
    cleaned = code.strip().upper()
    return AIRPORT_NAMES.get(cleaned, cleaned)


def _make_rng(origin: str, destination: str, date_str: str) -> random.Random:
    key = f"{origin.strip().upper()}|{destination.strip().upper()}|{date_str.strip()}".encode("utf-8")
    seed_int = int(hashlib.sha256(key).hexdigest(), 16) % (2**32)
    return random.Random(seed_int)


def simulate_trains(origin: str, destination: str, date_str: str, limit: int | None = None) -> List[Dict[str, Any]]:
    """Deterministic train simulator.

    Given origin, destination, and date, returns trains with:
    train_no, name, departure, arrival, duration, and classes 1A, 2A, 3A, SL, CC.
    Guarantees realistic fare ordering: SL < 3A < 2A < 1A, with CC between SL and 2A.
    """
    orig_code = origin.strip().upper()
    dest_code = destination.strip().upper()
    orig_name = _station_title(orig_code)
    dest_name = _station_title(dest_code)

    rng = _make_rng(orig_code, dest_code, date_str)

    if limit is not None and limit > 0:
        num_trains = min(len(TRAIN_TEMPLATES), max(3, limit))
    else:
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
            "from_name": orig_name,
            "to": dest_code,
            "to_name": dest_name,
            "date": date_str,
            "departure": departure,
            "arrival": arrival,
            "duration": duration,
            "duration_minutes": train_dur_mins,
            "distance_km": round((train_dur_mins / 60.0) * 65.0),
            "running_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
            "live_status": "On schedule",
            "delay_minutes": 0,
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


def calculate_irctc_fares(distance_km: float | None, duration_mins: int | None = None) -> Dict[str, int]:
    """Calculates realistic Indian Railways telescopic passenger fare slabs based on distance.

    Enforces strict hierarchy: SL < CC < 3A < 2A < 1A.
    """
    if distance_km is not None and distance_km > 10:
        d = float(distance_km)
    elif duration_mins is not None and duration_mins > 0:
        d = max(100.0, (duration_mins / 60.0) * 60.0)
    else:
        d = 500.0

    # Telescopic base rates per km
    sl_base = 120.0 + (d * 0.42)
    sl_fare = max(160, int(round(sl_base / 10.0) * 10))

    cc_fare = int(round((sl_fare * 1.65) / 10.0) * 10)
    a3_fare = int(round((sl_fare * 2.30) / 10.0) * 10)
    a2_fare = int(round((sl_fare * 3.30) / 10.0) * 10)
    a1_fare = int(round((sl_fare * 5.10) / 10.0) * 10)

    # Enforce strict hierarchy: SL < CC < 3A < 2A < 1A
    if cc_fare <= sl_fare:
        cc_fare = sl_fare + 150
    if a3_fare <= cc_fare:
        a3_fare = cc_fare + 200
    if a2_fare <= a3_fare:
        a2_fare = a3_fare + 350
    if a1_fare <= a2_fare:
        a1_fare = a2_fare + 600

    return {
        "1A": a1_fare,
        "2A": a2_fare,
        "3A": a3_fare,
        "SL": sl_fare,
        "CC": cc_fare,
    }


def fetch_live_trains(origin: str, destination: str, date_str: str) -> List[Dict[str, Any]]:
    """Fetch live train schedules, running status, timings and distance from RailRadar,
    and attach calibrated IRCTC class fares and availability options."""
    try:
        from app import live_providers
        rr_res = live_providers.search_trains_live(origin, destination, date_str)
        raw_trains = rr_res.get("trains", [])
        if not raw_trains:
            return []

        orig_code = origin.strip().upper()
        dest_code = destination.strip().upper()
        orig_name = _station_title(orig_code)
        dest_name = _station_title(dest_code)

        trains = []
        for t in raw_trains:
            t_no = str(t.get("train_number") or t.get("id") or "").strip()
            if not t_no:
                continue

            t_name = t.get("name") or f"{orig_name} - {dest_name} Express"
            dep_time = t.get("departure_time") or t.get("departure") or "08:00"
            arr_time = t.get("arrival_time") or t.get("arrival") or "18:00"
            dur_str = t.get("duration") or "10h 00m"
            dur_mins = t.get("duration_min") or 600
            dist_km = t.get("distance")
            day_str = t.get("day_str", "")
            running_days = t.get("running_days", [])
            dep_st = t.get("origin") or orig_code
            arr_st = t.get("destination") or dest_code

            # Live delay / status check
            live_status = "On schedule"
            delay_mins = 0
            try:
                today_iso = datetime.now().strftime("%Y-%m-%d")
                if date_str == today_iso:
                    status_res = live_providers.train_live_status(t_no)
                    if status_res and not status_res.get("error"):
                        delay_mins = int(status_res.get("delay_minutes", 0) or 0)
                        if delay_mins > 0:
                            live_status = f"Delayed {delay_mins}m"
                        else:
                            live_status = "On time"
            except Exception:
                pass

            fare_map = calculate_irctc_fares(dist_km, dur_mins)

            # Deterministic seat availability based on train number and date
            rng = _make_rng(orig_code, dest_code, f"{t_no}_{date_str}")
            classes_data = []
            for cls_name in CLASSES:
                r = rng.random()
                if r < 0.65:
                    seats = rng.randint(4, 48)
                    avail = f"AVL {seats}"
                    is_available = True
                elif r < 0.82:
                    seats = rng.randint(1, 10)
                    avail = f"RAC {seats}"
                    is_available = True
                else:
                    seats = rng.randint(1, 18)
                    avail = f"WL {seats}"
                    is_available = False

                classes_data.append({
                    "cls": cls_name,
                    "fare": fare_map[cls_name],
                    "availability": avail,
                    "available": is_available,
                })

            if not any(c["availability"].startswith("AVL") for c in classes_data):
                classes_data[2]["availability"] = f"AVL {rng.randint(6, 24)}"
                classes_data[2]["available"] = True

            trains.append({
                "train_no": t_no,
                "name": t_name,
                "from": dep_st,
                "from_name": _station_title(dep_st),
                "to": arr_st,
                "to_name": _station_title(arr_st),
                "date": date_str,
                "departure": dep_time,
                "arrival": arr_time,
                "day_str": day_str,
                "duration": dur_str,
                "duration_minutes": dur_mins,
                "distance_km": dist_km,
                "running_days": running_days,
                "live_status": live_status,
                "delay_minutes": delay_mins,
                "classes": classes_data,
                "badge": None,
                "badge_reason": None,
                "is_live": True,
                "source": "railradar",
            })

        return trains
    except Exception as exc:
        log.warning("fetch_live_trains error for %s->%s: %s", origin, destination, exc)
        return []


def simulate_flights(origin: str, destination: str, date_str: str, budget: float) -> Dict[str, Any]:
    """Deterministic flight simulator when live HasData API is unavailable or returns 0 flights.
    Provides 6 to 8 realistic flight options across major Indian airlines."""
    orig_code = origin.strip().upper()
    dest_code = destination.strip().upper()
    orig_title = _airport_title(orig_code)
    dest_title = _airport_title(dest_code)

    rng = _make_rng(orig_code, dest_code, f"flight_{date_str}")
    carriers = [
        {"airline": "IndiGo", "prefix": "6E", "base": 4200, "stops": 0, "stops_label": "Nonstop", "dur_min": 125},
        {"airline": "Air India", "prefix": "AI", "base": 5300, "stops": 0, "stops_label": "Nonstop", "dur_min": 130},
        {"airline": "Vistara", "prefix": "UK", "base": 5800, "stops": 0, "stops_label": "Nonstop", "dur_min": 120},
        {"airline": "Akasa Air", "prefix": "QP", "base": 3950, "stops": 0, "stops_label": "Nonstop", "dur_min": 135},
        {"airline": "SpiceJet", "prefix": "SG", "base": 4100, "stops": 0, "stops_label": "Nonstop", "dur_min": 140},
        {"airline": "IndiGo", "prefix": "6E", "base": 3600, "stops": 1, "stops_label": "1 stop", "dur_min": 260},
        {"airline": "Air India", "prefix": "AI", "base": 4800, "stops": 1, "stops_label": "1 stop", "dur_min": 275},
        {"airline": "Vistara", "prefix": "UK", "base": 5100, "stops": 0, "stops_label": "Nonstop", "dur_min": 125},
    ]

    departure_slots = [
        ("06:15", "08:20"),
        ("08:45", "10:55"),
        ("11:30", "13:35"),
        ("14:20", "16:35"),
        ("17:00", "19:15"),
        ("19:40", "23:55"),
        ("20:30", "01:05"),
        ("22:15", "00:20"),
    ]

    flights = []
    for i in range(len(carriers)):
        c = carriers[i]
        fl_no = f"{c['prefix']}-{rng.randint(101, 899)}"
        dep_time, arr_time = departure_slots[i % len(departure_slots)]
        dur_mins = c["dur_min"]
        dur_str = f"{dur_mins // 60}h {dur_mins % 60}m"
        fare = float(c["base"] + rng.randint(-250, 600))
        within = fare <= budget

        flights.append({
            "flight_no": fl_no,
            "name": f"{c['airline']} {fl_no}",
            "airline": c["airline"],
            "from": orig_code,
            "from_name": orig_title,
            "to": dest_code,
            "to_name": dest_title,
            "departure": dep_time,
            "arrival": arr_time,
            "duration": dur_str,
            "duration_minutes": dur_mins,
            "stops": c["stops"],
            "stops_label": c["stops_label"],
            "fare": fare,
            "within_budget": within,
            "verdict": "within budget" if within else "over budget, needs your approval",
            "badge": None,
            "badge_reason": None,
            "is_live": False,
            "source": "simulator",
        })

    fastest = min(flights, key=lambda x: x["duration_minutes"])
    fastest["badge"] = "Fastest"
    fastest["badge_reason"] = f"Fastest flight ({fastest['duration']}) by {fastest['airline']}."

    viable = [fl for fl in flights if fl["within_budget"]] or flights
    best_val = min(viable, key=lambda x: x["fare"])
    if not best_val.get("badge"):
        best_val["badge"] = "Best value"
        best_val["badge_reason"] = f"Lowest airfare at INR {best_val['fare']}."

    recommendations = {
        "fastest": {
            "flight_no": fastest["flight_no"],
            "name": fastest["name"],
            "fare": fastest["fare"],
            "reason": fastest["badge_reason"],
        },
        "best_value": {
            "flight_no": best_val["flight_no"],
            "name": best_val["name"],
            "fare": best_val["fare"],
            "reason": best_val.get("badge_reason") or f"Great value at INR {best_val['fare']}.",
        },
    }

    return {
        "from": orig_code,
        "from_name": orig_title,
        "to": dest_code,
        "to_name": dest_title,
        "date": date_str.strip(),
        "budget": float(budget),
        "mode": "flight",
        "is_live": False,
        "source": "simulator",
        "flights": flights,
        "trains": [],
        "recommendations": recommendations,
    }


def fetch_live_flights(origin: str, destination: str, date_str: str, budget: float) -> Dict[str, Any]:
    """Fetch live flights between cities or airport codes with HasData Google Flights scraper,
    including real airline prices in INR and budget annotations."""
    try:
        from app import live_providers
        f_res = live_providers.search_flights_live(origin, destination, date_str)
        raw_flights = f_res.get("flights", [])

        if not raw_flights:
            return simulate_flights(origin, destination, date_str, budget)

        annotated_flights = []
        for f in raw_flights:
            price = f.get("price_inr") or f.get("price") or 4500.0
            within = float(price) <= budget
            dur_mins = f.get("duration_min") or 120
            annotated_flights.append({
                "flight_no": f.get("flight_number") or f.get("id"),
                "name": f.get("name") or f.get("airline"),
                "airline": f.get("airline"),
                "from": f.get("origin"),
                "from_name": _airport_title(f.get("origin") or origin),
                "to": f.get("destination"),
                "to_name": _airport_title(f.get("destination") or destination),
                "departure": f.get("departure_time") or f.get("departure"),
                "arrival": f.get("arrival_time") or f.get("arrival"),
                "duration": f.get("duration") or "2h 10m",
                "duration_minutes": dur_mins,
                "stops": f.get("stops", 0),
                "stops_label": f.get("stops_label", "Nonstop"),
                "fare": float(price),
                "within_budget": within,
                "verdict": "within budget" if within else "over budget, needs your approval",
                "badge": None,
                "badge_reason": None,
                "is_live": True,
                "source": "hasdata",
            })

        recommendations = {}
        if annotated_flights:
            fastest = min(annotated_flights, key=lambda x: x["duration_minutes"])
            fastest["badge"] = "Fastest"
            fastest["badge_reason"] = f"Fastest flight ({fastest['duration']}) by {fastest['airline']}."
            recommendations["fastest"] = {
                "flight_no": fastest["flight_no"],
                "name": fastest["name"],
                "fare": fastest["fare"],
                "reason": fastest["badge_reason"],
            }

            viable = [fl for fl in annotated_flights if fl["within_budget"]] or annotated_flights
            best_val = min(viable, key=lambda x: x["fare"])
            if not best_val.get("badge"):
                best_val["badge"] = "Best value"
                best_val["badge_reason"] = f"Lowest fare at INR {best_val['fare']}."
            recommendations["best_value"] = {
                "flight_no": best_val["flight_no"],
                "name": best_val["name"],
                "fare": best_val["fare"],
                "reason": best_val.get("badge_reason") or f"Great value at INR {best_val['fare']}.",
            }

        return {
            "from": origin.strip().upper(),
            "from_name": _airport_title(origin),
            "to": destination.strip().upper(),
            "to_name": _airport_title(destination),
            "date": date_str.strip(),
            "budget": float(budget),
            "mode": "flight",
            "is_live": True,
            "source": "hasdata",
            "flights": annotated_flights,
            "trains": [],
            "recommendations": recommendations,
        }
    except Exception as exc:
        log.warning("fetch_live_flights error for %s->%s: %s", origin, destination, exc)
        return simulate_flights(origin, destination, date_str, budget)


def get_trains_for_booking(origin: str, destination: str, date_str: str) -> List[Dict[str, Any]]:
    """Retrieve train options for booking verification on the server.
    Ensures both live RailRadar trains and simulated trains match reliably."""
    sim_trains = simulate_trains(origin, destination, date_str)
    try:
        live_trains = fetch_live_trains(origin, destination, date_str)
        if live_trains:
            live_map = {t["train_no"]: t for t in live_trains}
            merged = list(live_trains)
            for t in sim_trains:
                if t["train_no"] not in live_map:
                    merged.append(t)
            return merged
    except Exception:
        pass
    return sim_trains


def search_journey(origin: str, destination: str, date_str: str, budget: float, mode: str = "train", limit: int | None = None) -> Dict[str, Any]:
    """Top-level journey search.
    Supports real-time RailRadar train schedules and live HasData flights,
    with automatic graceful fallback to the deterministic simulator."""
    clean_orig = origin.strip().upper()
    clean_dest = destination.strip().upper()
    clean_date = date_str.strip()
    num_budget = float(budget)

    if mode == "flight":
        return fetch_live_flights(clean_orig, clean_dest, clean_date, num_budget)

    # 1. Attempt live RailRadar search
    live_trains = fetch_live_trains(clean_orig, clean_dest, clean_date)
    if live_trains and len(live_trains) > 0:
        ranked = rank_and_annotate(live_trains, num_budget)
        return {
            "from": clean_orig,
            "to": clean_dest,
            "from_name": _station_title(clean_orig),
            "to_name": _station_title(clean_dest),
            "date": clean_date,
            "budget": num_budget,
            "mode": "train",
            "is_live": True,
            "source": "railradar",
            "trains": ranked["trains"],
            "recommendations": ranked["recommendations"],
        }

    # 2. Fallback to deterministic simulator
    trains = simulate_trains(clean_orig, clean_dest, clean_date, limit=limit)
    ranked = rank_and_annotate(trains, num_budget)
    return {
        "from": clean_orig,
        "to": clean_dest,
        "from_name": _station_title(clean_orig),
        "to_name": _station_title(clean_dest),
        "date": clean_date,
        "budget": num_budget,
        "mode": "train",
        "is_live": False,
        "source": "simulator",
        "trains": ranked["trains"],
        "recommendations": ranked["recommendations"],
    }


