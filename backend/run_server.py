"""Start Waypoint with environment variables and Windows-compatible async event loop."""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env before starting Uvicorn or its reload process.
ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_FILE, override=True)

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
