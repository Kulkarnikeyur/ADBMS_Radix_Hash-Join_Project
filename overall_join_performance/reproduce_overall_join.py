from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import csv

# ============================================================
# 0. CONFIGURATION
# ============================================================

BASE = Path(__file__).resolve().parent

RADIX_CLUSTER_FILE = BASE / "radix_cluster.csv"
RADIX_JOIN_FILE = BASE / "radix_join_time.csv"
PHASH_JOIN_FILE = BASE / "phash_join.csv"

OUT = BASE / "output"
OUT.mkdir(exist_ok=True)

# radix_cluster.csv contains measurements at this cardinality.
CLUSTER_REFERENCE_N = 8_000_000

# Paper strategy parameters.
INNER_TUPLE_BYTES = 12
TARGET_PHASH_CLUSTER = 256
OPTIMAL_PHASH_CLUSTER = 200
OPTIMAL_RADIX_CLUSTER = 4
TARGET_RADIX_CLUSTER = 8

# Hardware parameters used to calculate the cache/TLB strategies.
#
# IMPORTANT:
# Verify these against the hardware configuration used in your
# reproduction. These are exposed here rather than hidden in code.
L1_BYTES = 32 * 1024
L2_BYTES = 4 * 1024 * 1024
TLB_ENTRIES = 64
PAGE_BYTES = 16 * 1024

# Figure 13 cardinalities shown in the paper.
FIG13_CARDINALITIES = [
    15_625,
    62_500,
    250_000,
    1_000_000,
    4_000_000,
    16_000_000,
    64_000_000,
]

plt.rcParams.update({
    "figure.figsize": (10, 6),
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
})


# ============================================================
# 1. CSV LOADING AND NORMALIZATION
# ============================================================

def read_radix_join_csv(path):
    expected_columns = [
        "status", "N", "B", "H", "avg_cluster",
        "comparisons", "matches", "elapsed_ms", "checksum"
    ]

    with open(path, "r", newline="") as f:
        rows = list(csv.reader(f))

    if not rows:
        raise ValueError("radix_join_time.csv is empty")

    # Skip the header. The data rows may contain the extra RESULT field.
    data_rows = rows[1:]

    normalized = []

    for row in data_rows:
        row = [x.strip() for x in row]

        if not row or all(x == "" for x in row):
            continue

        # Expected data format:
        # RESULT,N,B,H,avg_cluster,comparisons,matches,elapsed_ms,checksum
        if len(row) == 9:
            normalized.append(row)

        # Also support data without the leading RESULT field.
        elif len(row) == 8:
            normalized.append(["RESULT"] + row)

        else:
            raise ValueError(
                f"Unexpected row with {len(row)} fields: {row}"
            )

    data = pd.DataFrame(normalized, columns=expected_columns)

    data = data.drop(columns=["status"])

    for col in [
        "N", "B", "H", "avg_cluster",
        "comparisons", "matches", "elapsed_ms", "checksum"
    ]:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    return data.dropna(subset=["N", "B", "elapsed_ms"])


def read_normal_csv(path, required_columns):
    data = pd.read_csv(path)
    data.columns = [str(c).strip() for c in data.columns]

    missing = [
        c for c in required_columns if c not in data.columns
    ]

    if missing:
        raise ValueError(
            f"{path.name} is missing columns: {missing}\n"
            f"Found columns: {list(data.columns)}"
        )

    for col in required_columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna(subset=required_columns)
    return data


radix_cluster = read_normal_csv(
    RADIX_CLUSTER_FILE,
    ["N", "B", "P", "bits_per_pass", "run", "time_ms"]
)

radix_join = read_radix_join_csv(RADIX_JOIN_FILE)

phash_join = read_normal_csv(
    PHASH_JOIN_FILE,
    ["N", "B", "elapsed_ms"]
)

print("Loaded CSV files:")
print("radix_cluster:", len(radix_cluster), "rows")
print("radix_join:   ", len(radix_join), "rows")
print("phash_join:   ", len(phash_join), "rows")


# ============================================================
# 2. SELECT OPTIMAL RADIX CLUSTERING PASSES
# ============================================================

# The paper says bits should be distributed evenly across passes.
# We use the measured median clustering time to select P for each B.

cluster_summary = (
    radix_cluster
    .groupby(["N", "B", "P"], as_index=False)
    .agg(
        median_cluster_ms=("time_ms", "median"),
        mean_cluster_ms=("time_ms", "mean"),
        run_count=("time_ms", "count"),
    )
)

reference_cluster = cluster_summary[
    cluster_summary["N"] == CLUSTER_REFERENCE_N
].copy()

if reference_cluster.empty:
    raise ValueError(
        f"No radix clustering rows found for N={CLUSTER_REFERENCE_N:,}."
    )

# For every B, choose the P with the smallest median time.
best_passes = (
    reference_cluster
    .sort_values(["B", "median_cluster_ms", "P"])
    .groupby("B", as_index=False)
    .first()
    [["B", "P", "median_cluster_ms", "run_count"]]
    .rename(columns={
        "P": "optimal_P",
        "median_cluster_ms": "cluster_ms_at_reference_N",
    })
)

best_passes.to_csv(
    OUT / "optimal_radix_passes_by_B.csv",
    index=False
)

print("\nOptimal pass count by B:")
print(best_passes.to_string(index=False))


def nearest_measured_B(B):
    """Return the closest B for which clustering was measured."""
    values = best_passes["B"].to_numpy()
    return int(values[np.argmin(np.abs(values - B))])


def optimal_P_for_B(B):
    measured_B = nearest_measured_B(B)
    row = best_passes[best_passes["B"] == measured_B].iloc[0]
    return int(row["optimal_P"])


# ============================================================
# 3. PREPARE JOIN-ONLY MEASUREMENTS
# ============================================================

# Median protects against repeated-run noise if the input has
# multiple measurements for the same N and B.
radix_join_summary = (
    radix_join
    .groupby(["N", "B"], as_index=False)
    .agg(elapsed_ms=("elapsed_ms", "median"))
)

phash_join_summary = (
    phash_join
    .groupby(["N", "B"], as_index=False)
    .agg(elapsed_ms=("elapsed_ms", "median"))
)


# ============================================================
# 4. INTERPOLATION HELPERS
# ============================================================

def interpolate_at_B(frame, B):
    """
    Interpolate elapsed_ms against B for one cardinality.
    Values outside the measured B range are clamped to the
    nearest measured endpoint, and reported as such.
    """
    frame = frame.sort_values("B")

    x = frame["B"].to_numpy(dtype=float)
    y = frame["elapsed_ms"].to_numpy(dtype=float)

    if len(x) == 1:
        return float(y[0])

    if B < x.min() or B > x.max():
        warnings.warn(
            f"B={B:.3f} outside measured range "
            f"[{x.min()}, {x.max()}]; clamping."
        )

    return float(np.interp(B, x, y))


def join_time_at(df, N, B):
    """
    Obtain join time at (N, B).

    First interpolate across B separately for each measured N.
    Then interpolate across cardinality in log2(N).

    This permits Figure 13 strategy points at cardinalities
    not explicitly present in the join CSV.
    """
    per_N = []

    for measured_N, group in df.groupby("N"):
        t = interpolate_at_B(group, B)
        per_N.append((float(measured_N), t))

    per_N.sort(key=lambda x: x[0])

    ns = np.array([x[0] for x in per_N], dtype=float)
    times = np.array([x[1] for x in per_N], dtype=float)

    if len(ns) == 1:
        return float(times[0])

    log_ns = np.log2(ns)
    target_log_n = np.log2(float(N))

    if target_log_n < log_ns.min() or target_log_n > log_ns.max():
        warnings.warn(
            f"N={N:,} outside measured join cardinality range "
            f"[{int(ns.min()):,}, {int(ns.max()):,}]; "
            "using endpoint."
        )

    # Interpolate in log-cardinality space.
    return float(np.interp(target_log_n, log_ns, times))


# ============================================================
# 5. FIGURE 12: ISOLATED JOIN PERFORMANCE
# ============================================================

fig, ax = plt.subplots(figsize=(10, 6))

# Radix join: thin lines.
for N, group in radix_join_summary.groupby("N"):
    group = group.sort_values("B")

    ax.plot(
        group["B"],
        group["elapsed_ms"],
        linewidth=1.0,
        marker="o",
        markersize=3,
        label=f"Radix N={int(N):,}",
    )

# Partitioned hash join: thick lines.
for N, group in phash_join_summary.groupby("N"):
    group = group.sort_values("B")

    ax.plot(
        group["B"],
        group["elapsed_ms"],
        linewidth=2.4,
        marker="s",
        markersize=3,
        label=f"Phash N={int(N):,}",
    )

ax.set_yscale("log")
ax.set_xlabel("Number of radix bits (B)")
ax.set_ylabel("Join time (milliseconds)")
ax.set_title("Figure 12 — Isolated Join Performance")
ax.legend(fontsize=7, ncol=2)
fig.tight_layout()

fig.savefig(OUT / "figure12_isolated_join.png", dpi=300)
fig.savefig(OUT / "figure12_isolated_join.pdf")
plt.close(fig)


# ============================================================
# 6. FIGURE 13 STRATEGY DEFINITIONS
# ============================================================

def safe_log2(value):
    if value <= 0:
        raise ValueError(f"log2 input must be positive: {value}")
    return max(0.0, float(np.log2(value)))


def strategy_bits(strategy, N):
    """
    Calculate the B value prescribed by each strategy
    in Section 3.4.4.
    """
    C = float(N)

    if strategy == "phash L2":
        return safe_log2(
            C * INNER_TUPLE_BYTES / L2_BYTES
        )

    if strategy == "phash TLB":
        tlb_bytes = TLB_ENTRIES * PAGE_BYTES
        return safe_log2(
            C * INNER_TUPLE_BYTES / tlb_bytes
        )

    if strategy == "phash L1":
        return safe_log2(
            C * INNER_TUPLE_BYTES / L1_BYTES
        )

    if strategy == "phash 256":
        return safe_log2(C / TARGET_PHASH_CLUSTER)

    if strategy == "phash min":
        return safe_log2(C / OPTIMAL_PHASH_CLUSTER)

    if strategy == "radix 8":
        return safe_log2(C / TARGET_RADIX_CLUSTER)

    if strategy == "radix min":
        return safe_log2(C / OPTIMAL_RADIX_CLUSTER)

    raise ValueError(f"Unknown strategy: {strategy}")


STRATEGIES = {
    "phash L2": "phash",
    "phash TLB": "phash",
    "phash L1": "phash",
    "phash 256": "phash",
    "phash min": "phash",
    "radix 8": "radix",
    "radix min": "radix",
}


# ============================================================
# 7. CLUSTERING COST ESTIMATE
# ============================================================

def cluster_time_reference(B):
    """
    Get the measured clustering time at reference N=8M.

    We select the optimal P for the nearest measured B.
    The time is interpolated between measured B values using
    the selected P at each measured B.

    This is a measured-data estimate, not the paper's complete
    analytical Tc(P,B,C) model.
    """
    selected_rows = []

    for _, row in best_passes.iterrows():
        selected_rows.append({
            "B": float(row["B"]),
            "time_ms": float(row["cluster_ms_at_reference_N"]),
        })

    selected = pd.DataFrame(selected_rows).sort_values("B")

    return float(np.interp(
        B,
        selected["B"].to_numpy(),
        selected["time_ms"].to_numpy(),
    ))


def estimated_cluster_time(N, B):
    """
    Approximation for cardinalities other than 8M:

        Tc(N,B) ~= Tc(8M,B) * N / 8M

    This linear scaling is an explicit approximation.
    The paper's Tc model is more detailed and accounts for
    cache and TLB effects as cardinality changes.
    """
    reference_ms = cluster_time_reference(B)
    return reference_ms * (float(N) / CLUSTER_REFERENCE_N)


# ============================================================
# 8. CALCULATE FIGURE 13 STRATEGY COSTS
# ============================================================

records = []

for N in FIG13_CARDINALITIES:
    for strategy, algorithm in STRATEGIES.items():

        B = strategy_bits(strategy, N)

        if algorithm == "phash":
            join_ms = join_time_at(
                phash_join_summary, N, B
            )
        else:
            join_ms = join_time_at(
                radix_join_summary, N, B
            )

        cluster_B = float(B)
        cluster_ms = estimated_cluster_time(N, cluster_B)

        P = optimal_P_for_B(cluster_B)

        total_ms = cluster_ms + join_ms

        records.append({
            "N": N,
            "strategy": strategy,
            "algorithm": algorithm,
            "B_calculated": B,
            "B_used_for_cluster_estimate": cluster_B,
            "optimal_P_nearest_measured_B": P,
            "cluster_ms_estimated": cluster_ms,
            "join_ms_interpolated": join_ms,
            "overall_ms_estimated": total_ms,
        })


fig13_data = pd.DataFrame(records)

fig13_data.to_csv(
    OUT / "figure13_strategy_costs.csv",
    index=False
)


# ============================================================
# 9. FIGURE 13 PLOT
# ============================================================

fig, ax = plt.subplots(figsize=(10, 6))

for strategy in STRATEGIES:
    group = fig13_data[
        fig13_data["strategy"] == strategy
    ].sort_values("N")

    ax.plot(
        group["N"],
        group["overall_ms_estimated"],
        marker="o",
        linewidth=1.8,
        label=strategy,
    )

ax.set_xscale("log", base=2)
ax.set_yscale("log")
ax.set_xlabel("Relation cardinality (tuples)")
ax.set_ylabel("Estimated overall time (milliseconds)")
ax.set_title(
    "Figure 13 — Overall Algorithm Comparison\n"
    "(linear scaling estimate for clustering cost)"
)

ax.set_xticks(FIG13_CARDINALITIES)
ax.set_xticklabels(
    [f"{n:,}" for n in FIG13_CARDINALITIES],
    rotation=30,
    ha="right",
)

ax.legend(fontsize=8)
fig.tight_layout()

fig.savefig(OUT / "figure13_overall_join.png", dpi=300)
fig.savefig(OUT / "figure13_overall_join.pdf")
plt.close(fig)


# ============================================================
# 10. EXPORT FIGURE 12 DATA AND SUMMARY
# ============================================================

radix_join_summary.to_csv(
    OUT / "figure12_radix_join_data.csv",
    index=False
)

phash_join_summary.to_csv(
    OUT / "figure12_phash_join_data.csv",
    index=False
)

print("\nGenerated output files:")
for path in sorted(OUT.iterdir()):
    print(" -", path.name)

print("\nFigure 13 strategy costs:")
print(
    fig13_data[
        [
            "N",
            "strategy",
            "B_calculated",
            "optimal_P_nearest_measured_B",
            "cluster_ms_estimated",
            "join_ms_interpolated",
            "overall_ms_estimated",
        ]
    ].to_string(index=False)
)

print("\nDone.")
