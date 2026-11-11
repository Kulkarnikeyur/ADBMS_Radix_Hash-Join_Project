"""
scripts/plot.py — generate all figures for the Radix Hash-Join project report.
Run from the project root:   python3 scripts/plot.py
Outputs PNGs into ./plots/
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --------------------------------------------------------------------
# global style
# --------------------------------------------------------------------
plt.rcParams.update({
    "font.size": 10,
    "figure.dpi": 130,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
})

os.makedirs("plots", exist_ok=True)


# ====================================================================
# PLOT 1 — Strided scan (paper Fig. 3 analog)
# ====================================================================
def plot_scan():
    df = pd.read_csv("results/scan.csv")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.loglog(df.stride_bytes, df.ns_per_access,
              marker="o", lw=1.8, ms=7, color="C0")

    # cache-line reference markers (i5-10310U: L1=64 B, L2=128 B, L3≈64 KB)
    for x, ls, label in [(64, "--", "L1 line\n(64 B)"),
                         (128, ":", "L2 line\n(128 B)"),
                         (64 * 1024, "-.", "L3 line\n(~64 KB)")]:
        ax.axvline(x, ls=ls, color="grey", alpha=0.6)
        ax.text(x, df.ns_per_access.min() * 1.15, " " + label,
                fontsize=8, va="bottom")

    ax.set_xlabel("stride (bytes)")
    ax.set_ylabel("ns per access")
    ax.set_title("Strided scan: latency vs stride "
                 "(i5-10310U; L1 32 KB / L2 1 MB / L3 6 MB)")
    plt.tight_layout()
    plt.savefig("plots/01_scan.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 2 — Radix partition: B vs P with TLB-thrash annotation (paper Fig. 9)
# ====================================================================
def plot_partition():
    df = pd.read_csv("results/partition.csv")

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for P, g in df.groupby("P"):
        ax.plot(g.B, g.time_ms, marker="o", lw=1.8, label=f"P = {P}")

    # TLB cliff annotation — this is the paper's central partition argument
    ax.axvline(18, ls="--", color="red", alpha=0.45)
    ax.annotate(
        "TLB thrashing:\n2^20 buckets > TLB entries\n→ 3× slowdown",
        xy=(20, 1487), xytext=(10, 1250),
        arrowprops=dict(arrowstyle="->", color="red", lw=1.2),
        color="red", fontsize=9,
    )
    ax.annotate(
        "multi-pass pays off\npast B ≈ 18",
        xy=(18, 670), xytext=(5, 950),
        arrowprops=dict(arrowstyle="->", color="darkblue", lw=1.2),
        color="darkblue", fontsize=9,
    )

    ax.set_xlabel("radix bits B")
    ax.set_ylabel("partition time (ms)")
    ax.set_title("Radix partition (8 M tuples): 1 pass is fine until B ≈ 18, "
                 "then TLB-thrash")
    ax.legend(title="passes", loc="center right")
    plt.tight_layout()
    plt.savefig("plots/02_partition.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 3 — Partition normalized (ns/tuple) — supplementary
# ====================================================================
def plot_partition_normalized():
    df = pd.read_csv("results/partition.csv")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for P, g in df.groupby("P"):
        ax.plot(g.B, g.ns_per_tuple, marker="o", lw=1.8, label=f"P = {P}")

    ax.set_xlabel("radix bits B")
    ax.set_ylabel("ns per tuple (partition phase)")
    ax.set_title("Partition cost normalized by input size")
    ax.legend(title="passes")
    plt.tight_layout()
    plt.savefig("plots/03_partition_normalized.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 4 — Join: per-algorithm time vs cardinality (paper Fig. 13 analog)
# ====================================================================
def plot_join():
    df = pd.read_csv("results/join.csv")
    best = df.loc[df.groupby(["cardinality", "algorithm"]).total_ms.idxmin()]

    markers = {"simple": "s", "phash_L2": "o", "phash_L3": "^",
               "phash_L1": "D", "radix_opt": "v"}
    colors  = {"simple": "black", "phash_L2": "C0", "phash_L3": "C2",
               "phash_L1": "C1", "radix_opt": "C3"}

    fig, ax = plt.subplots(figsize=(7.5, 5))
    for algo, g in best.groupby("algorithm"):
        g = g.sort_values("cardinality")
        ax.loglog(g.cardinality, g.total_ms,
                  marker=markers.get(algo, "o"), lw=1.8, ms=8,
                  color=colors.get(algo, "C4"),
                  label=algo)
    ax.set_xlabel("cardinality C (# tuples per side)")
    ax.set_ylabel("total join time (ms)")
    ax.set_title("Join time vs cardinality — all algorithms (log-log)")
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig("plots/04_join.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 5 — Join phase breakdown (partition / build / probe)
# ====================================================================
def plot_join_phases():
    df = pd.read_csv("results/join.csv")
    df = df[df.algorithm != "simple"]     # simple has no phases

    cards = sorted(df.cardinality.unique())
    algos = ["phash_L2", "phash_L3", "phash_L1", "radix_opt"]

    fig, axes = plt.subplots(1, len(cards), figsize=(15, 4), sharey=True)
    for ax, C in zip(axes, cards):
        sub = df[df.cardinality == C]
        x = np.arange(len(algos))
        part, build, probe = [], [], []
        for a in algos:
            row = sub[sub.algorithm == a]
            if len(row):
                part.append(row.partition_ms.iloc[0])
                build.append(row.build_ms.iloc[0])
                probe.append(row.probe_ms.iloc[0])
            else:
                part.append(0); build.append(0); probe.append(0)
        ax.bar(x - 0.25, part,  width=0.25, label="partition")
        ax.bar(x,        build, width=0.25, label="build")
        ax.bar(x + 0.25, probe, width=0.25, label="probe")
        ax.set_xticks(x)
        ax.set_xticklabels(algos, rotation=30, ha="right", fontsize=8)
        ax.set_title(f"C = {C:,}")

    axes[0].set_ylabel("ms")
    axes[0].legend(fontsize=8)
    plt.tight_layout()
    plt.savefig("plots/05_join_phases.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 6 — Best cache-conscious join vs simple hash (headline speedup)
# ====================================================================
def plot_join_speedup():
    df = pd.read_csv("results/join.csv")
    cache_df = df[df.algorithm != "simple"]
    best = cache_df.loc[cache_df.groupby("cardinality").total_ms.idxmin()]
    simple = df[df.algorithm == "simple"].set_index("cardinality")["total_ms"]

    merged = best.set_index("cardinality").join(simple.rename("simple_ms"))
    merged["speedup"] = merged.simple_ms / merged.total_ms

    fig, ax = plt.subplots(figsize=(7, 4.3))
    bars = ax.bar([f"{c:,}" for c in merged.index], merged.speedup,
                  color="C2", edgecolor="black")
    for bar, val in zip(bars, merged.speedup):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.05,
                f"{val:.2f}×", ha="center", fontsize=10, fontweight="bold")
    ax.axhline(1.0, ls="--", color="black", alpha=0.5)
    ax.set_xlabel("cardinality")
    ax.set_ylabel("speedup over simple hash join")
    ax.set_title("Best cache-conscious join vs simple hash join\n"
                 "(speedup grows with cardinality — paper's headline result)")
    ax.set_ylim(0, merged.speedup.max() * 1.2)
    plt.tight_layout()
    plt.savefig("plots/06_join_speedup.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# PLOT 7 — Parallel: per-phase time + Amdahl speedup with partition-only line
# ====================================================================
def plot_parallel():
    df = pd.read_csv("results/parallel.csv")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.3))

    # ---- left: per-phase bars ----
    x = np.arange(len(df)); w = 0.25
    ax1.bar(x - w, df.partition_ms, width=w, label="partition", color="C0")
    ax1.bar(x,     df.build_ms,     width=w, label="build",     color="C1")
    ax1.bar(x + w, df.probe_ms,     width=w, label="probe",     color="C2")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"T={t}" for t in df.threads])
    ax1.set_ylabel("ms")
    ax1.set_title("Per-phase time by thread count (C = 16 M)")
    ax1.legend()
    ax1.grid(True, axis="y", alpha=0.3)

    # ---- right: speedup (total vs partition-only vs ideal) ----
    t1_total = df.total_ms.iloc[0]
    t1_part  = df.partition_ms.iloc[0]
    ax2.plot(df.threads, t1_total / df.total_ms,
             marker="o", lw=2, ms=8, label="total speedup")
    ax2.plot(df.threads, t1_part / df.partition_ms,
             marker="s", lw=2, ms=8, label="partition-only speedup")
    ax2.plot(df.threads, df.threads, "--", color="grey", alpha=0.5, label="ideal")
    ax2.set_xlabel("threads")
    ax2.set_ylabel("speedup vs T=1")
    ax2.set_title("Amdahl: only partition is parallel")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # annotate the total speedup at T=4
    last_total = t1_total / df.total_ms.iloc[-1]
    ax2.annotate(f"{last_total:.2f}×",
                 xy=(df.threads.iloc[-1], last_total),
                 xytext=(df.threads.iloc[-1] - 0.5, last_total + 0.25),
                 fontsize=10, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color="black", lw=1))

    plt.tight_layout()
    plt.savefig("plots/07_parallel.png", bbox_inches="tight")
    plt.close()


# ====================================================================
# main
# ====================================================================
if __name__ == "__main__":
    plot_scan()
    plot_partition()
    plot_partition_normalized()
    plot_join()
    plot_join_phases()
    plot_join_speedup()
    plot_parallel()

    print("All plots written to ./plots/")
    for f in sorted(os.listdir("plots")):
        print(f"  {f}")