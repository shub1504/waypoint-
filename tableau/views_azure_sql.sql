-- Run this ONCE in the Azure SQL query editor (Azure portal > your database > Query editor)
-- after the backend has started at least once (the backend creates the tables).
-- These views are what Tableau connects to: one flat, analysis-ready table per question.

-- 1) Every agent decision, with member and trip context ---------------------------------
CREATE OR ALTER VIEW dbo.v_decisions AS
SELECT
    d.id                                   AS decision_id,
    d.created_at                           AS decided_at,
    d.event_type,
    d.kind,
    d.payment_type,
    d.status,
    CASE WHEN d.status = 'AUTO_BOOKED' THEN 1 ELSE 0 END           AS is_auto_booked,
    CASE WHEN d.status IN ('NEEDS_APPROVAL','FALLBACK_OPTIONS') THEN 1 ELSE 0 END AS is_waiting_on_member,
    m.name                                 AS member_name,
    m.budget_level,
    m.alert_channel,
    t.title                                AS trip_title,
    t.purpose_type,
    d.original_amount,
    d.ceiling,
    d.chosen_amount,
    d.pool_credit_used,
    CASE WHEN d.chosen_amount IS NULL OR d.original_amount = 0 THEN NULL
         ELSE (d.chosen_amount - d.original_amount) / d.original_amount END AS overage_pct,
    CASE WHEN d.chosen_amount IS NULL THEN NULL
         WHEN d.chosen_amount <= d.ceiling THEN 1 ELSE 0 END       AS within_ceiling,
    d.latency_ms
FROM dbo.decisions d
JOIN dbo.members m ON m.id = d.member_id
JOIN dbo.trips   t ON t.id = d.trip_id;
GO

-- 2) Where each member likes to stay (slide 7: relevance-aware rebooking) ---------------
CREATE OR ALTER VIEW dbo.v_stay_preferences AS
SELECT
    h.member_id,
    m.name            AS member_name,
    h.purpose_type,
    h.purpose_place,
    h.hotel_area,
    h.hotel_name,
    h.distance_km     AS distance_to_purpose_km,
    h.price_per_night,
    h.stayed_on
FROM dbo.booking_history h
JOIN dbo.members m ON m.id = h.member_id;
GO

-- 3) Trip budget envelope vs what is currently committed (slide 6: budget pool) ---------
CREATE OR ALTER VIEW dbo.v_trip_budget AS
SELECT
    t.id            AS trip_id,
    t.title         AS trip_title,
    m.name          AS member_name,
    m.budget_level,
    t.envelope      AS original_budget,
    ISNULL(SUM(CASE WHEN b.status = 'ACTIVE' THEN b.amount END), 0) AS committed_now,
    t.pool_credit   AS pool_credit_available
FROM dbo.trips t
JOIN dbo.members m ON m.id = t.member_id
LEFT JOIN dbo.bookings b ON b.trip_id = t.id
GROUP BY t.id, t.title, m.name, m.budget_level, t.envelope, t.pool_credit;
GO

-- 4) Raw disruption stream (for the "events over time" chart) ---------------------------
CREATE OR ALTER VIEW dbo.v_disruption_events AS
SELECT event_id, type AS event_type, member_id, trip_id, booking_id,
       delay_hours, demand_spike, detected_at, received_at
FROM dbo.disruption_events;
GO
