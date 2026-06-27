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

## Deploy on PythonAnywhere

Yes, the app can run on PythonAnywhere. Steps:

1. **Upload the project** via `git clone` or the PythonAnywhere Files tab.
2. **Create and activate a virtual environment** in a Bash console:
   ```bash
   cd ~/SIEM_simulator
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Cache the Hugging Face dataset locally.** Free PythonAnywhere accounts have
   strict outgoing-request rules, so download the dataset first on your local
   machine or on PythonAnywhere with a paid account. Then upload the cache
   folder to `~/.cache/huggingface/datasets/` on PythonAnywhere.
   On your local machine run once:
   ```bash
   python -c "from datasets import load_dataset; load_dataset('darkknight25/Advanced_SIEM_Dataset')"
   ```
   and upload the generated `~/.cache/huggingface/datasets/` directory.
4. **Edit `wsgi.py`** and replace `/home/yourusername/SIEM_simulator` with your
   actual PythonAnywhere project path.
5. **Configure the Web app** in the PythonAnywhere Web tab:
   - Source code directory: `/home/yourusername/SIEM_simulator`
   - Working directory: `/home/yourusername/SIEM_simulator`
   - WSGI configuration file: point it to `/home/yourusername/SIEM_simulator/wsgi.py`
   - Virtualenv path: `/home/yourusername/SIEM_simulator/venv`
6. **Static files mapping** (optional but recommended for performance):
   - URL: `/static/`
   - Directory: `/home/yourusername/SIEM_simulator/static`
7. **Reload** the web app and visit your PythonAnywhere domain.

> Note: the dataset is kept in memory. The PythonAnywhere free tier memory
> limit is enough for 100k rows, but avoid loading multiple copies.

