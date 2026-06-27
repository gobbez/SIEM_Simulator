# SIEM Insights Dashboard

A simple SIEM-style dashboard (similar to Sumo Logic) built with a Python Flask
backend and a vanilla HTML/CSS/JS frontend. It loads the
[`darkknight25/Advanced_SIEM_Dataset`](https://huggingface.co/datasets/darkknight25/Advanced_SIEM_Dataset)
dataset from Hugging Face and exposes insights, KPIs and a filterable event list.

## Structure

```
.
├── app.py                 # Flask backend
├── requirements.txt       # Python dependencies
├── static/
│   ├── index.html         # Dashboard UI
│   ├── style.css          # Dark SIEM theme
│   └── app.js             # Frontend logic and Chart.js visualisations
├── wsgi.py                # PythonAnywhere WSGI entry point
└── README.md
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

The first start downloads the dataset from Hugging Face (≈ a few seconds); the
data is then held in memory and all filters/charts are served from there.

## Features

- KPI cards: total events, critical/high counts, anomalies, unique users,
  unique source IPs and average risk score.
- Interactive charts: severity, event type, sources, users, actions, geo
  location, risk score distribution, events over time and anomaly timeline.
- Filterable event table with pagination and free-text search.
- Event detail modal with full raw log and metadata.

## API endpoints

- `GET /api/health` – dataset status and row count.
- `GET /api/filters` – distinct values for filter dropdowns.
- `GET /api/insights?...` – aggregated KPIs and chart data.
- `GET /api/events?...` – paginated event list.
- `GET /api/events/<event_id>` – single event details.

Query parameters accepted by `/api/insights` and `/api/events`:
`q`, `severity`, `event_type`, `source`, `user`, `alert_type`, `src_ip`,
`dst_ip`, `geo_location`, `anomaly`, `from`, `to`.

## Deploy on PythonAnywhere (step-by-step)

These instructions assume you already cloned the repository, e.g. in
`/home/yourusername/SIEM_Simulator`. Replace `yourusername` and the folder name
with your actual PythonAnywhere values.

### 1. Open a Bash console on PythonAnywhere

Go to **Consoles → Bash**.

### 2. Move into the project folder and create the virtual environment

```bash
cd ~/SIEM_Simulator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Cache the Hugging Face dataset

**Important for free accounts:** PythonAnywhere free tier restricts outgoing
requests. `load_dataset(...)` will fail if it has to download from Hugging Face.
You have two options.

**Option A – try downloading directly on PythonAnywhere** (often works on paid
accounts, sometimes on free ones):

```bash
source venv/bin/activate
python -c "from datasets import load_dataset; load_dataset('darkknight25/Advanced_SIEM_Dataset')"
```

If the command above succeeds, you are done with this step.

**Option B – upload the cache from your local machine** (recommended for free
accounts):

1. On your local machine, download the dataset once:
   ```bash
   python -c "from datasets import load_dataset; load_dataset('darkknight25/Advanced_SIEM_Dataset')"
   ```
2. Find your Hugging Face cache directory:
   - Linux/macOS: `~/.cache/huggingface/datasets/`
   - Windows: `%USERPROFILE%\.cache\huggingface\datasets\`
3. Upload the entire `datasets` folder to PythonAnywhere under
   `/home/yourusername/.cache/huggingface/datasets/` (use the Files tab or
   `scp`/`rsync`).

### 4. Configure `wsgi.py`

Edit `/home/yourusername/SIEM_Simulator/wsgi.py` on PythonAnywhere and replace:

```python
PROJECT_PATH = '/home/yourusername/SIEM_Simulator'
```

with your real path, for example:

```python
PROJECT_PATH = '/home/gobbez/SIEM_Simulator'
```

### 5. Create / reconfigure the Web app

1. Go to the **Web** tab on PythonAnywhere.
2. Click **Add a new web app** (or open your existing app).
3. Choose **Manual configuration** and select **Python 3.10** (or newer).
4. Fill in the form:
   - **Source code directory:** `/home/yourusername/SIEM_Simulator`
   - **Working directory:** `/home/yourusername/SIEM_Simulator`
   - **WSGI configuration file:** click the link and paste the contents of
     `/home/yourusername/SIEM_Simulator/wsgi.py`, or point it to that file.
   - **Virtualenv path:** `/home/yourusername/SIEM_Simulator/venv`

### 6. Add the static files mapping

Still in the **Web** tab, under **Static files**, add:

- **URL:** `/static/`
- **Directory:** `/home/yourusername/SIEM_Simulator/static`

This lets PythonAnywhere serve CSS/JS directly instead of going through Flask.

### 7. Reload and test

Click the **Reload** button for your web app and visit your PythonAnywhere
domain (e.g. `https://yourusername.pythonanywhere.com`).

You should see the dashboard. The first request may take 10–30 seconds while the
dataset is loaded into memory.

### Troubleshooting

- **500 Internal Server Error:** open the **Error log** in the Web tab; the most
  common cause is a missing dataset cache or a wrong path in `wsgi.py`.
- **Dataset not found / timeout:** the Hugging Face cache is missing or in the
  wrong location. Re-run step 3.
- **Static files missing (no CSS/JS):** double-check step 6 and reload the app.
- **Memory errors:** the free tier handles 100k rows, but if you run multiple
  reloads in a row, wait a moment for the old worker to be killed.

