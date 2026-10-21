<<<<<<< HEAD
# Waypoint: Autonomous Travel Disruption Concierge (prototype)

A cancelled flight or train arrives as a live event. The agent finds alternatives, checks them
against spend guardrails and the member's purpose for travelling, then rebooks on its own, asks
for approval, or offers fallback choices. The React screen updates in real time.

```
Simulator / UI button
        │ publish
        ▼
Azure Event Hubs  ──consume──►  FastAPI agent  ──►  Azure SQL  ◄── Tableau (live connection)
 (real-time bus)                 │  guardrail
                                 │  budget pool        ──WebSocket──►  React live dashboard
                                 │  relevance
                                 └─ fallback
```

| Deck slide | Where it lives |
|---|---|
| Spend Guardrail Engine | `backend/app/guardrail.py` |
| Trip Budget Pool | `guardrail.py` + `_release_hotel_night` in `agent.py` |
| Relevance-Aware Rebooking | `backend/app/relevance.py`, visualised in Tableau |
| No-Availability Fallback | `_fallback_options` in `agent.py` |
| User onboarding data (budget level, channel, consents) | `members` table in `models.py` |

The agent's decision is plain, tested code. Gemini (optional) only rewords the notification, so
a model error can never overspend a member's money.

## Run it offline first (no Azure needed)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000/api/health

cd ../frontend                          # second terminal
npm install
npm run dev                             # http://localhost:5173
```

Click the scenario buttons. You should see `bus: local  db: sqlite` in the header.
Run the tests any time: `cd backend && python -m pytest -q`

## Then switch on Azure

Follow `azure/README.md`, then `tableau/TABLEAU_GUIDE.md`. Nothing in the code changes; the
`.env` file decides whether it uses the local queue/SQLite or Event Hubs/Azure SQL.

## Demo order that tells the story

1. **Flight cancelled → auto-rebooked**: ₹4,200 original, rebooked at ₹4,900 under a ₹6,720 limit.
2. **Every option above the ceiling**: Rohan (low budget). Agent refuses to auto-book, asks him.
3. **Long delay → budget pool**: a freed hotel night lets the flight go above the normal ceiling.
4. **Hotel overbooked**: picks the stay near the temple, not the cheapest one 4.5 km away.
5. **Train sold out**: offers a bus or a nearby station, including the extra cab cost.
6. Show Tableau: stay preferences cluster, decisions by outcome, trip budgets.

Press **Reset demo data** between runs.

## What is mocked

Flight, train and hotel inventory is a mock dataset (`backend/app/inventory.py`), since free real
flight APIs were not usable. `search_transport` and `search_hotels` are the only two functions to
replace when you get a real supplier API.
=======
# waypoint-
>>>>>>> ba050380bcd2a8138678ab6056d2ca1d18fcff05
