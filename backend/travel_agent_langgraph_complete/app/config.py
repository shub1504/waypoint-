import os
from pathlib import Path
from dotenv import dotenv_values

_backend_env = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
_local_env = {**_backend_env, **dotenv_values(Path(__file__).resolve().parents[1] / ".env")}

MODEL_NAME = os.getenv("MODEL_NAME") or os.getenv("GEMINI_MODEL") or _local_env.get("MODEL_NAME") or _local_env.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or _local_env.get("GOOGLE_API_KEY") or _local_env.get("GEMINI_API_KEY")
RAILRADAR_API_KEY = os.getenv("RAILRADAR_API_KEY") or _local_env.get("RAILRADAR_API_KEY") or ""
HASDATA_API_KEY = os.getenv("HASDATA_API_KEY") or _local_env.get("HASDATA_API_KEY") or ""
HOTEL_API_KEY = os.getenv("HOTEL_API_KEY") or _local_env.get("HOTEL_API_KEY") or ""
HOTEL_API_URL = os.getenv("HOTEL_API_URL") or _local_env.get("HOTEL_API_URL") or ""
BOOKING_API_URL = os.getenv("BOOKING_API_URL") or _local_env.get("BOOKING_API_URL") or ""
BOOKING_API_KEY = os.getenv("BOOKING_API_KEY") or _local_env.get("BOOKING_API_KEY") or ""
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
