
import pandas as pd
import matplotlib.pyplot as plt
import os

os.makedirs("plots", exist_ok=True)

# ==========================================
# 1. SELECTION
# ==========================================

df = pd.read_csv("results/selection.csv")

df["Selectivity"] = df["Algorithm"].str.extract(
    r"(\d+)pct"
).astype(float)

df["Method"] = df["Algorithm"].str.extract(
    r"(Scan_Select|Sorted_Index)"
)

for n in sorted(df["N"].unique()):

    subset = df[df["N"] == n]

    plt.figure(figsize=(9, 5))

    for method in subset["Method"].unique():

        data = subset[subset["Method"] == method]

        plt.plot(
            data["Selectivity"],
            data["Time_ms"],
            marker="o",
            label=method
        )

    plt.xlabel("Selectivity (%)")
    plt.ylabel("Execution Time (ms)")
    plt.title(f"Selection Algorithms (N={n})")
    plt.legend()
    plt.grid(True)

    plt.savefig(f"plots/selection_{n}.png")
    plt.close()


# ==========================================
# 2. GROUPING
# ==========================================

df = pd.read_csv("results/grouping.csv")

plt.figure(figsize=(9, 5))

for algorithm in df["Algorithm"].unique():

    data = df[df["Algorithm"] == algorithm]

    plt.plot(
        data["N"],
        data["Time_ms"],
        marker="o",
        label=algorithm
    )

plt.xlabel("Number of Tuples")
plt.ylabel("Execution Time (ms)")
plt.title("Hash Grouping vs Sort/Merge Grouping")
plt.legend()
plt.grid(True)

plt.savefig("plots/grouping.png")
plt.close()


# ==========================================
# 3. EQUI-JOIN
# ==========================================

df = pd.read_csv("results/join.csv")

plt.figure(figsize=(9, 5))

for algorithm in df["Algorithm"].unique():

    data = df[df["Algorithm"] == algorithm]

    plt.plot(
        data["N"],
        data["Time_ms"],
        marker="o",
        label=algorithm
    )

plt.xlabel("Relation Cardinality")
plt.ylabel("Execution Time (ms)")
plt.title("Hash Join vs Sort-Merge Join")
plt.legend()
plt.grid(True)

plt.savefig("plots/join.png")
plt.close()

print("All graphs generated successfully!")
