
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("counters.csv")

metrics = [
    ("L1_misses", "L1 Data Cache Misses"),
    ("L2_misses", "L2 Demand Data-Read Misses"),
    ("TLB_misses", "DTLB Load + Store Misses"),
]

for column, title in metrics:
    plt.figure(figsize=(9, 5))

    for p in sorted(df["P"].unique()):
        subset = df[df["P"] == p].sort_values("B")

        plt.plot(
            subset["B"],
            subset[column],
            marker="o",
            label=f"{p} pass{'es' if p > 1 else ''}"
        )

    plt.xlabel("Number of bits (B)")
    plt.ylabel("Number of misses")
    plt.title(title)
    plt.xticks(range(1, 25))
    plt.yscale("log")
    plt.grid(True, which="both", linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()

    plt.savefig(f"{column}.png", dpi=300)
    plt.show()
