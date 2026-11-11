
import re
import csv
import argparse
from pathlib import Path

def generate_csv(input_file, output_file):
    # Matches stride headings such as:
    # Stride: 32
    # Stride = 32
    stride_pattern = re.compile(
        r"Stride\s*[:=]?\s*(\d+)", re.IGNORECASE
    )

    # Matches lines such as:
    # Run 1: 0.0091 ms (average of 10 scans)
    run_pattern = re.compile(
        r"Run\s+(\d+)\s*:\s*([\d.eE+-]+)\s*ms",
        re.IGNORECASE
    )

    rows = []
    current_stride = None

    with open(input_file, "r") as file:
        for line in file:
            stride_match = stride_pattern.search(line)

            if stride_match:
                current_stride = int(stride_match.group(1))
                continue

            run_match = run_pattern.search(line)

            if run_match and current_stride is not None:
                repetition = int(run_match.group(1))
                execution_time = float(run_match.group(2))

                rows.append({
                    "stride_bytes": current_stride,
                    "repetition": repetition,
                    "execution_time_ms": execution_time
                })

    if not rows:
        print("No measurements found. Check the TXT output format.")
        return

    with open(output_file, "w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "stride_bytes",
                "repetition",
                "execution_time_ms"
            ]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Successfully generated {output_file}")
    print(f"Total measurements: {len(rows)}")
    print(f"Strides found: {sorted(set(r['stride_bytes'] for r in rows))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input experiment TXT file")
    parser.add_argument(
        "-o", "--output",
        default="result.csv",
        help="Output CSV filename"
    )

    args = parser.parse_args()
    generate_csv(args.input, args.output)
