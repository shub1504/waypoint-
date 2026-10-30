# Tableau guide (first time user)

What Tableau does in Waypoint, matching slide 7: it analyses past bookings to show **where each
member likes to stay**, and it gives the judges a live view of how the agent is behaving.

How "real-time" works here, honestly:
- The **React app is the real-time screen** (events appear in milliseconds through Event Hubs and WebSocket).
- **Tableau reads the same Azure SQL database with a live connection.** It is not pushed new data; it
  re-queries when you refresh (F5 or the refresh button). So it is near real time, one click behind.
  Tableau cannot stream from a message bus; that is a Tableau limitation, not a bug in this project.

## Which Tableau?

- **Tableau Desktop** (free 1 year for students at tableau.com/academic/students): can connect
  live to Azure SQL. Use this.
- **Tableau Public** (free, no signup for the desktop app): cannot connect to Azure SQL. Run
  `python export_csv.py` and connect to the CSV files in `tableau/exports/` instead. Data will be a
  snapshot, so refresh by re-exporting.

## Part A: Connect

1. Open Tableau Desktop > left panel **To a Server** > **Microsoft SQL Server**.
   (If it asks for a driver, install the "Microsoft SQL Server" driver from Tableau's driver page.)
2. Fill in:
   - Server: `<your-sql-server>.database.windows.net`
   - Database: `waypoint`
   - Authentication: **Username and Password**: `waypointadmin` and your password
   - Tick **Require SSL**
3. Click **Sign In**.
4. In the left list you will see the views: `v_decisions`, `v_stay_preferences`, `v_trip_budget`,
   `v_disruption_events`. Drag `v_decisions` into the canvas.
5. Top right: choose **Live** (not Extract).

Check: click **Sheet 1** at the bottom. The left pane lists fields like `status`, `member_name`, `latency_ms`.

If sign-in fails with a firewall error, your IP changed. Re-run the firewall command from `azure/README.md`.

## Part B: Build 5 sheets

Press **Ctrl+M** for a new sheet each time. Rename a sheet by right-clicking its tab.

First, trigger a few scenarios in the React app so there is data.

### Sheet 1: "Decisions by outcome"
Data source `v_decisions`.
1. Drag **status** to **Columns**.
2. Drag **Number of Records** (bottom of the Measures list) to **Rows**.
3. Drag **status** to **Color** as well.

This shows how many were auto-booked vs waiting on the member. Slide 14: "balanced automation".

### Sheet 2: "Time to decision"
1. Drag **latency_ms** to **Text**. Right-click the pill > **Measure** > **Average**.
2. Rename the sheet. This is your big headline number: "average decision time in ms".

### Sheet 3: "Where does Aarav stay?" (the relevance slide)
Switch the data source (top-left Data tab) to `v_stay_preferences`. Add it first via
**Data > New Data Source** if it is not there, then repeat Part A step 1 to 3 and drag this view in.
1. Drag **distance_to_purpose_km** to **Columns** (right-click the pill > **Dimension** so each stay is a dot).
2. Drag **price_per_night** to **Rows**.
3. Drag **hotel_area** to **Color**.
4. Drag **member_name** to **Filters**, choose all, then in the filter right-click > **Show Filter**.
5. Drag **purpose_type** to **Filters** too and show it.

Read it: pick Aarav + temple. The dots cluster at 0.2 to 0.8 km in "Temple Area". That cluster is
the preference the agent copies when it rebooks his hotel. Pick Priya + business and the
cluster moves to BKC. Same logic, learned per member and per trip purpose.

### Sheet 4: "Trip budget vs spend" (budget pool slide)
Use `v_trip_budget`.
1. Drag **trip_title** to **Rows**.
2. Drag **committed_now** to **Columns**.
3. Drag **original_budget** to **Columns** next to it, then in the **Show Me** panel (top right) choose **bullet graph**.
   (If Show Me is greyed out, make sure both are on the shelf as measures.)
4. Drag **pool_credit_available** to **Label**.

The bar shows what is committed; the marker is the original budget.

### Sheet 5: "Overage vs original"
Back on `v_decisions`.
1. Drag **budget_level** to **Columns**.
2. Drag **overage_pct** to **Rows**, then right-click > **Measure** > **Average**.
3. Right-click the axis > **Format** > Numbers > **Percentage**.
4. Drag **kind** to **Color**.

This proves the guardrail: low budget members get tighter overage than high budget members.

## Part C: Put it on a dashboard

1. Click the **new dashboard** icon (bottom, next to the new sheet icon).
2. Set **Size** (left) to **Automatic**.
3. Drag sheets in: put "Time to decision" on top as a tile, "Decisions by outcome" and
   "Overage" in a row, "Where does Aarav stay?" and "Trip budget" below.
4. On "Where does Aarav stay?" click the small arrow in the corner > **Filters** > **Member name**
   to show the filter on the dashboard.
5. Click a bar in "Decisions by outcome". To make it filter the others, click the funnel icon on
   that sheet (**Use as Filter**).

## Part D: Make it feel live during the demo

1. Keep the React app on one screen and Tableau on another.
2. Press the **refresh** button (or F5) in Tableau after each scenario. The numbers change.
3. Optional: publish to **Tableau Cloud** (Server > Tableau Cloud) and open the dashboard
   URL with `?:refresh=yes` on the end to force fresh data on each load. Cloud also needs the Azure
   SQL firewall to allow Tableau Cloud's IPs; for a hackathon demo, Desktop is simpler.

## Common problems

| Problem | Fix |
|---|---|
| Views missing in the list | Run `tableau/views_azure_sql.sql` in the Azure query editor, then reconnect |
| Numbers do not change after a scenario | Press F5 / refresh. Live connections only update on refresh |
| First query is very slow | Serverless SQL was paused; it needs about a minute to wake |
| `overage_pct` shows as a decimal | Format the axis as Percentage (Sheet 5, step 3) |
