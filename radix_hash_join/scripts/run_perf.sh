#!/usr/bin/env bash
# Linux only. Requires perf_event_paranoid <= 1 or CAP_PERFMON.
mkdir -p results/perf
perf stat -e cycles,instructions,cache-references,cache-misses,\
L1-dcache-loads,L1-dcache-load-misses,\
LLC-loads,LLC-load-misses,dTLB-loads,dTLB-load-misses \
  ./build/radixjoin partition results/perf/partition_perf.csv \
  2> results/perf/partition_perf.txt || true
perf stat -e cycles,instructions,cache-misses,dTLB-load-misses \
  ./build/radixjoin join results/perf/join_perf.csv \
  2> results/perf/join_perf.txt || true