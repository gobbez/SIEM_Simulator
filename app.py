"""
SIEM-like dashboard backend for the darkknight25/Advanced_SIEM_Dataset.
Loads the Hugging Face dataset into memory and exposes REST endpoints used
by a simple HTML/CSS/JS frontend.
"""

import os
import re
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
from datasets import load_dataset
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

DATASET_NAME = "darkknight25/Advanced_SIEM_Dataset"
_df = None


def load_data():
    """Load the dataset from Hugging Face and normalise it into a DataFrame."""
    global _df
    if _df is not None:
        return _df

    print(f"[{datetime.now()}] Loading dataset {DATASET_NAME}...")
    ds = load_dataset(DATASET_NAME)
    train = ds["train"]

    # Convert to pandas. 100k rows is small enough to keep in memory.
    df = train.to_pandas()

    # Normalise timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Extract nested fields for easier filtering/aggregation
    meta = df["advanced_metadata"].apply(lambda x: x or {})
    df["geo_location"] = meta.apply(lambda x: x.get("geo_location"))
    df["risk_score"] = meta.apply(lambda x: x.get("risk_score"))
    df["confidence"] = meta.apply(lambda x: x.get("confidence"))
    df["session_id"] = meta.apply(lambda x: x.get("session_id"))

    behavior = df["behavioral_analytics"].apply(lambda x: x or {})
    df["baseline_deviation"] = behavior.apply(lambda x: x.get("baseline_deviation"))
    df["entropy"] = behavior.apply(lambda x: x.get("entropy"))
    df["frequency_anomaly"] = behavior.apply(lambda x: x.get("frequency_anomaly", False))
    df["sequence_anomaly"] = behavior.apply(lambda x: x.get("sequence_anomaly", False))

    # Ensure string columns are strings (or empty string when null)
    text_cols = [
        "event_id", "event_type", "source", "severity", "raw_log", "user",
        "action", "object", "parent_process", "additional_info", "description",
        "device_type", "device_id", "firmware_version", "src_ip", "dst_ip",
        "alert_type", "signature_id", "category", "cloud_service", "resource_id",
        "model_id", "input_hash", "output_hash", "protocol", "method", "mac_address",
        "geo_location", "session_id",
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).replace("nan", "")

    # Numeric cleanup
    for col in ["src_port", "dst_port", "bytes", "duration", "process_id"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    df["anomaly"] = df["frequency_anomaly"] | df["sequence_anomaly"]
    df["date"] = df["timestamp"].dt.floor("min")
    df["hour"] = df["timestamp"].dt.floor("h")

    # Sort by time descending for the event table
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)

    _df = df
    print(f"[{datetime.now()}] Dataset ready: {len(df):,} rows")
    return _df


@app.before_request
def ensure_data():
    if _df is None:
        load_data()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_top(series, n=10, other_label="Other"):
    """Return a list of {name, value} for the top-n values of a series."""
    counts = series[series.astype(bool)].value_counts()
    if len(counts) <= n:
        return [{"name": str(k), "value": int(v)} for k, v in counts.items()]
    top = counts.head(n)
    other = counts.iloc[n:].sum()
    result = [{"name": str(k), "value": int(v)} for k, v in top.items()]
    if other:
        result.append({"name": other_label, "value": int(other)})
    return result


def apply_filters(df, args):
    """Apply query-string filters to the DataFrame."""
    if args.get("severity"):
        df = df[df["severity"].isin(args.get("severity").split(","))]
    if args.get("event_type"):
        df = df[df["event_type"].isin(args.get("event_type").split(","))]
    if args.get("source"):
        df = df[df["source"].isin(args.get("source").split(","))]
    if args.get("user"):
        df = df[df["user"].isin(args.get("user").split(","))]
    if args.get("alert_type"):
        df = df[df["alert_type"].isin(args.get("alert_type").split(","))]
    if args.get("src_ip"):
        df = df[df["src_ip"].isin(args.get("src_ip").split(","))]
    if args.get("dst_ip"):
        df = df[df["dst_ip"].isin(args.get("dst_ip").split(","))]
    if args.get("geo_location"):
        df = df[df["geo_location"].isin(args.get("geo_location").split(","))]
    if args.get("anomaly"):
        df = df[df["anomaly"] == (args.get("anomaly").lower() == "true")]

    # Time range: from / to in ISO-8601
    if args.get("from"):
        df = df[df["timestamp"] >= pd.to_datetime(args.get("from"))]
    if args.get("to"):
        df = df[df["timestamp"] <= pd.to_datetime(args.get("to"))]

    # Free text search across common fields
    q = args.get("q", "").strip().lower()
    if q:
        mask = (
            df["raw_log"].str.lower().str.contains(q, na=False, regex=False)
            | df["description"].str.lower().str.contains(q, na=False, regex=False)
            | df["user"].str.lower().str.contains(q, na=False, regex=False)
            | df["object"].str.lower().str.contains(q, na=False, regex=False)
            | df["src_ip"].str.lower().str.contains(q, na=False, regex=False)
            | df["dst_ip"].str.lower().str.contains(q, na=False, regex=False)
        )
        df = df[mask]
    return df.copy()


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    df = load_data()
    return jsonify({
        "status": "ok",
        "rows": len(df),
        "time_range": {
            "min": df["timestamp"].min().isoformat() if not df["timestamp"].isna().all() else None,
            "max": df["timestamp"].max().isoformat() if not df["timestamp"].isna().all() else None,
        }
    })


@app.route("/api/filters")
def filters():
    """Return distinct values useful for the filter dropdowns."""
    df = load_data()
    return jsonify({
        "severity": df["severity"][df["severity"].astype(bool)].unique().tolist(),
        "event_type": df["event_type"][df["event_type"].astype(bool)].unique().tolist(),
        "source": df["source"][df["source"].astype(bool)].unique().tolist(),
        "user": df["user"][df["user"].astype(bool)].unique().tolist(),
        "alert_type": df["alert_type"][df["alert_type"].astype(bool)].unique().tolist(),
        "geo_location": sorted(df["geo_location"][df["geo_location"].astype(bool)].unique().tolist()),
    })


@app.route("/api/insights")
def insights():
    """Aggregate KPIs and distributions for the dashboard charts."""
    df = apply_filters(load_data().copy(), request.args)

    # Time bucket selection based on time range
    time_min = df["timestamp"].min()
    time_max = df["timestamp"].max()
    if pd.isna(time_min) or pd.isna(time_max):
        bucket = "hour"
    else:
        delta = time_max - time_min
        if delta <= timedelta(hours=6):
            bucket = "10min"
        elif delta <= timedelta(days=1):
            bucket = "hour"
        elif delta <= timedelta(days=7):
            bucket = "6h"
        else:
            bucket = "D"

    df["time_bucket"] = df["timestamp"].dt.floor(bucket)
    timeline = (
        df.groupby("time_bucket")
        .size()
        .reset_index(name="count")
        .rename(columns={"time_bucket": "time"})
    )
    timeline["time"] = timeline["time"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Severity distribution with critical/high emphasis
    severity_order = ["critical", "high", "medium", "low", "informational"]
    severity_counts = df["severity"].value_counts().to_dict()
    severity = [{"name": s, "value": int(severity_counts.get(s, 0))} for s in severity_order]

    # Risk score distribution (10 bins)
    rs = df["risk_score"].dropna()
    if len(rs):
        bins = pd.cut(rs, bins=10, include_lowest=True)
        risk_hist = bins.value_counts().sort_index()
        risk_distribution = [
            {"name": f"{int(interval.left)}-{int(interval.right)}", "value": int(v)}
            for interval, v in risk_hist.items()
        ]
    else:
        risk_distribution = []

    # Recent anomaly timeline (last 24h by hour)
    last_day = df[df["timestamp"] >= (time_max - timedelta(hours=24))] if not pd.isna(time_max) else df
    anomaly_timeline = []
    if not last_day.empty:
        at = (
            last_day.groupby([last_day["timestamp"].dt.floor("h"), "anomaly"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        at = at.rename(columns={"timestamp": "time"})
        for _, row in at.iterrows():
            anomaly_timeline.append({
                "time": row["time"].strftime("%Y-%m-%dT%H:%M:%S"),
                "normal": int(row.get(False, 0)),
                "anomaly": int(row.get(True, 0)),
            })

    return jsonify({
        "kpis": {
            "total_events": int(len(df)),
            "critical_events": int((df["severity"] == "critical").sum()),
            "high_events": int((df["severity"] == "high").sum()),
            "unique_users": int(df["user"][df["user"].astype(bool)].nunique()),
            "unique_src_ips": int(df["src_ip"][df["src_ip"].astype(bool)].nunique()),
            "unique_dst_ips": int(df["dst_ip"][df["dst_ip"].astype(bool)].nunique()),
            "anomalies": int(df["anomaly"].sum()),
            "avg_risk_score": round(df["risk_score"].mean(), 2) if not df["risk_score"].isna().all() else 0,
        },
        "severity": severity,
        "event_type": safe_top(df["event_type"]),
        "source": safe_top(df["source"]),
        "top_users": safe_top(df["user"]),
        "top_actions": safe_top(df["action"]),
        "geo_location": safe_top(df["geo_location"], n=15),
        "alert_type": safe_top(df["alert_type"]),
        "risk_distribution": risk_distribution,
        "timeline": timeline.to_dict(orient="records"),
        "anomaly_timeline": anomaly_timeline,
    })


@app.route("/api/events")
def events():
    """Paginated, filterable event list."""
    df = load_data().copy()
    df = apply_filters(df, request.args)

    # Sorting
    sort = request.args.get("sort", "timestamp")
    order = request.args.get("order", "desc")
    if sort in df.columns:
        df = df.sort_values(sort, ascending=(order == "asc"), na_position="last")

    # Pagination
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 50)), 10), 500)
    except ValueError:
        page, per_page = 1, 50

    total = len(df)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    # Convert to JSON-serialisable dicts
    records = page_df.to_dict(orient="records")
    for r in records:
        # Replace NaT/NaN with None
        for k, v in list(r.items()):
            if pd.isna(v):
                r[k] = None
            elif isinstance(v, datetime):
                r[k] = v.isoformat()
        # Trim huge raw logs for the list view
        r["raw_log_preview"] = (r.get("raw_log") or "")[:240]

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "events": records,
    })


@app.route("/api/events/<event_id>")
def event_detail(event_id):
    """Return a single event with all its fields."""
    df = load_data()
    row = df[df["event_id"] == event_id]
    if row.empty:
        return jsonify({"error": "Event not found"}), 404
    record = row.iloc[0].to_dict()
    for k, v in list(record.items()):
        if pd.isna(v):
            record[k] = None
        elif isinstance(v, datetime):
            record[k] = v.isoformat()
    return jsonify(record)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
