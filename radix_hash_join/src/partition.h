#pragma once
#include "common.h"
#include <vector>

struct PartitionResult {
    std::vector<Tuple> data;
    std::vector<size_t> offsets;   // size 2^B + 1
};

// Full radix-cluster on the low B bits using P passes.
PartitionResult radix_cluster(std::vector<Tuple> input, int B, int P);

// Parallel wrapper (chunked across T threads, merged at the end).
PartitionResult radix_cluster_parallel(const std::vector<Tuple>& input,
                                       int B, int P, int T);