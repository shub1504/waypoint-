"""Unit tests for live_providers (RailRadar & HasData).
All HTTP calls are mocked. No real network calls are made.
"""
from unittest.mock import MagicMock, patch
import pytest
import httpx

from app import config, live_providers


@pytest.fixture(autouse=True)
def clean_state():
    live_providers.clear_cache()
    yield
    live_providers.clear_cache()


def test_station_code_resolution():
    assert live_providers.resolve_station_code("Delhi") == "NDLS"
    assert live_providers.resolve_station_code("dilli") == "NDLS"
    assert live_providers.resolve_station_code("New Delhi") == "NDLS"
    assert live_providers.resolve_station_code("NDLS") == "NDLS"
    assert live_providers.resolve_station_code("Mumbai") == "CSMT"
    assert live_providers.resolve_station_code("bombay") == "CSMT"
    assert live_providers.resolve_station_code("Indore") == "INDB"
    assert live_providers.resolve_station_code("Ujjain") == "UJN"
    assert live_providers.resolve_station_code("Jaipur") == "JP"
    assert live_providers.resolve_station_code("Bhopal") == "BPL"
    assert live_providers.resolve_station_code("Goa") == "MAO"
    # Fuzzy match typo
    assert live_providers.resolve_station_code("delhii") == "NDLS"
    assert live_providers.resolve_station_code("indor") == "INDB"

    # Regional and state resolution
    assert "LDH" in live_providers.resolve_station_codes("Punjab")
    assert "ASR" in live_providers.resolve_station_codes("Punjab")
    assert live_providers.resolve_station_code("Ludhiana") == "LDH"
    assert live_providers.resolve_station_code("ludhiana junction") == "LDH"
    assert live_providers.resolve_station_code("Amritsar") == "ASR"
    assert "ERS" in live_providers.resolve_station_codes("Kerala")
    assert "JP" in live_providers.resolve_station_codes("Rajasthan")


def test_airport_code_resolution():
    assert live_providers.resolve_airport_code("Delhi") == "DEL"
    assert live_providers.resolve_airport_code("DEL") == "DEL"
    assert live_providers.resolve_airport_code("Mumbai") == "BOM"
    assert live_providers.resolve_airport_code("bombay") == "BOM"
    assert live_providers.resolve_airport_code("mubmai") == "BOM"  # typo
    assert live_providers.resolve_airport_code("Indore") == "IDR"
    assert live_providers.resolve_airport_code("Jaipur") == "JAI"
    assert live_providers.resolve_airport_code("Bhopal") == "BHO"
    assert live_providers.resolve_airport_code("Goa") == "GOI"


def test_real_railradar_response_shape():
    """Verify parsing against the exact real RailRadar /v1/trains/between envelope:
    - nested item['from']['departure'] and item['to']['arrival']
    - day progression (day 2 to day 3 -> '+1 day')
    - integer duration in minutes (1585 -> '26h 25m')
    - float distance labeled with 'km' (1544.2 -> '1544 km')
    - departure/arrival stations mentioned in clean line
    """
    raw_railradar_envelope = {
        "success": True,
        "data": {
            "from": "NDLS",
            "to": "CSMT",
            "trains": [
                {
                    "train": {
                        "number": "12138",
                        "name": "Punjab Mail",
                        "origin": "FZR",
                        "destination": "CSMT",
                    },
                    "from": {
                        "code": "NDLS",
                        "name": "New Delhi",
                        "departure": "05:10",
                        "day": 2,
                    },
                    "to": {
                        "code": "CSMT",
                        "name": "Chhatrapati Shivaji Maharaj Terminus",
                        "arrival": "07:35",
                        "day": 3,
                    },
                    "duration": 1585,
                    "distance": 1544.2,
                    "running_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
                    "classes": ["1A", "2A", "3A", "SL"],
                }
            ],
        },
        "meta": {"timestamp": "2026-11-10T22:00:00Z"},
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = raw_railradar_envelope

    with patch.object(config, "RAILRADAR_API_KEY", "test-key"):
        with patch.object(live_providers, "_http_get_with_retry", return_value=mock_resp):
            res = live_providers.search_trains_live("NDLS", "CSMT", "2026-11-11")
            assert res["source"] == "railradar"
            assert res["total_found"] == 1
            train = res["trains"][0]

            assert train["train_number"] == "12138"
            assert train["name"] == "Punjab Mail"
            assert train["departure_time"] == "05:10"
            assert train["arrival_time"] == "07:35"
            assert train["day_str"] == " (+1 day)"
            assert train["duration"] == "26h 25m"
            assert train["distance_label"] == "1544 km"
            assert train["origin"] == "NDLS"
            assert train["destination"] == "CSMT"

            # Check clean line per train format
            assert "Punjab Mail (12138): departs 05:10 from NDLS, arrives 07:35 (+1 day) at CSMT, 26h 25m (1544 km)" == train["summary_line"]
            # No fabricated price or seats
            assert train["price"] is None
            assert train["price_known"] is False
            assert train["seats"] is None


def test_search_trains_live_parsing():
    sample_envelope = {
        "success": True,
        "data": {
            "from": "NDLS",
            "to": "INDB",
            "count": 1,
            "trains": [
                {
                    "train": {
                        "number": "12415",
                        "name": "Intercity Express",
                    },
                    "departure_time": "06:00",
                    "arrival_time": "20:00",
                    "duration": "14h 00m",
                    "running_days": ["MON", "TUE", "WED"],
                    "classes": ["3A", "2A", "SL"],
                }
            ],
        },
        "meta": {"timestamp": "2026-11-10T22:00:00Z"},
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_envelope

    with patch.object(config, "RAILRADAR_API_KEY", "test-key"):
        with patch.object(live_providers, "_http_get_with_retry", return_value=mock_resp) as mock_get:
            res = live_providers.search_trains_live("NDLS", "INDB", "2026-11-11")

            assert res["source"] == "railradar"
            assert res["total_found"] == 1
            train = res["trains"][0]
            assert train["train_number"] == "12415"
            assert "Intercity Express" in train["name"]
            assert train["departure_time"] == "06:00"
            assert train["arrival_time"] == "20:00"
            # RailRadar does not have fares or seats: never invented
            assert train["price"] is None
            assert train["price_known"] is False
            assert "IRCTC" in train["fare_note"]

            # Second call should use cache and not hit _http_get_with_retry again
            cached_res = live_providers.search_trains_live("NDLS", "INDB", "2026-11-11")
            assert cached_res["total_found"] == 1
            assert mock_get.call_count == 1


def test_multi_station_city_resolution():
    """Verify that multi-station cities return all major station codes."""
    mumbai_codes = live_providers.resolve_station_codes("Mumbai")
    assert "CSMT" in mumbai_codes
    assert "BCT" in mumbai_codes or "MMCT" in mumbai_codes
    assert "DR" in mumbai_codes
    assert "LTT" in mumbai_codes
    assert "BDTS" in mumbai_codes

    delhi_codes = live_providers.resolve_station_codes("Delhi")
    assert "NDLS" in delhi_codes
    assert "DLI" in delhi_codes
    assert "NZM" in delhi_codes
    assert "ANVT" in delhi_codes

    # Specific station request returns ONLY that station
    assert live_providers.resolve_station_codes("BDTS") == ["BDTS"]
    assert live_providers.resolve_station_codes("Nizamuddin") == ["NZM"]


def test_search_trains_live_no_key():
    with patch.object(config, "RAILRADAR_API_KEY", ""):
        res = live_providers.search_trains_live("NDLS", "INDB")
        assert res["source"] == "railradar"
        assert res["trains"] == []
        assert "not configured" in res["error"]


def test_search_trains_live_api_error():
    with patch.object(config, "RAILRADAR_API_KEY", "test-key"):
        with patch.object(live_providers, "_http_get_with_retry", side_effect=httpx.ConnectTimeout("timeout")):
            res = live_providers.search_trains_live("NDLS", "INDB")
            assert res["source"] == "railradar"
            assert res["trains"] == []
            assert "Failed to connect" in res["error"]


def test_train_live_status_parsing():
    sample_live = {
        "success": True,
        "data": {
            "train_number": "12919",
            "train_name": "Malwa Express",
            "delay": 25,
            "current_station_name": "Mathura Jn",
            "eta": "14:30",
        },
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_live

    with patch.object(config, "RAILRADAR_API_KEY", "test-key"):
        with patch.object(live_providers, "_http_get_with_retry", return_value=mock_resp):
            res = live_providers.train_live_status("12919")
            assert res["source"] == "railradar"
            assert res["train_number"] == "12919"
            assert res["delay_min"] == 25
            assert "Late by 25 min" in res["status"]
            assert res["current_station"] == "Mathura Jn"


def test_search_flights_live_parsing():
    sample_flights = {
        "bestFlights": [
            {
                "price": 4900,
                "totalDuration": 115,
                "flights": [
                    {
                        "airline": "IndiGo",
                        "flightNumber": "6E-512",
                        "departureAirport": {"id": "DEL", "time": "2026-11-11 10:00"},
                        "arrivalAirport": {"id": "IDR", "time": "2026-11-11 11:55"},
                        "duration": 115,
                    }
                ],
                "layovers": [],
            }
        ],
        "otherFlights": [],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_flights

    with patch.object(config, "HASDATA_API_KEY", "hasdata-key"):
        with patch.object(live_providers, "_http_get_with_retry", return_value=mock_resp) as mock_get:
            res = live_providers.search_flights_live("DEL", "IDR", "2026-11-11")
            assert res["source"] == "hasdata"
            assert res["total_found"] == 1
            flight = res["flights"][0]
            assert flight["flight_number"] == "6E-512"
            assert flight["airline"] == "IndiGo"
            assert flight["stops"] == 0
            assert flight["stops_label"] == "Nonstop"
            assert flight["price"] == 4900.0
            assert flight["price_known"] is True

            # Cache test
            res2 = live_providers.search_flights_live("DEL", "IDR", "2026-11-11")
            assert res2["total_found"] == 1
            assert mock_get.call_count == 1


def test_extract_travel_entities_hinglish_and_typos():
    """Verify free-form Hinglish, instrumental 'train se', and typos extract accurately."""
    # 1. 'mujhe kal train se delhi se lucknow jana hai'
    ent1 = live_providers.extract_travel_entities("mujhe kal train se delhi se lucknow jana hai")
    assert ent1["mode"] == "train"
    assert ent1["origin"].lower() == "delhi"
    assert ent1["destination"].lower() == "lucknow"
    assert ent1["date"] != ""

    # 2. 'delhi se indore train kal'
    ent2 = live_providers.extract_travel_entities("delhi se indore train kal")
    assert ent2["mode"] == "train"
    assert ent2["origin"].lower() == "delhi"
    assert ent2["destination"].lower() == "indore"

    # 3. 'delhi to mubmai flihgt'
    ent3 = live_providers.extract_travel_entities("delhi to mubmai flihgt")
    assert ent3["mode"] == "flight"
    assert ent3["origin"].lower() == "delhi"
    assert "mubmai" in ent3["destination"].lower()
    assert live_providers.resolve_airport_code(ent3["destination"]) == "BOM"

    # 4. 'cheapest flight DEL to BOM friday'
    ent4 = live_providers.extract_travel_entities("cheapest flight DEL to BOM friday")
    assert ent4["mode"] == "flight"
    assert ent4["origin"].upper() == "DEL"
    assert ent4["destination"].upper() == "BOM"
