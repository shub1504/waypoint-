import pytest
from unittest.mock import MagicMock
import httpx
from app import config


@pytest.fixture(autouse=True)
def offline_tests(monkeypatch):
    """Ensure all tests run purely offline without making external LLM or API network calls."""
    # Ensure offline LLM routing and notifications
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "")

    try:
        from app import notify
        monkeypatch.setattr(notify, "compose", notify._template)
    except ImportError:
        pass

    try:
        from app import live_providers

        def _mock_http_get(url, *args, **kwargs):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            u = str(url).lower()
            if "live" in u:
                resp.json.return_value = {
                    "success": True,
                    "data": {
                        "train_number": "12919",
                        "train_name": "Malwa Express",
                        "delay": 15,
                        "current_station_name": "Mathura Jn",
                        "eta": "14:30",
                    },
                }
            elif "hasdata" in u:
                resp.json.return_value = {
                    "bestFlights": [
                        {
                            "price": 4500,
                            "totalDuration": 120,
                            "flights": [
                                {
                                    "airline": "IndiGo",
                                    "flightNumber": "6E-101",
                                    "departureAirport": {"id": "BOM", "time": "08:00"},
                                    "arrivalAirport": {"id": "DEL", "time": "10:00"},
                                    "duration": 120,
                                }
                            ],
                            "layovers": [],
                        }
                    ],
                    "otherFlights": [],
                }
            else:
                resp.json.return_value = {
                    "success": True,
                    "data": {
                        "trains": [
                            {
                                "train": {"number": "12415", "name": "Intercity Express"},
                                "from": {"code": "NDLS", "departure": "06:00", "day": 1},
                                "to": {"code": "INDB", "arrival": "20:00", "day": 1},
                                "duration": 840,
                                "distance": 820.0,
                                "runDays": ["MON", "TUE", "WED"],
                            }
                        ]
                    },
                }
            return resp

        monkeypatch.setattr(live_providers, "_http_get_with_retry", _mock_http_get)
    except ImportError:
        pass
