
import re
import statistics
import matplotlib.pyplot as plt

INPUT_FILE = "updated_strides.txt"
OUTPUT_FILE = "stride_vs_time.png"

# Store timings for each stride
results = {}

current_stride = None

# Extract stride and trial timings from benchmark output
with open(INPUT_FILE, "r") as file:
    for line in file:

        stride_match = re.search(r"Testing stride:\s*(\d+)\s*bytes", line)

        if stride_match:
            current_stride = int(stride_match.group(1))
            results[current_stride] = []
            continue

        time_match = re.search(
            r"Run\s+\d+:\s*([\d.]+)\s*ms\s*\(average of",
            line
        )

        if time_match and current_stride is not None:
            results[current_stride].append(float(time_match.group(1)))

# Validate extracted data
if not results or any(not times for times in results.values()):
    raise ValueError("Could not find benchmark timings. Check the input file format.")

# Calculate mean and standard deviation
strides = sorted(results.keys())
means = []
std_devs = []

for stride in strides:
    times = results[stride]

    means.append(statistics.mean(times))
    std_devs.append(statistics.stdev(times) if len(times) > 1 else 0)

# Generate graph
plt.figure(figsize=(10, 6))

plt.errorbar(
    strides,
    means,
    yerr=std_devs,
    marker="o",
    capsize=5,
    linewidth=2
)

plt.xscale("log", base=2)
plt.xticks(strides, strides)

plt.xlabel("Stride (bytes)")
plt.ylabel("Average Execution Time (ms)")
plt.title("Memory Access Time vs Stride")

plt.grid(True, alpha=0.3)
plt.tight_layout()

plt.savefig(OUTPUT_FILE, dpi=300)
plt.show()

print("\nResults:")
for stride, mean, std in zip(strides, means, std_devs):
    print(f"Stride {stride:3d}: {mean:.6f} ms (std dev: {std:.6f} ms)")

print(f"\nGraph saved as {OUTPUT_FILE}")
