"""Dump the Tableau-facing tables to CSV (fallback for Tableau Public / offline work).

    python export_csv.py            ->  ../tableau/exports/*.csv

Tableau Public cannot connect live to Azure SQL, so for that edition you load these files instead.
With Tableau Desktop + Azure SQL, skip this and connect to the views directly.
"""
import csv
import pathlib

from sqlalchemy import text

from app.db import engine, init_db

QUERIES = {
    "decisions": """SELECT d.id AS decision_id, d.created_at AS decided_at, d.event_type, d.kind, d.payment_type,
        d.status, m.name AS member_name, m.budget_level, t.title AS trip_title, d.original_amount, d.ceiling,
        d.chosen_amount, d.pool_credit_used, d.latency_ms
        FROM decisions d JOIN members m ON m.id = d.member_id JOIN trips t ON t.id = d.trip_id""",
    "stay_preferences": """SELECT h.member_id, m.name AS member_name, h.purpose_type, h.purpose_place, h.hotel_area,
        h.hotel_name, h.distance_km AS distance_to_purpose_km, h.price_per_night, h.stayed_on
        FROM booking_history h JOIN members m ON m.id = h.member_id""",
    "trip_budget": """SELECT t.id AS trip_id, t.title AS trip_title, m.name AS member_name, m.budget_level,
        t.envelope AS original_budget, t.pool_credit AS pool_credit_available,
        (SELECT COALESCE(SUM(b.amount),0) FROM bookings b WHERE b.trip_id = t.id AND b.status = 'ACTIVE') AS committed_now
        FROM trips t JOIN members m ON m.id = t.member_id""",
}

if __name__ == "__main__":
    init_db()
    out = pathlib.Path(__file__).resolve().parent.parent / "tableau" / "exports"
    out.mkdir(parents=True, exist_ok=True)
    with engine.connect() as c:
        for name, sql in QUERIES.items():
            res = c.execute(text(sql))
            with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(res.keys())
                w.writerows(res.fetchall())
            print("wrote", out / f"{name}.csv")
