
#!/usr/bin/env bash

set -u

OUT="results"
mkdir -p "$OUT"
rm -f "$OUT/results.csv"

echo "N,B,H,avg_cluster,clusters,hash_probes,matches,elapsed_ms,checksum,repeat" \
    > "$OUT/results.csv"

CARDINALITIES=(15625 125000 1000000 8000000 64000000)
REPEATS=1

# Choose an allowed CPU manually after checking taskset -pc $$
CPU=2

for N in "${CARDINALITIES[@]}"; do

    # floor(log2(N)): last useful B with H <= N
    MAX_B=0
    TMP=$N

    while (( TMP > 1 )); do
        TMP=$((TMP / 2))
        MAX_B=$((MAX_B + 1))
    done

    echo "N=$N, running B=1..$MAX_B"

    for B in $(seq 1 "$MAX_B"); do

        H=$((1 << B))

        for REP in $(seq 1 "$REPEATS"); do

            CTL="$OUT/ctl_${N}_${B}_${REP}"
            ACK="$OUT/ack_${N}_${B}_${REP}"
            PERF="$OUT/perf_${N}_${B}_${REP}.txt"

            rm -f "$CTL" "$ACK"

            mkfifo "$CTL" "$ACK"

            # Keep both FIFO endpoints open, avoiding open-order deadlocks.
            exec {ctl_fd}<>"$CTL"
            exec {ack_fd}<>"$ACK"

            echo "N=$N B=$B repeat=$REP"
            {
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
                   ./hash_join "$N" "$B" "$CTL" "$ACK" | tr -d '\n'
            echo ",$REP"
            } >> "$OUT/results.csv"

            STATUS=$?

            exec {ctl_fd}>&-
            exec {ack_fd}>&-

            rm -f "$CTL" "$ACK"

            if (( STATUS != 0 )); then
                echo "FAILED N=$N B=$B repeat=$REP status=$STATUS"
            fi

        done
    done
done

echo "Finished hash-join experiment."
