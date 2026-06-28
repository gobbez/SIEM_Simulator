# SIEM Insights Dashboard

A simple SIEM-style dashboard (similar to Sumo Logic) built with a Python Flask
backend and a vanilla HTML/CSS/JS frontend. It loads the
[`darkknight25/Advanced_SIEM_Dataset`](https://huggingface.co/datasets/darkknight25/Advanced_SIEM_Dataset)
dataset from Hugging Face and exposes insights, KPIs and a filterable event list.

## Structure

```
.
├── app.py                 # Flask backend
├── convert_dataset.py     # Generate dataset.parquet from Hugging Face
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

## Dataset

The app prefers a local `dataset.parquet` file (small, fast, no internet needed
at runtime). Generate it once on a machine with internet access:

```bash
source venv/bin/activate
python convert_dataset.py
```

This creates `dataset.parquet` (≈ 35–40 MB for 100k rows). Place it next to
`app.py` before starting the server.

If `dataset.parquet` is missing, the app falls back to downloading the dataset
from Hugging Face, which requires the `datasets` library and internet access.

## Run

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

The dataset is held in memory; all filters and charts are served from there.

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

This is the recommended approach for PythonAnywhere free accounts because it
avoids downloading the dataset on the server and uses a much smaller virtual
environment.

These instructions assume the project is cloned in
`/home/yourusername/SIEM_Simulator`. Replace `yourusername` and the folder name
with your actual values.

### 1. On your local machine: generate `dataset.parquet`

You need internet access and a bit of free disk space. In the project folder:

```bash
python3 -m venv venv
source venv/bin/activate
pip install datasets pandas pyarrow
python convert_dataset.py
```

This produces `dataset.parquet` (≈ 35–40 MB).

### 2. Upload the project and the Parquet file to PythonAnywhere

Upload the whole project folder, **including `dataset.parquet`**, to
`/home/yourusername/SIEM_Simulator` using the Files tab, `scp`, `rsync` or a
similar tool.

> Do **not** upload the `venv/` folder.

### 3. Open a Bash console and create a small virtual environment

```bash
cd ~/SIEM_Simulator
rm -rf venv                 # remove any previous venv to free space
python3 -m venv venv
source venv/bin/activate
pip install --no-cache-dir -r requirements.txt
```

The new `requirements.txt` no longer includes `datasets`, so the venv will be
significantly smaller (≈ 200–250 MB instead of 330+ MB).

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
   - **Source code:** `/home/yourusername/SIEM_Simulator`
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

Click the **Reload** button and visit your PythonAnywhere domain, e.g.
`https://yourusername.pythonanywhere.com`.

The first request may take 10–30 seconds while the Parquet file is loaded into
memory.

### Troubleshooting

- **500 Internal Server Error:** open the **Error log** in the Web tab. The most
  common causes are a missing `dataset.parquet` file or a wrong path in
  `wsgi.py`.
- **Disk quota exceeded during `pip install`:** remove old virtual environments
  (`rm -rf ~/SIEM_Simulator/venv`) and reinstall with
  `pip install --no-cache-dir -r requirements.txt`.
- **Dataset not found:** ensure `dataset.parquet` is in the project root next to
  `app.py`.
- **Static files missing (no CSS/JS):** double-check step 6 and reload the app.
- **Memory errors:** the free tier handles 100k rows, but if you reload many
  times in a row, wait a moment for the old worker to be killed.
