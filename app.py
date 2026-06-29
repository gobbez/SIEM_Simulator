"""
SIEM-like dashboard backend.
Dataset is a local SQLite file (dataset.db) — only Flask is required.
Run convert_dataset.py locally to generate dataset.db, then upload it to PythonAnywhere.
"""

import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")
DB_FILE = os.path.join(os.path.dirname(__file__), "dataset.db")


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def check_db():
    """Validate that the SQLite dataset exists and has rows."""
    if not os.path.exists(DB_FILE):
        raise RuntimeError(
            f"Dataset file not found: {DB_FILE}. "
            "Run 'python convert_dataset.py' locally and upload dataset.db."
        )
    with get_db() as conn:
        cur = conn.execute("SELECT COUNT(*) as cnt FROM logs")
        if cur.fetchone()["cnt"] == 0:
            raise RuntimeError("Dataset file exists but contains 0 rows.")


@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON errors instead of Flask HTML debug pages."""
    import traceback
    app.logger.exception(e)
    return jsonify({
        "error": str(e),
        "traceback": traceback.format_exc() if app.debug else None,
    }), 500


@app.before_request
def ensure_db():
    check_db()


def _and(where, extra):
    """Append a condition to an existing WHERE clause."""
    return f"{where} AND {extra}" if where else f"WHERE {extra}"


def build_where(args):
    """Return (WHERE clause string, params list) from request args."""
    conditions, params = [], []

    for field in ("severity", "event_type", "source", "user",
                  "alert_type", "src_ip", "dst_ip", "geo_location"):
        val = args.get(field, "")
        if val:
            items = val.split(",")
            conditions.append(f"{field} IN ({','.join('?' * len(items))})")
            params.extend(items)

    if args.get("anomaly"):
        conditions.append("anomaly = ?")
        params.append(1 if args["anomaly"].lower() == "true" else 0)

    if args.get("from"):
        conditions.append("timestamp >= ?")
        params.append(args["from"])

    if args.get("to"):
        conditions.append("timestamp <= ?")
        params.append(args["to"])

    q = args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        conditions.append(
            "(raw_log LIKE ? OR description LIKE ? OR user LIKE ?"
            " OR object LIKE ? OR src_ip LIKE ? OR dst_ip LIKE ?)"
        )
        params.extend([like] * 6)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def _bucket_expr(delta):
    """Return a SQLite expression that truncates timestamp to the appropriate bucket."""
    if delta is None or delta > timedelta(days=7):
        return "strftime('%Y-%m-%dT00:00:00', timestamp)"
    if delta > timedelta(days=1):
        # 6-hour buckets
        return (
            "strftime('%Y-%m-%dT', timestamp) ||"
            " CASE WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 6 THEN '00'"
            " WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 12 THEN '06'"
            " WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 18 THEN '12'"
            " ELSE '18' END || ':00:00'"
        )
    if delta > timedelta(hours=6):
        return "strftime('%Y-%m-%dT%H:00:00', timestamp)"
    # 10-minute buckets
    return (
        "strftime('%Y-%m-%dT%H:', timestamp) ||"
        " CASE WHEN CAST(strftime('%M', timestamp) AS INTEGER) < 10 THEN '00'"
        " WHEN CAST(strftime('%M', timestamp) AS INTEGER) < 20 THEN '10'"
        " WHEN CAST(strftime('%M', timestamp) AS INTEGER) < 30 THEN '20'"
        " WHEN CAST(strftime('%M', timestamp) AS INTEGER) < 40 THEN '30'"
        " WHEN CAST(strftime('%M', timestamp) AS INTEGER) < 50 THEN '40'"
        " ELSE '50' END || ':00'"
    )


def top_n(conn, col, where, params, n=10):
    """Return [{name, value}] for the top-n values of col, with an Other bucket."""
    w = _and(where, f"{col} IS NOT NULL AND {col} != ''")
    rows = conn.execute(
        f"SELECT {col} as name, COUNT(*) as cnt FROM logs {w}"
        f" GROUP BY {col} ORDER BY cnt DESC LIMIT ?",
        params + [n + 1]
    ).fetchall()

    if len(rows) <= n:
        return [{"name": r["name"], "value": r["cnt"]} for r in rows]

    top_names = [r["name"] for r in rows[:n]]
    placeholders = ",".join("?" * len(top_names))
    other_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM logs {w} AND {col} NOT IN ({placeholders})",
        params + top_names
    ).fetchone()
    result = [{"name": r["name"], "value": r["cnt"]} for r in rows[:n]]
    if other_row and other_row["cnt"]:
        result.append({"name": "Other", "value": other_row["cnt"]})
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MIN(timestamp) as ts_min, MAX(timestamp) as ts_max FROM logs"
        ).fetchone()
    return jsonify({
        "status": "ok",
        "rows": row["cnt"],
        "time_range": {"min": row["ts_min"], "max": row["ts_max"]},
    })


@app.route("/api/filters")
def filters():
    with get_db() as conn:
        def distinct(col):
            rows = conn.execute(
                f"SELECT DISTINCT {col} FROM logs"
                f" WHERE {col} IS NOT NULL AND {col} != '' ORDER BY {col}"
            ).fetchall()
            return [r[0] for r in rows]

        return jsonify({
            "severity": distinct("severity"),
            "event_type": distinct("event_type"),
            "source": distinct("source"),
            "user": distinct("user"),
            "alert_type": distinct("alert_type"),
            "geo_location": distinct("geo_location"),
        })


@app.route("/api/insights")
def insights():
    where, params = build_where(request.args)

    with get_db() as conn:
        # Time range
        row = conn.execute(
            f"SELECT MIN(timestamp) as ts_min, MAX(timestamp) as ts_max FROM logs {where}",
            params
        ).fetchone()
        ts_min, ts_max = row["ts_min"], row["ts_max"]

        delta = None
        if ts_min and ts_max:
            try:
                delta = datetime.fromisoformat(ts_max) - datetime.fromisoformat(ts_min)
            except ValueError:
                pass

        # KPIs
        kpi = conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high,
                COUNT(DISTINCT CASE WHEN user != '' AND user IS NOT NULL THEN user END) as uniq_users,
                COUNT(DISTINCT CASE WHEN src_ip != '' AND src_ip IS NOT NULL THEN src_ip END) as uniq_src,
                COUNT(DISTINCT CASE WHEN dst_ip != '' AND dst_ip IS NOT NULL THEN dst_ip END) as uniq_dst,
                SUM(anomaly) as anomalies,
                AVG(risk_score) as avg_risk
            FROM logs {where}
        """, params).fetchone()

        # Severity distribution
        severity_order = ["critical", "high", "medium", "low", "informational"]
        sev_rows = conn.execute(
            f"SELECT severity, COUNT(*) as cnt FROM logs {where} GROUP BY severity", params
        ).fetchall()
        sev_map = {r["severity"]: r["cnt"] for r in sev_rows}
        severity = [{"name": s, "value": sev_map.get(s, 0)} for s in severity_order]

        # Top-N distributions
        event_type_dist = top_n(conn, "event_type", where, params)
        source_dist = top_n(conn, "source", where, params)
        top_users = top_n(conn, "user", where, params)
        top_actions = top_n(conn, "action", where, params)
        geo_location = top_n(conn, "geo_location", where, params, n=15)
        alert_type = top_n(conn, "alert_type", where, params)

        # Risk score distribution (10 equal-width bins)
        risk_distribution = []
        rs_row = conn.execute(
            f"SELECT MIN(risk_score) as mn, MAX(risk_score) as mx FROM logs {where}", params
        ).fetchone()
        if rs_row["mn"] is not None and rs_row["mx"] is not None:
            mn, mx = rs_row["mn"], rs_row["mx"]
            width = (mx - mn) / 10 if mx != mn else 1
            cases = " ".join(
                f"WHEN risk_score >= {mn + i * width} AND risk_score < {mn + (i + 1) * width}"
                f" THEN '{int(mn + i * width)}-{int(mn + (i + 1) * width)}'"
                for i in range(9)
            )
            last_bin = f"'{int(mn + 9 * width)}-{int(mx)}'"
            w_rs = _and(where, "risk_score IS NOT NULL")
            risk_rows = conn.execute(
                f"SELECT CASE {cases} ELSE {last_bin} END as bin,"
                f" COUNT(*) as cnt, MIN(risk_score) as min_rs"
                f" FROM logs {w_rs} GROUP BY bin ORDER BY min_rs",
                params
            ).fetchall()
            risk_distribution = [{"name": r["bin"], "value": r["cnt"]} for r in risk_rows]

        # Timeline
        bucket_expr = _bucket_expr(delta)
        timeline_rows = conn.execute(
            f"SELECT {bucket_expr} as time, COUNT(*) as cnt"
            f" FROM logs {where} GROUP BY time ORDER BY time",
            params
        ).fetchall()
        timeline = [{"time": r["time"], "count": r["cnt"]} for r in timeline_rows]

        # Anomaly timeline (last 24h by hour)
        anomaly_timeline = []
        if ts_max:
            try:
                dt_max = datetime.fromisoformat(ts_max)
                cutoff = (dt_max - timedelta(hours=24)).isoformat()
                w_at = _and(where, "timestamp >= ?")
                at_rows = conn.execute(
                    f"SELECT strftime('%Y-%m-%dT%H:00:00', timestamp) as hour,"
                    f" anomaly, COUNT(*) as cnt"
                    f" FROM logs {w_at} GROUP BY hour, anomaly ORDER BY hour",
                    params + [cutoff]
                ).fetchall()
                hourly = {}
                for r in at_rows:
                    h = r["hour"]
                    if h not in hourly:
                        hourly[h] = {"time": h, "normal": 0, "anomaly": 0}
                    if r["anomaly"]:
                        hourly[h]["anomaly"] += r["cnt"]
                    else:
                        hourly[h]["normal"] += r["cnt"]
                anomaly_timeline = sorted(hourly.values(), key=lambda x: x["time"])
            except ValueError:
                pass

    return jsonify({
        "kpis": {
            "total_events": kpi["total"],
            "critical_events": kpi["critical"],
            "high_events": kpi["high"],
            "unique_users": kpi["uniq_users"],
            "unique_src_ips": kpi["uniq_src"],
            "unique_dst_ips": kpi["uniq_dst"],
            "anomalies": kpi["anomalies"] or 0,
            "avg_risk_score": round(kpi["avg_risk"], 2) if kpi["avg_risk"] is not None else 0,
        },
        "severity": severity,
        "event_type": event_type_dist,
        "source": source_dist,
        "top_users": top_users,
        "top_actions": top_actions,
        "geo_location": geo_location,
        "alert_type": alert_type,
        "risk_distribution": risk_distribution,
        "timeline": timeline,
        "anomaly_timeline": anomaly_timeline,
    })


@app.route("/api/events")
def events():
    where, params = build_where(request.args)

    sort = request.args.get("sort", "timestamp")
    order = request.args.get("order", "desc").upper()
    allowed_sort = {
        "timestamp", "event_id", "event_type", "source", "severity",
        "user", "action", "src_ip", "dst_ip", "risk_score", "anomaly",
    }
    if sort not in allowed_sort:
        sort = "timestamp"
    if order not in ("ASC", "DESC"):
        order = "DESC"

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 50)), 10), 500)
    except ValueError:
        page, per_page = 1, 50

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM logs {where}", params
        ).fetchone()["cnt"]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT * FROM logs {where}"
            f" ORDER BY {sort} {order} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

    records = []
    for row in rows:
        r = dict(row)
        r["raw_log_preview"] = (r.get("raw_log") or "")[:240]
        records.append(r)

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "events": records,
    })


VALID_LABELS = {"False Positive", "True Positive", "No Action"}


@app.route("/api/events/<event_id>/classify", methods=["POST"])
def classify_event(event_id):
    """Store the user's triage decision and report whether it matches the ground truth."""
    data = request.get_json(silent=True) or {}
    label = data.get("label")
    if label not in VALID_LABELS:
        return jsonify({
            "error": f"Invalid label. Use one of: {', '.join(sorted(VALID_LABELS))}"
        }), 400

    with get_db() as conn:
        row = conn.execute(
            "SELECT true_label, user_label FROM logs WHERE event_id = ?", [event_id]
        ).fetchone()
        if row is None:
            return jsonify({"error": "Event not found"}), 404

        correct = (label == row["true_label"])
        conn.execute(
            "UPDATE logs SET user_label = ? WHERE event_id = ?",
            [label, event_id]
        )
        conn.commit()

    return jsonify({
        "event_id": event_id,
        "label": label,
        "true_label": row["true_label"],
        "correct": correct,
        "previous_label": row["user_label"],
    })


@app.route("/api/events/<event_id>")
def event_detail(event_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM logs WHERE event_id = ?", [event_id]
        ).fetchone()
    if row is None:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(dict(row))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
