import csv
import os

RESULTS = "/home/keyur/ADBMS_project/isolated_join_performance/results/results.csv"
CLEAN   = "/home/keyur/ADBMS_project/isolated_join_performance/results/results_clean.csv"

if not os.path.exists(RESULTS):
    raise FileNotFoundError(f"Not found: {RESULTS}")

header = None
rows = []

with open(RESULTS, newline="") as f:
    reader = csv.reader(f)
    for raw in reader:
        if not raw:
            continue

        # First non-empty line is the header
        if header is None:
            header = raw
            continue

        # Data rows look like: RESULT,15625,1,2,...
        # Drop the leading "RESULT" tag so fields match the header
        if raw[0] == "RESULT":
            raw = raw[1:]

        # Keep only rows whose field count matches the header
        if len(raw) == len(header):
            rows.append(raw)
        else:
            print(f"Skipping non-data line: {raw}")

with open(CLEAN, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"Wrote {len(rows)} data rows to {CLEAN}")