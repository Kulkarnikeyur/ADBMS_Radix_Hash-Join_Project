
#!/bin/bash

set -u

mkdir -p results

rm -f results/results.csv

echo "N,B,H,avg_cluster,clusters,hash_probes,matches,elapsed_ms,checksum" \
    > results/results.csv

CARDINALITIES=(
    15625
    125000
    1000000
    8000000
    64000000
)

BITS=$(seq 5 25)

for N in "${CARDINALITIES[@]}"; do

    for B in $BITS; do

        H=$((1 << B))

        echo ""
        echo "====================================="
        echo "Partitioned Hash Join"
        echo "N=$N B=$B H=$H"
        echo "Average cluster size: $((N / H))"
        echo "====================================="

        CTL="results/ctl_${N}_${B}"
        PERF="results/perf_${N}_${B}.txt"

        rm -f "$CTL"
        mkfifo "$CTL"

        timeout 900s perf stat \
            --no-big-num \
            -x, \
            -o "$PERF" \
            --control="fifo:$CTL" \
            -e l1d.replacement \
            -e l2_rqsts.demand_data_rd_miss \
            -e dtlb_load_misses.stlb_hit \
            -e dtlb_load_misses.miss_causes_a_walk \
            -e dtlb_store_misses.stlb_hit \
            -e dtlb_store_misses.miss_causes_a_walk \
            -- ./hash_join "$N" "$B" "$CTL" \
            >> results/results.csv

        STATUS=$?

        rm -f "$CTL"

        if (( STATUS != 0 )); then
            echo "WARNING: N=$N B=$B failed (status=$STATUS)"
        fi

    done
done

echo "All experiments finished."
