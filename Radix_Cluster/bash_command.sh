set -u

rm -rf results_overall
mkdir -p results_overall
mkdir -p results_overall/perf_results

CARDINALITIES=(15625 62500 250000 1000000 4000000 16000000 64000000)

for N in "${CARDINALITIES[@]}"; do
    for B in $(seq 1 25); do
        for P in $(seq 1 4); do
            if [ "$P" -le "$B" ]; then
                echo "Running B=$B, P=$P"

                perf stat -x, \
                    -e L1-dcache-load-misses,l2_rqsts.demand_data_rd_miss,dTLB-load-misses,dTLB-store-misses \
                    -o "results_overall/perf_results/N${N}_B${B}_P${P}.csv" \
                    -- ./radix_cluster "$B" "$P" "$N"
            fi
        done
    done
done