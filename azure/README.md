# Azure setup (about 20 minutes)

You need two Azure services. Everything else (FastAPI, React) runs on your laptop.

| Service | Why | Replaces in the deck |
|---|---|---|
| **Event Hubs** | the real-time stream of disruption events | Cloud Pub/Sub |
| **Azure SQL Database** | stores members, bookings, decisions; Tableau reads it | BigQuery |

Do the steps one at a time. After each step there is a check so you know it worked.

> Azure CLI commands below are PowerShell-friendly. Prefer clicking? Every step can also be done
> in the Azure portal; the names to use are the same.

## Step 0: Login

```powershell
az login
az account show --query "{name:name, id:id}"   # check it is the subscription with your $100 credits
```

## Step 1: Resource group (one folder that holds everything, so you can delete it in one go)

```powershell
az group create --name waypoint-rg --location centralindia
```

## Step 2: Event Hubs

Namespace names must be globally unique, so add your own suffix.

```powershell
$NS = "waypoint-ns-<yourname>"
az eventhubs namespace create --resource-group waypoint-rg --name $NS --location centralindia --sku Basic
az eventhubs eventhub create --resource-group waypoint-rg --namespace-name $NS --name disruptions --partition-count 2
az eventhubs namespace authorization-rule keys list --resource-group waypoint-rg --namespace-name $NS --name RootManageSharedAccessKey --query primaryConnectionString -o tsv
```

The last command prints a long string starting with `Endpoint=sb://`. Copy it. That goes in
`backend/.env` as `EVENTHUB_CONNECTION_STRING`.

Check: Azure portal > your Event Hubs namespace > Event Hubs > you can see `disruptions`.

## Step 3: Azure SQL

```powershell
$SQL = "waypoint-sql-<yourname>"
az sql server create --resource-group waypoint-rg --name $SQL --location centralindia --admin-user waypointadmin --admin-password "<a-strong-password>"
az sql db create --resource-group waypoint-rg --server $SQL --name waypoint --edition GeneralPurpose --compute-model Serverless --family Gen5 --capacity 1 --auto-pause-delay 60
```

Serverless with auto-pause means you only pay while it is running. The first query after a pause
takes about a minute to wake it up; that is normal.

If you get `RegionDoesNotAllowProvisioning`, student subscriptions sometimes block SQL in some
regions. Use another region for the SQL server only (for example `southeastasia` or `eastus`);
it does not have to match Event Hubs.

Let your laptop in through the firewall (replace with your public IP, search "what is my ip"):

```powershell
az sql server firewall-rule create --resource-group waypoint-rg --server $SQL --name my-laptop --start-ip-address <YOUR_IP> --end-ip-address <YOUR_IP>
```

If your IP changes (new Wi-Fi), run it again with the new IP. Tableau Desktop on the same laptop
is covered by the same rule.

## Step 4: ODBC driver (Windows, once)

The Python backend and Tableau both talk to Azure SQL through a driver. Install
**"ODBC Driver 18 for SQL Server"** from Microsoft's download page.

## Step 5: Fill in `backend/.env`

Copy `backend/.env.example` to `backend/.env` and set:

```
EVENTHUB_CONNECTION_STRING=Endpoint=sb://...   # from step 2
EVENTHUB_NAME=disruptions
DATABASE_URL=mssql+pyodbc://waypointadmin:<password>@<SQL>.database.windows.net:1433/waypoint?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
```

If your password has special characters like `@` or `#`, URL-encode them (`@` becomes `%40`).

## Step 6: Run it

Terminal 1: `cd backend` then `uvicorn app.main:app --reload`
You should see: `Event bus: azure-event-hubs | DB: mssql`

Terminal 2: `cd frontend` then `npm run dev`, open http://localhost:5173

Terminal 3 (optional): `cd backend` then `python simulator.py flight_auto`
This publishes an event straight to Event Hubs from outside the app. It appears in the UI within
a second. That is the real-time path from the deck.

## Step 7: Create the Tableau views

Azure portal > your SQL database > Query editor > paste `tableau/views_azure_sql.sql` > Run.
Then continue with `tableau/TABLEAU_GUIDE.md`.

## Cleaning up

When the hackathon is over, delete everything in one command:

```powershell
az group delete --name waypoint-rg --yes
```

## Keep your credits safe

- Event Hubs Basic and a serverless SQL database cost only a few dollars a month at this size.
- Never commit `backend/.env` to GitHub (the `.gitignore` already blocks it).
- In the Azure portal, Cost Management > Budgets lets you set an alert at, say, $20.
