import pandas as pd
import matplotlib.pyplot as plt

# Read benchmark results
df = pd.read_csv("results.csv")

# Calculate average execution time for each stride
averages = df.groupby("stride_bytes")["average_scan_time_ms"].mean()

# Calculate mean and standard deviation
stats = df.groupby("stride_bytes")["average_scan_time_ms"].agg(
    ["mean", "std"]
)

plt.figure(figsize=(9, 5))

plt.errorbar(
    stats.index,
    stats["mean"],
    yerr=stats["std"],
    marker="o",
    capsize=5,
    linewidth=2
)

plt.xscale("log", base=2)
plt.xticks(stats.index, stats.index)

plt.xlabel("Stride (bytes)")
plt.ylabel("Average Execution Time (ms)")
plt.title("Memory Access Time vs Stride")

plt.grid(True, alpha=0.3)
plt.tight_layout()

plt.savefig("stride_vs_time.png", dpi=300)
plt.show()