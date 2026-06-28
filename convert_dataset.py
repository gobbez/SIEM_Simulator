"""
Convert the Hugging Face Advanced_SIEM_Dataset to a local Parquet file.

Run this script on your local machine (where you have disk space and network
access). It downloads the dataset, flattens the nested metadata columns and
saves a single `dataset.parquet` file. Upload that file to PythonAnywhere
instead of the Hugging Face cache.
"""

import pandas as pd
from datasets import load_dataset

DATASET_NAME = "darkknight25/Advanced_SIEM_Dataset"
OUTPUT_FILE = "dataset.parquet"


def main():
    print(f"Loading {DATASET_NAME}...")
    ds = load_dataset(DATASET_NAME)
    df = ds["train"].to_pandas()

    print("Flattening nested columns...")
    # advanced_metadata
    meta = df["advanced_metadata"].apply(lambda x: x or {})
    df["geo_location"] = meta.apply(lambda x: x.get("geo_location"))
    df["risk_score"] = meta.apply(lambda x: x.get("risk_score"))
    df["confidence"] = meta.apply(lambda x: x.get("confidence"))
    df["session_id"] = meta.apply(lambda x: x.get("session_id"))
    df["device_hash"] = meta.apply(lambda x: x.get("device_hash"))
    df["user_agent"] = meta.apply(lambda x: x.get("user_agent"))

    # behavioral_analytics
    behavior = df["behavioral_analytics"].apply(lambda x: x or {})
    df["baseline_deviation"] = behavior.apply(lambda x: x.get("baseline_deviation"))
    df["entropy"] = behavior.apply(lambda x: x.get("entropy"))
    df["frequency_anomaly"] = behavior.apply(lambda x: x.get("frequency_anomaly", False))
    df["sequence_anomaly"] = behavior.apply(lambda x: x.get("sequence_anomaly", False))

    print(f"Saving {len(df):,} rows to {OUTPUT_FILE}...")
    df.to_parquet(OUTPUT_FILE, index=False, compression="snappy")

    size_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
    file_mb = pd.io.common.file_exists(OUTPUT_FILE) and (
        __import__("os").path.getsize(OUTPUT_FILE) / 1024 / 1024
    )
    print(f"Done. File size: {file_mb:.2f} MB")
    print(f"In-memory size: {size_mb:.2f} MB")
    print(f"Upload {OUTPUT_FILE} to PythonAnywhere next to app.py.")


if __name__ == "__main__":
    main()
