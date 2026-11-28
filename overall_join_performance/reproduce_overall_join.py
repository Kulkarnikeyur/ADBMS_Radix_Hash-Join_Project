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


def optimal_P_for_B(B, N=CLUSTER_REFERENCE_N):
    group = cluster_summary[
        (cluster_summary["N"] == N) &
        (cluster_summary["B"] == B)
    ]

    if group.empty:
        raise ValueError(
            f"No clustering measurements for N={N}, B={B}"
        )

    best_row = group.loc[group["median_cluster_ms"].idxmin()]
    return int(best_row["P"])

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



def interpolate_at_B(frame, B, value_col="elapsed_ms"):
    frame = frame.sort_values("B")

    x = frame["B"].to_numpy(dtype=float)
    y = frame[value_col].to_numpy(dtype=float)

    if len(x) == 0:
        raise ValueError("No measurements available.")

    if len(x) == 1:
        if not np.isclose(B, x[0]):
            raise ValueError(
                f"Cannot estimate B={B} from a single "
                f"measurement at B={x[0]}."
            )
        return float(y[0])

    if B < x.min() or B > x.max():
        raise ValueError(
            f"Cannot estimate B={B} from measured range "
            f"[{x.min()}, {x.max()}]."
        )

    return float(np.interp(B, x, y))



def join_time_at(df, N, B):
    n_values = np.sort(df["N"].unique().astype(float))

    # First check whether an exact cardinality exists.
    exact_N = n_values[np.isclose(n_values, N)]

    if len(exact_N) > 0:
        required_N = [exact_N[0]]

    # Otherwise, find the two surrounding cardinalities.
    elif N < n_values[0]:
        required_N = [n_values[0]]

    elif N > n_values[-1]:
        required_N = [n_values[-1]]

    else:
        idx = np.searchsorted(n_values, N)
        required_N = [n_values[idx - 1], n_values[idx]]

    times = []

    for measured_N in required_N:
        group = df[
            np.isclose(df["N"], measured_N)
        ]

        t = interpolate_at_B(group, B)

        times.append((float(measured_N), t))

    # Exact cardinality: no N interpolation needed.
    if len(times) == 1:
        return times[0][1]

    # Interpolate between cardinalities using log2(N).
    n_lo, t_lo = times[0]
    n_hi, t_hi = times[1]

    weight = (
        (np.log2(float(N)) - np.log2(n_lo))
        / (np.log2(n_hi) - np.log2(n_lo))
    )

    return float(t_lo + weight * (t_hi - t_lo))


# Fastest measured clustering time for each exact N,B.
cluster_best_by_NB = (
    cluster_summary
    .sort_values(["N", "B", "median_cluster_ms", "P"])
    .groupby(["N", "B"], as_index=False)
    .first()
    [["N", "B", "P", "median_cluster_ms"]]
)


def single_cluster_time_at(N, B):
    group = cluster_best_by_NB[
        cluster_best_by_NB["N"] == N
    ].sort_values("B")

    if group.empty:
        raise ValueError(
            f"No clustering measurements for N={N}"
        )

    return interpolate_at_B(
        group.rename(
            columns={"median_cluster_ms": "cluster_ms"}
        ),
        B,
        value_col="cluster_ms",
    )


def estimated_cluster_time(N, B):
    # Two relations are clustered.
    return 2.0 * single_cluster_time_at(N, B)


def total_time_at(join_df, N, B):
    join_ms = join_time_at(join_df, N, B)
    cluster_ms = estimated_cluster_time(N, B)

    return join_ms + cluster_ms


def optimal_P_for_B(B, N):
    group = cluster_summary[
        (cluster_summary["N"] == N) &
        (np.isclose(cluster_summary["B"], B))
    ]

    if group.empty:
        # For interpolated B, use the closest measured B to report P.
        measured_Bs = cluster_summary[
            cluster_summary["N"] == N
        ]["B"].unique()

        if len(measured_Bs) == 0:
            raise ValueError(
                f"No pass measurements for N={N}"
            )

        closest_B = measured_Bs[
            np.argmin(np.abs(measured_Bs - B))
        ]

        group = cluster_summary[
            (cluster_summary["N"] == N) &
            (cluster_summary["B"] == closest_B)
        ]

    return int(
        group.loc[group["median_cluster_ms"].idxmin(), "P"]
    )


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

def safe_log2(value):
    if value <= 0:
        raise ValueError(f"log2 input must be positive: {value}")
    return max(0.0, float(np.log2(value)))


# ============================================================
# 5. FIGURE 12: ISOLATED JOIN PERFORMANCE
# ============================================================

fig, ax = plt.subplots(figsize=(12, 8))

# Different line styles distinguish cardinalities.
cardinality_styles = {
    15625: ":",
    62500: "-.",
    250000: "--",
    1000000: "-",
    4000000: (0, (5, 2)),
    16000000: (0, (3, 1, 1, 1)),
    64000000: (0, (1, 1)),
}

# Markers represent the number of clustering passes.
pass_markers = {
    1: "+",
    2: "s",
    3: "s",
    4: "^",
}

# Plot Radix (thin) and Phash (thick) performance curves.
algorithms = [
    ("Radix", radix_join_summary, 1.0),
    ("Phash", phash_join_summary, 2.5),
]

for algorithm_name, join_df, linewidth in algorithms:

    for N, group in join_df.groupby("N"):
        group = group.sort_values("B").copy()

        # Calculate total time for each measured B.
        group["total_ms"] = [
            total_time_at(join_df, N, B)
            for B in group["B"]
        ]

        style = cardinality_styles.get(int(N), "-")

        ax.plot(
            group["B"],
            group["total_ms"],
            linestyle=style,
            linewidth=linewidth,
            color="black",
            zorder=2,
        )

        # Draw markers according to the optimal measured pass count.
        for _, row in group.iterrows():
            P = optimal_P_for_B(row["B"], N)

            marker = pass_markers.get(P, "o")

            if P == 3:
                markerfacecolor = "black"
            else:
                markerfacecolor = "none"

            ax.plot(
                row["B"],
                row["total_ms"],
                marker=marker,
                color="black",
                markerfacecolor=markerfacecolor,
                markersize=5,
                linestyle="none",
                zorder=3,
            )

        # Circle the minimum TOTAL time for this N and algorithm.
        min_row = group.loc[group["total_ms"].idxmin()]

        ax.scatter(
            min_row["B"],
            min_row["total_ms"],
            s=100,
            facecolors="none",
            edgecolors="black",
            linewidths=1.2,
            zorder=5,
        )


# -------------------------------------------------------
# Fixed strategy lines
# -------------------------------------------------------

fixed_strategies = {
    "phash L2": "phash",
    "phash TLB": "phash",
    "phash L1": "phash",
    "radix 8": "radix",
}

strategy_styles = {
    "phash L2": (0, (3, 2)),
    "phash TLB": (0, (5, 2)),
    "phash L1": (0, (1, 2)),
    "radix 8": (0, (6, 2, 1, 2)),
}

strategy_points = {}

for strategy, algorithm in fixed_strategies.items():

    join_df = (
        phash_join_summary
        if algorithm == "phash"
        else radix_join_summary
    )

    points = []

    for N in sorted(join_df["N"].unique()):

        # Calculate the strategy's selected number of bits.
        B = max(1, int(np.ceil(strategy_bits(strategy, N))))

        # Calculate total clustering + join time.
        total_ms = total_time_at(join_df, N, B)

        points.append((B, total_ms))

    strategy_points[strategy] = points

    points.sort(key=lambda p: p[0])

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    ax.plot(
        xs,
        ys,
        color="black",
        linestyle=strategy_styles[strategy],
        linewidth=0.8,
        alpha=0.9,
        zorder=1,
    )

    # Label the strategy near its rightmost point.
    if points:
        x, y = points[-1]

        ax.annotate(
            strategy,
            (x, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )


# -------------------------------------------------------
# Axes and formatting
# -------------------------------------------------------

ax.set_yscale("log")
ax.set_xlim(1, 25)

ax.set_xlabel("Number of bits")
ax.set_ylabel("Milliseconds")

ax.set_title(
    "Figure 12 — Overall Performance of Radix-Join "
    "vs. Partitioned Hash-Join"
)

ax.grid(
    True,
    which="both",
    linestyle=":",
    alpha=0.25,
)

fig.tight_layout()

fig.savefig(OUT / "figure12_total_join.png", dpi=300)
fig.savefig(OUT / "figure12_total_join.pdf")

plt.close(fig)

# ============================================================
# 6. FIGURE 13 STRATEGY DEFINITIONS
# ============================================================




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
    group = cluster_summary[
        (cluster_summary["N"] == N) &
        (cluster_summary["B"] == B)
    ]

    if group.empty:
        raise ValueError(
            f"No clustering measurements for N={N}, B={B}"
        )

    # Each P has a median time across its runs.
    # Select the fastest measured P for this exact N and B.
    best_row = group.loc[group["median_cluster_ms"].idxmin()]

    # Clustering is performed for both relations.
    return 2 * float(best_row["median_cluster_ms"])


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
        P = optimal_P_for_B(cluster_B, N)

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