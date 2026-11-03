import os
from pathlib import Path
from dotenv import dotenv_values

_local_env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RAILRADAR_API_KEY = os.getenv("RAILRADAR_API_KEY")
HASDATA_API_KEY = os.getenv("HASDATA_API_KEY")
HOTEL_API_KEY = os.getenv("HOTEL_API_KEY")
HOTEL_API_URL = os.getenv("HOTEL_API_URL")
BOOKING_API_URL = os.getenv("BOOKING_API_URL")
BOOKING_API_KEY = os.getenv("BOOKING_API_KEY")
_configured_database_url = (
    os.getenv("TRAVEL_AGENT_DATABASE_URL")
    or os.getenv("LANGGRAPH_DATABASE_URL")
    or _local_env.get("TRAVEL_AGENT_DATABASE_URL")
    or _local_env.get("LANGGRAPH_DATABASE_URL")
)
if not _configured_database_url:
    for _generic_database_url in (
        os.getenv("DATABASE_URL", ""),
        _local_env.get("DATABASE_URL", ""),
    ):
        if _generic_database_url.startswith(("postgresql://", "postgres://")):
            _configured_database_url = _generic_database_url
            break
DATABASE_URL = _configured_database_url
