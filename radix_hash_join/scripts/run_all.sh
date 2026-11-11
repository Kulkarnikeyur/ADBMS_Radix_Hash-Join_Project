#!/usr/bin/env bash
set -e
mkdir -p results plots
cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j >/dev/null
./build/radixjoin scan      results/scan.csv
./build/radixjoin partition results/partition.csv
./build/radixjoin join      results/join.csv
./build/radixjoin parallel  results/parallel.csv