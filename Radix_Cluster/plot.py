
import pandas as pd
import matplotlib.pyplot as plt
import os

os.makedirs("results/plots", exist_ok=True)

df = pd.read_csv("results/radix_cluster.csv")

# Calculate median execution time for every configuration.
summary = (
    df.groupby(["B", "P"])["time_ms"]
    .median()
    .reset_index()
)

plt.figure(figsize=(10, 6))

for p in sorted(summary["P"].unique()):

    subset = summary[summary["P"] == p]

    plt.plot(
        subset["B"],
        subset["time_ms"],
        marker="o",
        label=f"{p} Passes"
    )

plt.xlabel("Number of Clustering Bits (B)")
plt.ylabel("Execution Time (ms)")
plt.title("Radix Cluster: Execution Time vs Number of Bits")

plt.xticks(range(10, 28))
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    "results/plots/radix_cluster_time.png",
    dpi=300
)

plt.show()
