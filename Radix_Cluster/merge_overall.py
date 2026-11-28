import os
import csv
import re
import glob

# Configuration
INPUT_DIR = "results_overall/perf_results"
OUTPUT_FILE = "results_overall/radix_cluster_counters.csv"

# Regex to extract N, B, and P from filenames like "N125000_B24_P3.csv"
filename_pattern = re.compile(r"N(\d+)_B(\d+)_P(\d+)\.csv")

all_data = []

# Find all CSV files in the directory
csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))

if not csv_files:
    print(f"No CSV files found in '{INPUT_DIR}'.")
else:
    for filepath in csv_files:
        filename = os.path.basename(filepath)
        match = filename_pattern.match(filename)
        
        if not match:
            print(f"Skipping unrecognized file: {filename}")
            continue
            
        N, B, P = match.groups()
        
        # Default time if we don't find it
        time_ms = ""
        
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip empty rows or perf comment/header lines
                if not row or row[0].startswith('#'):
                    continue
                
                # Depending on how perf was run, the elapsed time might be a specific event
                # or it might just be the raw output of your program. 
                # Assuming your program outputs "time_ms" as the event name, or it's hardcoded:
                if len(row) >= 3 and row[2].strip() == "time_ms":
                    time_ms = row[0].strip()
                
                # Fallback: If the perf file only contains standard hardware counters, 
                # you might need to extract the time differently depending on your setup.
                
        # Create one single row per file
        # N, B, P, bits_per_pass, run, time_ms
        # We assume bits_per_pass = B and run = 1 (or you can define these however needed)
        new_row = [N, B, P, B, 1, time_ms]
        all_data.append(new_row)

    # Write the merged data
    if all_data:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Simple 6-column header
            header = ['N', 'B', 'P', 'bits_per_pass', 'run', 'time_ms']
            writer.writerow(header)
            
            # Write all collected rows
            writer.writerows(all_data)
            
        print(f"Successfully merged {len(csv_files)} files into {OUTPUT_FILE}")
        print(f"Total data rows: {len(all_data)}")
    else:
        print("No valid data found to merge.")