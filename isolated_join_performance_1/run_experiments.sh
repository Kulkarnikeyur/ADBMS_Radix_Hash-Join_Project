
#!/bin/bash

set -u

OUT="results"

mkdir -p "$OUT"

# Clear previous experiment output.
rm -f "$OUT/results.csv"

echo "N,B,H,avg_cluster,comparisons,matches,elapsed_ms,checksum" \
    > "$OUT/results.csv"

# Five cardinalities used in Figure 10.
CARDINALITIES=(
    15625
    125000
    1000000
    8000000
    64000000
)

# Radix bits.
BITS=$(seq 1 25)

# Maximum estimated comparisons per experiment.
# Increase this if you want to include more expensive runs.
MAX_COMPARISONS=512000000
CPU=2    # check with taskset -pc $$
for N in "${CARDINALITIES[@]}"; do

    for B in $BITS; do

        H=$((1 << B))

        AVG=$(( (N + H - 1) / H ))

        EST=$(( N * AVG ))

        if (( EST > MAX_COMPARISONS )); then
            echo "SKIPPED N=$N B=$B estimated comparisons=$EST"
            continue
        fi

        echo ""
        echo "========================================"
        echo "Running N=$N B=$B H=$H"
        echo "Estimated comparisons: $EST"
        echo "========================================"

        CTL="$OUT/ctl_${N}_${B}"
        ACK="$OUT/ack_${N}_${B}"
        PERF="$OUT/perf_${N}_${B}.txt"

        rm -f "$CTL" "$ACK"
        mkfifo "$CTL" "$ACK" || { echo "mkfifo failed"; exit 1; }

        # Counters are enabled/disabled by the C++ program.
        timeout 900s perf stat \
            -D -1 \
            --no-big-num \
            -x, \
            -o "$PERF" \
            --control="fifo:$CTL,$ACK" \
            -e l1d.replacement \
            -e l2_rqsts.demand_data_rd_miss \
            -e dtlb_load_misses.stlb_hit \
            -e dtlb_load_misses.miss_causes_a_walk \
            -e dtlb_store_misses.stlb_hit \
            -e dtlb_store_misses.miss_causes_a_walk \
            -- taskset -c "$CPU" \
            ./join_bench "$N" "$B" "$CTL" "$ACK" \
            >> "$OUT/results.csv"

        STATUS=$?

        rm -f "$CTL" "$ACK"

        if (( STATUS != 0 )); then
            echo "WARNING: N=$N B=$B exited with status $STATUS"
        fi

    done
done

echo ""
echo "Experiments completed."
echo "Results: $OUT/results.csv"
echo "Perf counters: $OUT/perf_*.txt"
