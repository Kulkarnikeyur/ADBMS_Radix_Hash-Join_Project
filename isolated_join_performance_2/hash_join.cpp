
#include <iostream>
#include <vector>
#include <algorithm>
#include <random>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
#include <bits/stdc++.h>


using namespace std;
using namespace chrono;

// 8-byte input tuple
struct Tuple {
    uint32_t key;
    uint32_t oid;
};

// Hash-table node
struct Node {
    uint32_t key;
    uint32_t oid;
    int64_t next;
};

// Result tuple
struct Result {
    uint32_t left_oid;
    uint32_t right_oid;
};

// Multiplicative hash function
static inline uint64_t hash_key(uint32_t key) {
    return static_cast<uint64_t>(key) * 2654435761ULL;
}

int main(int argc, char* argv[]) {

    if (argc != 4) {
        cerr << "Usage: ./hash_join N B CONTROL_FIFO\n";
        return 1;
    }

    uint64_t N = stoull(argv[1]);
    int B = stoi(argv[2]);
    const char* fifo = argv[3];

    if (N == 0 || N > UINT32_MAX || B < 1 || B > 25) {
        cerr << "Invalid arguments\n";
        return 1;
    }

    uint64_t H = 1ULL << B;
    uint64_t mask = H - 1;

    // --------------------------------------------
    // STEP 1: Generate two relations
    // --------------------------------------------

    vector<Tuple> L(N);
    vector<Tuple> R(N);

    for (uint64_t i = 0; i < N; i++) {

        L[i] = {
            static_cast<uint32_t>(i),
            static_cast<uint32_t>(i)
        };

        R[i] = {
            static_cast<uint32_t>(i),
            static_cast<uint32_t>(i)
        };
    }

    mt19937_64 rng(123456789ULL + N + B);

    shuffle(L.begin(), L.end(), rng);
    shuffle(R.begin(), R.end(), rng);

    // --------------------------------------------
    // STEP 2: Radix clustering
    // EXCLUDED FROM MEASUREMENT
    // --------------------------------------------

    auto bucket_compare = [mask](const Tuple& a,
                                 const Tuple& b) {
        return (a.key & mask) < (b.key & mask);
    };

    sort(L.begin(), L.end(), bucket_compare);
    sort(R.begin(), R.end(), bucket_compare);

    // --------------------------------------------
    // STEP 3: Allocate result storage
    // EXCLUDED FROM MEASUREMENT
    // --------------------------------------------

    vector<Result> output(N);

    uint64_t matches = 0;
    uint64_t hash_probes = 0;
    uint64_t clusters_processed = 0;

    // --------------------------------------------
    // STEP 4: Open perf control FIFO
    // --------------------------------------------

    int ctl = open(fifo, O_WRONLY);

    if (ctl < 0) {
        perror("Opening control FIFO");
        return 1;
    }

    // Enable performance counters.
    if (write(ctl, "enable\n", 7) != 7) {
        perror("Enabling counters");
        return 1;
    }

    // --------------------------------------------
    // STEP 5: PARTITIONED HASH JOIN
    // --------------------------------------------

    auto start = steady_clock::now();

    uint64_t i = 0;
    uint64_t j = 0;

    while (i < N && j < N) {

        uint64_t bucketL = L[i].key & mask;
        uint64_t bucketR = R[j].key & mask;

        // Skip unmatched radix partitions.
        if (bucketL < bucketR) {

            while (i < N &&
                   (L[i].key & mask) == bucketL) {
                i++;
            }

            continue;
        }

        if (bucketL > bucketR) {

            while (j < N &&
                   (R[j].key & mask) == bucketR) {
                j++;
            }

            continue;
        }

        // Find end of matching partitions.
        uint64_t i_end = i;
        uint64_t j_end = j;

        while (i_end < N &&
               (L[i_end].key & mask) == bucketL) {
            i_end++;
        }

        while (j_end < N &&
               (R[j_end].key & mask) == bucketR) {
            j_end++;
        }

        uint64_t inner_size = i_end - i;
        uint64_t outer_size = j_end - j;

        // ----------------------------------------
        // BUILD PHASE
        // ----------------------------------------

        // Target average chain length = 4.
        uint64_t bucket_count =
            max(1ULL, (long long unsigned int)((inner_size + 3) / 4));

        // Hash table allocation is intentionally
        // INSIDE the measured region.
        vector<int64_t> heads(bucket_count, -1);

        vector<Node> nodes(inner_size);

        // Insert inner relation tuples.
        for (uint64_t x = 0; x < inner_size; x++) {

            const Tuple& t = L[i + x];

            uint64_t h = hash_key(t.key) % bucket_count;

            nodes[x].key = t.key;
            nodes[x].oid = t.oid;

            nodes[x].next = heads[h];

            heads[h] = static_cast<int64_t>(x);
        }

        // ----------------------------------------
        // PROBE PHASE
        // ----------------------------------------

        for (uint64_t y = j; y < j_end; y++) {

            const Tuple& probe = R[y];

            uint64_t h =
                hash_key(probe.key) % bucket_count;

            int64_t current = heads[h];

            while (current != -1) {

                hash_probes++;

                const Node& entry =
                    nodes[static_cast<uint64_t>(current)];

                if (entry.key == probe.key) {

                    output[matches++] = {
                        entry.oid,
                        probe.oid
                    };

                    break;
                }

                current = entry.next;
            }
        }

        clusters_processed++;

        // heads and nodes are destroyed here.
        // Their destruction is part of the
        // measured join execution.

        i = i_end;
        j = j_end;
    }

    auto stop = steady_clock::now();

    // Disable counters immediately after the join.
    if (write(ctl, "disable\n", 8) != 8) {
        perror("Disabling counters");
        return 1;
    }

    close(ctl);

    double elapsed_ms =
        duration<double, milli>(stop - start).count();

    // --------------------------------------------
    // STEP 6: Validate result
    // --------------------------------------------

    uint64_t checksum = 0;

    for (uint64_t k = 0; k < matches; k++) {

        checksum += output[k].left_oid;
        checksum += output[k].right_oid;
    }

    if (matches != N) {

        cerr << "ERROR: Expected " << N
             << " matches, obtained " << matches << endl;

        return 2;
    }

    // --------------------------------------------
    // STEP 7: Output
    // --------------------------------------------

    cout << N << ","
         << B << ","
         << H << ","
         << static_cast<double>(N) / H << ","
         << clusters_processed << ","
         << hash_probes << ","
         << matches << ","
         << elapsed_ms << ","
         << checksum
         << endl;

    return 0;
}
