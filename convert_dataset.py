"""
Convert Advanced_SIEM_Dataset to a local SQLite file (dataset.db).

Requirements (local only — NOT needed on PythonAnywhere):
    pip install pyarrow
    pip install requests   # only if you need to download the dataset

Usage
-----
If you already have dataset.parquet (generated previously):
    python convert_dataset.py

To download fresh from Hugging Face and then convert:
    python convert_dataset.py --download
"""

import os
import sqlite3
import sys

try:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
except ImportError:
    sys.exit(
        "\nERROR: pyarrow is not installed.\n"
        "Run: pip install pyarrow\n"
    )

DATASET_NAME = "darkknight25/Advanced_SIEM_Dataset"
PARQUET_FILE = "dataset.parquet"
OUTPUT_FILE = "dataset.db"

INDEXES = (
    "timestamp", "severity", "event_type", "source", "user",
    "alert_type", "src_ip", "dst_ip", "geo_location", "anomaly", "event_id",
)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_parquet():
    """Download the first train-split Parquet file from Hugging Face Hub."""
    try:
        import requests
    except ImportError:
        sys.exit("\nERROR: requests is not installed.\nRun: pip install requests\n")

    print("Fetching parquet URL from Hugging Face Hub…")
    api_url = f"https://huggingface.co/api/datasets/{DATASET_NAME}/parquet"
    resp = requests.get(api_url, timeout=30)
    resp.raise_for_status()

    train_files = resp.json().get("train", [])
    if not train_files:
        sys.exit("No train-split parquet files found on Hugging Face.")

    url = train_files[0]["url"]
    print(f"Downloading {url} …")

    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(PARQUET_FILE, "wb") as f:
            for chunk in r.iter_content(chunk_size=65_536):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / total * 100:.0f}%  ({done // 1_048_576} MB)", end="", flush=True)
    print(f"\nSaved to {PARQUET_FILE}")


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def flatten_structs(table):
    """Extract fields from nested struct columns into flat top-level columns."""
    STRUCT_FIELDS = {
        "advanced_metadata": [
            "geo_location", "risk_score", "confidence",
            "session_id", "device_hash", "user_agent",
        ],
        "behavioral_analytics": [
            "baseline_deviation", "entropy",
            "frequency_anomaly", "sequence_anomaly",
        ],
    }
    for struct_col, fields in STRUCT_FIELDS.items():
        if struct_col not in table.schema.names:
            continue
        col = table[struct_col]
        col_type = table.schema.field(struct_col).type
        for field_name in fields:
            try:
                if pa.types.is_struct(col_type):
                    extracted = pc.struct_field(col, field_name)
                else:
                    extracted = pa.array([None] * len(table))
            except (KeyError, pa.ArrowInvalid):
                extracted = pa.array([None] * len(table))
            table = table.append_column(field_name, extracted)
        idx = table.schema.get_field_index(struct_col)
        table = table.remove_column(idx)
    return table


def normalize(table):
    """Normalize column types for SQLite storage."""
    new_cols = {}

    for i, field in enumerate(table.schema):
        col = table.column(i)
        name = field.name

        if pa.types.is_boolean(field.type):
            col = col.cast(pa.int32())
        elif pa.types.is_timestamp(field.type):
            col = pc.strftime(col, format="%Y-%m-%dT%H:%M:%S")
        elif pa.types.is_floating(field.type) or pa.types.is_integer(field.type):
            pass  # keep numeric as-is
        else:
            # Cast everything else to string; replace nulls with ""
            col = col.cast(pa.string(), safe=False)
            null_mask = pc.is_null(col)
            col = pc.if_else(null_mask, pa.scalar(""), col)

        new_cols[name] = col

    # Derived anomaly flag (int)
    if "frequency_anomaly" in new_cols and "sequence_anomaly" in new_cols:
        freq = new_cols["frequency_anomaly"].cast(pa.bool_())
        seq = new_cols["sequence_anomaly"].cast(pa.bool_())
        new_cols["anomaly"] = pc.or_(freq, seq).cast(pa.int32())

    return pa.table(new_cols)


# ---------------------------------------------------------------------------
# Write SQLite
# ---------------------------------------------------------------------------

def table_to_sqlite(table, db_path):
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)

    # CREATE TABLE
    col_defs = []
    for field in table.schema:
        if pa.types.is_floating(field.type):
            col_defs.append(f'"{field.name}" REAL')
        elif pa.types.is_integer(field.type):
            col_defs.append(f'"{field.name}" INTEGER')
        else:
            col_defs.append(f'"{field.name}" TEXT')
    conn.execute(f"CREATE TABLE logs ({', '.join(col_defs)})")

    col_names = table.schema.names
    quoted = [f'"{c}"' for c in col_names]
    placeholders = ",".join("?" * len(col_names))
    insert_sql = f"INSERT INTO logs ({','.join(quoted)}) VALUES ({placeholders})"

    total = len(table)
    inserted = 0
    for batch in table.to_batches(max_chunksize=5_000):
        columns = [batch.column(c).to_pylist() for c in col_names]
        rows = list(zip(*columns))
        conn.executemany(insert_sql, rows)
        inserted += len(rows)
        print(f"\r  {inserted:,} / {total:,} rows", end="", flush=True)

    print()
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    download = "--download" in sys.argv

    if download or not os.path.exists(PARQUET_FILE):
        if not os.path.exists(PARQUET_FILE):
            print(f"{PARQUET_FILE} not found — downloading from Hugging Face…")
        download_parquet()

    print(f"Reading {PARQUET_FILE}…")
    table = pq.read_table(PARQUET_FILE)
    print(f"  {len(table):,} rows, {len(table.schema)} columns")

    print("Flattening nested columns…")
    table = flatten_structs(table)

    print("Normalizing types…")
    table = normalize(table)

    print(f"Writing to {OUTPUT_FILE}…")
    conn = table_to_sqlite(table, OUTPUT_FILE)

    print("Creating indexes…")
    for col in INDEXES:
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{col} ON logs("{col}")')
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

    size_mb = os.path.getsize(OUTPUT_FILE) / 1_048_576
    print(f"\nDone. {OUTPUT_FILE}: {size_mb:.1f} MB")
    print(f"Upload {OUTPUT_FILE} to PythonAnywhere next to app.py.")


if __name__ == "__main__":
    main()
