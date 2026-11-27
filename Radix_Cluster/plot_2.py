import csv
import re
import math
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Part 1: Merge perf CSV files into a single counters.csv
# ---------------------------------------------------------------------------

INPUT_DIR = Path("perf_results")
OUTPUT_FILE = Path("results/counters.csv")
PLOTS_DIR = Path("results/plots")

# Map the event names to the columns in the final CSV.
EVENTS = {
    "L1-dcache-load-misses": "L1_misses",
    "l2_rqsts.demand_data_rd_miss": "L2_misses",
    "dTLB-load-misses": "DTLB_load_misses",
    "dTLB-store-misses": "DTLB_store_misses",
}


def extract_counter(filepath, target_event):
    with open(filepath, "r") as f:
        reader = csv.reader(f)

        for row in reader:
            # Locate the requested event in this row.
            if not any(target_event in field for field in row):
                continue

            # Find the numeric counter value before the event name.
            for field in row:
                try:
                    value = float(field.strip())
                    if math.isfinite(value):
                        return value
                except ValueError:
                    continue

    return None


def merge_counters():
    results = []

    for filepath in sorted(INPUT_DIR.glob("B*_P*.csv")):
        match = re.search(r"B(\d+)_P(\d+)", filepath.name)

        if not match:
            continue

        B = int(match.group(1))
        P = int(match.group(2))

        row = {
            "B": B,
            "P": P,
        }

        for event, column in EVENTS.items():
            row[column] = extract_counter(filepath, event)

        # Total DTLB misses = load misses + store misses.
        load = row["DTLB_load_misses"]
        store = row["DTLB_store_misses"]

        row["TLB_misses"] = (
            load + store
            if load is not None and store is not None
            else None
        )

        results.append(row)

    # Sort by B and then P.
    results.sort(key=lambda x: (x["B"], x["P"]))

    columns = [
        "B",
        "P",
        "L1_misses",
        "L2_misses",
        "DTLB_load_misses",
        "DTLB_store_misses",
        "TLB_misses",
    ]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    print(f"Successfully processed {len(results)} files.")
    print(f"Output saved to: {OUTPUT_FILE}")

    if len(results) != 76:
        print("WARNING: Expected 76 files. Check your perf_results directory.")

    missing = [
        (r["B"], r["P"])
        for r in results
        if any(r[col] is None for col in columns[2:])
    ]

    if missing:
        print("\nWARNING: Missing counter values for:")
        for B, P in missing:
            print(f"  B={B}, P={P}")


# ---------------------------------------------------------------------------
# Part 2: Plot L1/L2/TLB misses from counters.csv
# ---------------------------------------------------------------------------

def plot_counters():
    df = pd.read_csv(OUTPUT_FILE)

    metrics = [
        ("L1_misses", "L1 Data Cache Misses"),
        ("L2_misses", "L2 Demand Data-Read Misses"),
        ("TLB_misses", "DTLB Load + Store Misses"),
    ]

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    for column, title in metrics:
        plt.figure(figsize=(9, 5))

        for p in sorted(df["P"].unique()):
            subset = df[df["P"] == p].sort_values("B")

            plt.plot(
                subset["B"],
                subset[column],
                marker="o",
                label=f"{p} pass{'es' if p > 1 else ''}"
            )

        plt.xlabel("Number of bits (B)")
        plt.ylabel("Number of misses")
        plt.title(title)
        plt.xticks(range(10, 28))
        plt.yscale("log")
        plt.grid(True, which="both", linestyle="--", alpha=0.4)
        plt.legend()
        plt.tight_layout()

        out_path = PLOTS_DIR / f"{column}.png"
        plt.savefig(out_path, dpi=300)
        print(f"Plot saved to: {out_path}")

        plt.show()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    merge_counters()
    plot_counters()