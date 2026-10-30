"""All settings come from environment variables (or a .env file).

Nothing here is required to run locally: with no .env the app uses SQLite and an
in-process event queue. Add the Azure values below to switch to the cloud services.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# --- Database -------------------------------------------------------------
# Local default: SQLite file. For Azure SQL use (see azure/README.md):
#   mssql+pyodbc://USER:PASSWORD@SERVER.database.windows.net:1433/waypoint
#   ?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./waypoint.db"

# --- Azure Event Hubs (real-time bus) ------------------------------------
EVENTHUB_CONNECTION_STRING = os.getenv("EVENTHUB_CONNECTION_STRING", "")
EVENTHUB_NAME = os.getenv("EVENTHUB_NAME") or "disruptions"
EVENTHUB_CONSUMER_GROUP = os.getenv("EVENTHUB_CONSUMER_GROUP", "$Default")
USE_EVENTHUB = bool(EVENTHUB_CONNECTION_STRING)

# --- Optional LLM (only used to phrase the notification text) -------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# --- CORS (React dev server) ---------------------------------------------
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# --- PayPal (Sandbox only) -----------------------------------------------
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_BASE_URL = os.getenv("PAYPAL_BASE_URL") or "https://api-m.sandbox.paypal.com"
DEMO_INR_PER_USD = float(os.getenv("DEMO_INR_PER_USD") or 85)  # demo exchange rate only
USE_PAYPAL = bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)

# Safety: this project must never talk to the live PayPal API.
if "sandbox" not in PAYPAL_BASE_URL:
    raise RuntimeError("PAYPAL_BASE_URL must be the sandbox URL")