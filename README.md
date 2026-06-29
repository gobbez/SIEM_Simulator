# SIEM Insights Dashboard

A SIEM-style dashboard (similar to Sumo Logic) built with a Python Flask backend
and a vanilla HTML/CSS/JS frontend. It loads the
[`darkknight25/Advanced_SIEM_Dataset`](https://huggingface.co/datasets/darkknight25/Advanced_SIEM_Dataset)
dataset (100k security log events) and exposes insights, KPIs and a filterable
event list.

## Structure

```
.
├── app.py                 # Flask backend (only dependency: Flask)
├── convert_dataset.py     # One-time local script: generates dataset.db
├── requirements.txt       # Runtime dependencies (Flask only)
├── static/
│   ├── index.html         # Dashboard UI
│   ├── style.css          # Dark SIEM theme
│   └── app.js             # Frontend logic and Chart.js charts
├── wsgi.py                # PythonAnywhere WSGI entry point
└── README.md
```

## How it works

The backend reads from a local **SQLite** file (`dataset.db`). SQLite is part of
the Python standard library — no extra packages are needed at runtime. This keeps
the PythonAnywhere deployment well under the 500 MB free-tier disk limit.

`convert_dataset.py` is a **local-only** utility that you run once on your own
machine to produce `dataset.db`. You then upload that file to PythonAnywhere.

## Local development

### 1. Install runtime dependencies

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

`requirements.txt` contains only `flask`.

### 2. Generate the dataset (one-time)

You need `pyarrow` locally for the conversion. If you already have
`dataset.parquet` from a previous run:

```bash
pip install pyarrow
python convert_dataset.py
```

If you need to download the dataset fresh from Hugging Face:

```bash
pip install pyarrow requests
python convert_dataset.py --download
```

This produces `dataset.db` (~80–150 MB). The script also accepts an existing
`dataset.parquet` and converts it without downloading again.

### 3. Run

```bash
python app.py
```

Open `http://localhost:5000`.

## Features

- KPI cards: total events, critical/high counts, anomalies, unique users,
  source IPs and average risk score.
- Interactive charts: severity, event type, sources, top users, top actions,
  geo location, risk score distribution, events over time, anomaly timeline.
- Filterable event table with pagination and free-text search.
- Event detail modal with full raw log and metadata.

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Dataset status and row count |
| `GET /api/filters` | Distinct values for filter dropdowns |
| `GET /api/insights?...` | Aggregated KPIs and chart data |
| `GET /api/events?...` | Paginated event list |
| `GET /api/events/<event_id>` | Single event detail |

Query parameters accepted by `/api/insights` and `/api/events`:
`q`, `severity`, `event_type`, `source`, `user`, `alert_type`, `src_ip`,
`dst_ip`, `geo_location`, `anomaly`, `from`, `to`, `sort`, `order`,
`page`, `per_page`.

## Deploy on PythonAnywhere (free tier)

### Disk usage at a glance

| Component | Size |
|---|---|
| Flask + dependencies | ~15 MB |
| `dataset.db` | ~80–150 MB |
| Source files + static | ~1 MB |
| **Total** | **~100–170 MB** (well under the 500 MB limit) |

### Step 1 — Generate `dataset.db` locally

```bash
pip install pyarrow requests   # one-time, on your machine only
python convert_dataset.py --download   # omit --download if you have dataset.parquet
```

### Step 2 — Upload to PythonAnywhere

Upload the following files to `/home/yourusername/SIEM_Simulator/`:

```
app.py
wsgi.py
requirements.txt
dataset.db          ← the generated SQLite file
static/
```

> Do **not** upload `venv/`, `dataset.parquet`, or `convert_dataset.py`.

Use the **Files** tab, `scp`, or `rsync`. For large files (dataset.db),
`scp` is fastest:

```bash
scp dataset.db yourusername@ssh.pythonanywhere.com:~/SIEM_Simulator/
```

### Step 3 — Create the virtual environment on PythonAnywhere

Open a **Bash console**:

```bash
cd ~/SIEM_Simulator
python3 -m venv venv
source venv/bin/activate
pip install --no-cache-dir -r requirements.txt
```

This installs only Flask (~15 MB total).

### Step 4 — Configure `wsgi.py`

Edit `wsgi.py` and set `PROJECT_PATH` to your actual path:

```python
PROJECT_PATH = '/home/yourusername/SIEM_Simulator'
```

### Step 5 — Create / configure the Web app

1. Go to the **Web** tab → **Add a new web app**.
2. Choose **Manual configuration** → **Python 3.10** (or newer).
3. Fill in:
   - **Source code:** `/home/yourusername/SIEM_Simulator`
   - **Working directory:** `/home/yourusername/SIEM_Simulator`
   - **WSGI configuration file:** paste the contents of `wsgi.py`
   - **Virtualenv path:** `/home/yourusername/SIEM_Simulator/venv`

### Step 6 — Add the static files mapping

In the **Web** tab → **Static files**:

| URL | Directory |
|---|---|
| `/static/` | `/home/yourusername/SIEM_Simulator/static` |

### Step 7 — Reload and test

Click **Reload** and open `https://yourusername.pythonanywhere.com`.

The first request is instant — SQLite queries on 100k rows are fast.

### Troubleshooting

| Symptom | Fix |
|---|---|
| 500 error on first load | Check **Error log** in Web tab; most likely `dataset.db` is missing or `wsgi.py` has the wrong path. |
| Disk quota exceeded during `pip install` | Run `rm -rf ~/SIEM_Simulator/venv` then reinstall. |
| `dataset.db` not found | Confirm the file is in the project root next to `app.py`. |
| No CSS/JS | Double-check the static files mapping in Step 6 and reload. |
