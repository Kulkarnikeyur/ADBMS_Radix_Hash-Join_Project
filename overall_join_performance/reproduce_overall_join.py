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
RADIX_JOIN_FILE = BASE / "radix_join.csv"
PHASH_JOIN_FILE = BASE / "phash_join.csv"

OUT = BASE / "output"
OUT.mkdir(exist_ok=True)

# CLUSTER_REFERENCE_N is discovered from radix_cluster_overall.csv.
# Set PREFERRED_CLUSTER_REFERENCE_N to force a specific value; None
# means "use the largest N present in the clustering file".
PREFERRED_CLUSTER_REFERENCE_N = None

# Paper strategy parameters.
INNER_TUPLE_BYTES = 26
TARGET_PHASH_CLUSTER = 256
OPTIMAL_PHASH_CLUSTER = 200
OPTIMAL_RADIX_CLUSTER = 4
TARGET_RADIX_CLUSTER = 8

# Hardware parameters used to calculate the cache/TLB strategies.
L1_BYTES = 32 * 1024
L2_BYTES = 256 * 1024      # 256 KB per core
TLB_ENTRIES = 1536
PAGE_BYTES = 4 * 1024

# Populated after loading CSVs.
CLUSTER_REFERENCE_N = None
FIG13_CARDINALITIES = None

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

    data_rows = rows[1:]
    normalized = []

    for row in data_rows:
        row = [x.strip() for x in row]

        if not row or all(x == "" for x in row):
            continue

        if len(row) == 9:
            normalized.append(row)
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

    missing = [c for c in required_columns if c not in data.columns]
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
    ["N", "B", "P", "run", "time_ms"]
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
# 1b. DISCOVER REFERENCE CARDINALITY AND FIGURE 13 SET
# ============================================================

cluster_cardinalities = sorted(
    int(n) for n in radix_cluster["N"].unique()
)
if not cluster_cardinalities:
    raise ValueError("radix_cluster.csv contains no N values.")

if PREFERRED_CLUSTER_REFERENCE_N is not None:
    if PREFERRED_CLUSTER_REFERENCE_N not in cluster_cardinalities:
        raise ValueError(
            f"PREFERRED_CLUSTER_REFERENCE_N="
            f"{PREFERRED_CLUSTER_REFERENCE_N:,} is not present in "
            f"radix_cluster_overall.csv. Available N values: "
            f"{cluster_cardinalities}"
        )
    CLUSTER_REFERENCE_N = PREFERRED_CLUSTER_REFERENCE_N
else:
    CLUSTER_REFERENCE_N = cluster_cardinalities[-1]

print(
    f"\nUsing CLUSTER_REFERENCE_N = {CLUSTER_REFERENCE_N:,} "
    f"(available: {cluster_cardinalities})"
)

# Figure 13: use cardinalities measured by both join files.
join_cardinalities = sorted(
    set(int(n) for n in radix_join["N"].unique())
    & set(int(n) for n in phash_join["N"].unique())
)
if not join_cardinalities:
    join_cardinalities = sorted(
        set(int(n) for n in radix_join["N"].unique())
        | set(int(n) for n in phash_join["N"].unique())
    )
    warnings.warn(
        "radix_join.csv and phash_join.csv share no N values; "
        "using the union for Figure 13."
    )

FIG13_CARDINALITIES = join_cardinalities
print(f"Figure 13 cardinalities: {FIG13_CARDINALITIES}")


# ============================================================
# 2. SELECT OPTIMAL RADIX CLUSTERING PASSES
# ============================================================

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
    # This should never happen now, but keep a clear guard.
    raise ValueError(
        f"No radix clustering rows found for "
        f"N={CLUSTER_REFERENCE_N:,}. "
        f"Available N: {cluster_cardinalities}"
    )

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
    values = best_passes["B"].to_numpy()
    return int(values[np.argmin(np.abs(values - B))])


def optimal_P_for_B(B):
    measured_B = nearest_measured_B(B)
    row = best_passes[best_passes["B"] == measured_B].iloc[0]
    return int(row["optimal_P"])


# ============================================================
# 3. PREPARE JOIN-ONLY MEASUREMENTS
# ============================================================

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
    frame = frame.sort_values("B")

    x = frame["B"].to_numpy(dtype=float)
    y = frame["elapsed_ms"].to_numpy(dtype=float)

    if len(x) == 1:
        if not np.isclose(B, x[0]):
            raise ValueError(
                f"Cannot estimate B={B} from a single "
                f"measurement at B={x[0]}"
            )
        return float(y[0])

    # Reject extrapolation instead of silently clamping.
    if B < x.min() or B > x.max():
        raise ValueError(
            f"Cannot estimate B={B} from measured range "
            f"[{x.min()}, {x.max()}]. "
            "Run the missing experiment or revise the strategy."
        )

    return float(np.interp(B, x, y))


def join_time_at(df, N, B):
    n_values = np.sort(df["N"].unique().astype(float))

    # Find the cardinality or the two cardinalities surrounding N.
    if N <= n_values[0]:
        n_lo = n_hi = n_values[0]
    elif N >= n_values[-1]:
        n_lo = n_hi = n_values[-1]
    else:
        idx = np.searchsorted(n_values, N)
        n_lo = n_values[idx - 1]
        n_hi = n_values[idx]

    lower_group = df[df["N"] == n_lo]
    upper_group = df[df["N"] == n_hi]

    # Interpolate B only for the required cardinalities.
    t_lo = interpolate_at_B(lower_group, B)

    if n_lo == n_hi:
        return t_lo

    t_hi = interpolate_at_B(upper_group, B)

    # Interpolate between cardinalities in log2(N) space.
    weight = (
        (np.log2(N) - np.log2(n_lo))
        / (np.log2(n_hi) - np.log2(n_lo))
    )

    return float(t_lo + weight * (t_hi - t_lo))


# ============================================================
# 5. FIGURE 12: ISOLATED JOIN PERFORMANCE
# ============================================================

fig, ax = plt.subplots(figsize=(12, 7))

all_summaries = [
    ("Radix", radix_join_summary, "-", "o", 1.2),
    ("Phash", phash_join_summary, "--", "s", 2.0),
]

for strategy, summary, linestyle, marker, linewidth in all_summaries:

    for N, group in summary.groupby("N"):

        group = group.sort_values("B")

        line, = ax.plot(
            group["B"],
            group["elapsed_ms"],
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=5,
            label=f"{strategy} N={int(N):,}",
        )

        color = line.get_color()

        # ----------------------------------------------------
        # Annotate every point with the optimal pass count.
        # P is obtained from radix_cluster.csv through best_passes.
        # ----------------------------------------------------

        for point_number, (_, row) in enumerate(group.iterrows()):

            passes = optimal_P_for_B(row["B"])

            # Alternate annotation positions to reduce overlap.
            offset = 9 if point_number % 2 == 0 else -13

            ax.annotate(
                f"P={passes}",
                (row["B"], row["elapsed_ms"]),
                textcoords="offset points",
                xytext=(0, offset),
                ha="center",
                fontsize=7,
                color=color,
            )

        # ----------------------------------------------------
        # Circle the minimum join time for each N and strategy.
        # ----------------------------------------------------

        min_idx = group["elapsed_ms"].idxmin()
        min_row = group.loc[min_idx]

        ax.scatter(
            min_row["B"],
            min_row["elapsed_ms"],
            s=180,
            facecolors="none",
            edgecolors=color,
            linewidths=2.0,
            zorder=6,
        )

# ------------------------------------------------------------
# Axes and formatting
# ------------------------------------------------------------

ax.set_yscale("log")

ax.set_xlabel("Number of radix bits (B)")
ax.set_ylabel("Total isolated join time (milliseconds)")

ax.set_title("Figure 12 — Isolated Join Performance")

ax.grid(
    True,
    which="both",
    linestyle=":",
    alpha=0.3,
)

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
    C = float(N)

    if strategy == "phash L2":
        return safe_log2(C * INNER_TUPLE_BYTES / L2_BYTES)
    if strategy == "phash TLB":
        tlb_bytes = TLB_ENTRIES * PAGE_BYTES
        return safe_log2(C * INNER_TUPLE_BYTES / tlb_bytes)
    if strategy == "phash L1":
        return safe_log2(C * INNER_TUPLE_BYTES / L1_BYTES)
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
    Measured clustering time at the discovered reference N,
    interpolated across the measured B values.
    """
    selected = best_passes[["B", "cluster_ms_at_reference_N"]] \
        .rename(columns={"cluster_ms_at_reference_N": "time_ms"}) \
        .sort_values("B")

    return float(np.interp(
        B,
        selected["B"].to_numpy(dtype=float),
        selected["time_ms"].to_numpy(dtype=float),
    ))


def estimated_cluster_time(N, B):
    """
    Estimated clustering cost for BOTH relations in the join.

    Each relation has the same size and distribution, so:
    Tc_join(N,B) = 2 * Tc_single(N,B)
    """
    reference_ms = cluster_time_reference(B)

    single_cluster_ms = (
        reference_ms * (float(N) / float(CLUSTER_REFERENCE_N))
    )

    return 2 * single_cluster_ms

def find_best_B(N, algorithm):
    if algorithm == "phash":
        join_df = phash_join_summary
    elif algorithm == "radix":
        join_df = radix_join_summary
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    n_values = np.sort(join_df["N"].unique().astype(float))

    # Find the cardinality or the two cardinalities surrounding N.
    if N <= n_values[0]:
        required_N = [n_values[0]]
    elif N >= n_values[-1]:
        required_N = [n_values[-1]]
    else:
        idx = np.searchsorted(n_values, N)
        required_N = [n_values[idx - 1], n_values[idx]]

    # Find the B range supported by every required cardinality.
    required_groups = [
        join_df[join_df["N"] == n]
        for n in required_N
    ]

    min_B = max(group["B"].min() for group in required_groups)
    max_B = min(group["B"].max() for group in required_groups)

    # Consider only measured B values inside the common range.
    candidate_Bs = sorted(
        b for b in join_df["B"].unique()
        if min_B <= b <= max_B
    )

    if not candidate_Bs:
        raise ValueError(
            f"No common measured B range for N={N}, "
            f"algorithm={algorithm}. "
            f"Required cardinalities: {required_N}, "
            f"common B range: [{min_B}, {max_B}]."
        )

    best_B = None
    best_total = float("inf")

    for B in candidate_Bs:
        join_ms = join_time_at(join_df, N, B)
        cluster_ms = estimated_cluster_time(N, B)
        total_ms = cluster_ms + join_ms

        if total_ms < best_total:
            best_total = total_ms
            best_B = B

    return float(best_B)


# ============================================================
# 8. CALCULATE FIGURE 13 STRATEGY COSTS
# ============================================================

records = []

for N in FIG13_CARDINALITIES:
    for strategy, algorithm in STRATEGIES.items():

        if strategy in ("phash min", "radix min"):
            B = find_best_B(N, algorithm)
        else:
            B = strategy_bits(strategy, N)

        # B must be an integer.
        # Round up so the required number of clusters fits.
        # If negative, use 0 (no clustering required).
        B = max(1, int(np.ceil(B)))

        if algorithm == "phash":
            join_ms = join_time_at(phash_join_summary, N, B)
        else:
            join_ms = join_time_at(radix_join_summary, N, B)

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
    f"(clustering reference N = {CLUSTER_REFERENCE_N:,}; "
    "linear scaling estimate)"
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
