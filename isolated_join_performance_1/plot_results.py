
import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import math

RESULTS = "results/results_clean.csv"

df = pd.read_csv(RESULTS)

# Remove invalid or incomplete rows.
df = df.dropna(subset=["N", "B", "elapsed_ms"])

# Read perf stat output.
perf_data = {}

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


for filename in glob.glob("results/perf_*.txt"):

    name = os.path.basename(filename)

    # perf_N_B.txt
    parts = name.replace(".txt", "").split("_")

    N = int(parts[1])
    B = int(parts[2])

    perf_data[(N, B)] = read_perf_file(filename)


# Extract hardware counters.
df["L1_misses"] = float("nan")
df["L2_misses"] = float("nan")
df["TLB_misses"] = float("nan")

for index, row in df.iterrows():

    key = (int(row["N"]), int(row["B"]))

    counters = perf_data.get(key, {})

    df.loc[index, "L1_misses"] = counters.get(
        "l1d.replacement", float("nan")
    )

    df.loc[index, "L2_misses"] = counters.get(
        "l2_rqsts.demand_data_rd_miss", float("nan")
    )

    tlb_events = [
        "dtlb_load_misses.stlb_hit",
        "dtlb_load_misses.miss_causes_a_walk",
        "dtlb_store_misses.stlb_hit",
        "dtlb_store_misses.miss_causes_a_walk"
    ]

    available = [
        counters[e] for e in tlb_events if e in counters
    ]

    if available:
        df.loc[index, "TLB_misses"] = sum(available)


# Four graphs corresponding to Figure 10.
metrics = [
    ("L1_misses", "L1 misses"),
    ("L2_misses", "L2 misses"),
    ("TLB_misses", "TLB misses"),
    ("elapsed_ms", "Execution time (ms)")
]

fig, axes = plt.subplots(
    4, 1,
    figsize=(11, 16),
    sharex=True
)

for ax, (column, ylabel) in zip(axes, metrics):

    for N in sorted(df["N"].unique()):

        subset = df[df["N"] == N].sort_values("B")

        subset = subset[
            subset[column].notna() &
            (subset[column] > 0)
        ]

        if len(subset) == 0:
            continue

        ax.semilogy(
            subset["B"],
            subset[column],
            marker="o",
            markersize=3,
            linewidth=1,
            label=f"N={int(N):,}"
        )

    ax.set_ylabel(ylabel)
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize=8)

axes[-1].set_xlabel("Number of radix bits (B)")

fig.suptitle(
    "Isolated Radix-Join Performance",
    fontsize=15
)

plt.tight_layout()

os.makedirs("plots", exist_ok=True)

plt.savefig(
    "plots/figure10_reproduction.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()

print("Graph saved to plots/figure10_reproduction.png")
