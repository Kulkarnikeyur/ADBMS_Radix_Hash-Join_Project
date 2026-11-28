
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import glob
import os

# ---------------------------------------
# 1. Read all experimental repetitions
# ---------------------------------------

df = pd.read_csv("results_overall/hash_join.csv")

df = df.dropna(subset=["N", "B", "elapsed_ms"])

# ---------------------------------------
# 2. Parse perf counter files
# ---------------------------------------

perf = {}

def read_perf(path):

    counts = {}

    with open(path) as f:

        for line in f:

            p = line.strip().split(",")

            if len(p) < 3:
                continue

            try:
                val = float(p[0])
            except ValueError:
                continue

            event = p[2].strip()

            counts[event] = val

    return counts


for path in glob.glob("results_overall/perf_*.txt"):

    name = os.path.basename(path)

    # perf_N_B_REPEAT.txt
    parts = name.replace(".txt", "").split("_")

    N = int(parts[1])
    B = int(parts[2])
    REP = int(parts[3])

    perf[(N, B, REP)] = read_perf(path)


# ---------------------------------------
# 3. Attach hardware-counter values
# ---------------------------------------

df["L1"] = np.nan
df["L2"] = np.nan
df["TLB"] = np.nan

tlb_events = [
    "dtlb_load_misses.stlb_hit",
    "dtlb_load_misses.miss_causes_a_walk",
    "dtlb_store_misses.stlb_hit",
    "dtlb_store_misses.miss_causes_a_walk"
]

for i, row in df.iterrows():

    key = (
        int(row["N"]),
        int(row["B"]),
        int(row["repeat"])
    )

    c = perf.get(key, {})

    df.loc[i, "L1"] = c.get(
        "l1d.replacement", np.nan
    )

    df.loc[i, "L2"] = c.get(
        "l2_rqsts.demand_data_rd_miss", np.nan
    )

    vals = [
        c[e] for e in tlb_events
        if e in c
    ]

    if vals:
        df.loc[i, "TLB"] = sum(vals)


# ---------------------------------------
# 4. Aggregate using median
# ---------------------------------------

agg = df.groupby(["N", "B"], as_index=False).agg({
    "H": "median",
    "avg_cluster": "median",
    "clusters": "median",
    "hash_probes": "median",
    "matches": "median",
    "elapsed_ms": "median",
    "L1": "median",
    "L2": "median",
    "TLB": "median"
})

agg.to_csv("results_overall/median_results.csv", index=False)

# ---------------------------------------
# 5. Calibrated cost model
# ---------------------------------------

# Model:
# T = a*N + b*H + c*L1 + d*L2 + e*TLB
#
# All times are milliseconds.
#
# Coefficients are fitted from YOUR measurements,
# not copied from the original paper.

X = np.column_stack([
    agg["N"].values,
    agg["H"].values,
    agg["L1"].values,
    agg["L2"].values,
    agg["TLB"].values
])

y = agg["elapsed_ms"].values

valid = (
    np.isfinite(X).all(axis=1) &
    np.isfinite(y) &
    (y > 0)
)

X_valid = X[valid]
y_valid = y[valid]

# Least-squares fit.
coef, _, _, _ = np.linalg.lstsq(
    X_valid, y_valid, rcond=None
)

agg["model_ms"] = (
    coef[0] * agg["N"] +
    coef[1] * agg["H"] +
    coef[2] * agg["L1"] +
    coef[3] * agg["L2"] +
    coef[4] * agg["TLB"]
)

print("\nFitted model coefficients:")
print("per tuple:          ", coef[0])
print("per cluster:        ", coef[1])
print("per L1 replacement: ", coef[2])
print("per L2 miss:        ", coef[3])
print("per TLB miss:       ", coef[4])

agg.to_csv("results_overall/phash_join.csv", index=False)

