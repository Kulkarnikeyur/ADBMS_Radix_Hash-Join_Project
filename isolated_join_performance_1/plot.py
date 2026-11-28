import csv
import glob
import os
import re

import pandas as pd
import matplotlib.pyplot as plt


RESULTS = "results/results.csv"
PERF_CSV = "results/results_l12_tlb.csv"


# ---------------------------------------------------------------------------
# Part 1: Parse perf_*.txt once -> results/l12_tlb.csv
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


# ---------------------------------------------------------------------------
# Part 2: Merge perf CSV into results and plot Figure 10
# ---------------------------------------------------------------------------

def plot_figure10():
    # Read results.
    df = pd.read_csv(RESULTS)
    df = df.dropna(subset=["N", "B", "elapsed_ms"])
    df["N"] = df["N"].astype(int)
    df["B"] = df["B"].astype(int)

    # Read (or build) the perf CSV.
    if os.path.exists(PERF_CSV):
        perf_df = pd.read_csv(PERF_CSV)
        print(f"Loaded perf data from {PERF_CSV}")
    else:
        perf_df = build_perf_csv()

    # Left-join: keep all result rows, attach counters where available.
    df = df.merge(
        perf_df[["N", "B", "L1_misses", "L2_misses", "TLB_misses"]],
        on=["N", "B"],
        how="left",
    )

    # Four graphs corresponding to Figure 10.
    metrics = [
        ("L1_misses", "L1 misses"),
        ("L2_misses", "L2 misses"),
        ("TLB_misses", "TLB misses"),
        ("elapsed_ms", "Execution time (ms)"),
    ]

    fig, axes = plt.subplots(
        4, 1,
        figsize=(11, 16),
        sharex=True,
    )

    for ax, (column, ylabel) in zip(axes, metrics):
        for N in sorted(df["N"].unique()):
            subset = df[df["N"] == N].sort_values("B")
            subset = subset[
                subset[column].notna() & (subset[column] > 0)
            ]
            if len(subset) == 0:
                continue

            ax.semilogy(
                subset["B"],
                subset[column],
                marker="o",
                markersize=3,
                linewidth=1,
                label=f"N={int(N):,}",
            )

        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend(fontsize=8)

    axes[-1].set_xlabel("Number of radix bits (B)")
    fig.suptitle("Isolated Radix-Join Performance", fontsize=15)

    plt.tight_layout()

    os.makedirs("plots", exist_ok=True)
    plt.savefig(
        "plots/figure10_reproduction.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.show()

    print("Graph saved to plots/figure10_reproduction.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_perf_csv()      # always regenerate from perf_*.txt
    plot_figure10()       # consumes results/l12_tlb.csv