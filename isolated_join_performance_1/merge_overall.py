import glob
import os
import re

import pandas as pd
import matplotlib.pyplot as plt


RESULTS = "results_overall/radix_join.csv"
PERF_CSV = "results_overall/radix_join_l12_tlb.csv"


# ---------------------------------------------------------------------------
# Part 1: Parse perf_*.txt once -> results_overall/l12_tlb.csv
# ---------------------------------------------------------------------------

TLB_EVENTS = [
    "dtlb_load_misses.stlb_hit",
    "dtlb_load_misses.miss_causes_a_walk",
    "dtlb_store_misses.stlb_hit",
    "dtlb_store_misses.miss_causes_a_walk",
]

PERF_NAME_RE = re.compile(r"^perf_(\d+)_(\d+)\.txt$")


def read_perf_file(filename):
    counters = {}
    with open(filename, "r") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            value = parts[0].strip()
            event = parts[2].strip()
            try:
                value = float(value)
            except ValueError:
                continue
            counters[event] = value
    return counters


def build_perf_csv():
    """
    Read every results/perf_N_B.txt once and write a tidy CSV:
        N,B,L1_misses,L2_misses,TLB_misses
    Only rows with at least one parsed counter are emitted.
    """
    rows = []

    for filename in sorted(glob.glob("results/perf_*.txt")):
        name = os.path.basename(filename)
        m = PERF_NAME_RE.match(name)
        if not m:
            print(f"Skipping unrecognised perf file: {name}")
            continue

        N = int(m.group(1))
        B = int(m.group(2))

        counters = read_perf_file(filename)
        if not counters:
            print(f"No counters found in {name}; skipping.")
            continue

        l1 = counters.get("l1d.replacement", float("nan"))
        l2 = counters.get("l2_rqsts.demand_data_rd_miss", float("nan"))

        available = [counters[e] for e in TLB_EVENTS if e in counters]
        tlb = sum(available) if available else float("nan")

        rows.append({
            "N": N,
            "B": B,
            "L1_misses": l1,
            "L2_misses": l2,
            "TLB_misses": tlb,
        })

    df = pd.DataFrame(
        rows,
        columns=["N", "B", "L1_misses", "L2_misses", "TLB_misses"],
    ).sort_values(["N", "B"]).reset_index(drop=True)

    os.makedirs(os.path.dirname(PERF_CSV), exist_ok=True)
    df.to_csv(PERF_CSV, index=False)

    print(f"Wrote {len(df)} rows to {PERF_CSV}")
    return df

if __name__ == "__main__":
    build_perf_csv()