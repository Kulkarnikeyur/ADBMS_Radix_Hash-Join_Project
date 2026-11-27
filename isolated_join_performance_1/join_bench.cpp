//join_bench.cpp
#include <iostream>
#include <vector>
#include <algorithm>
#include <random>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include "perf_control.h"

using namespace std;
using namespace chrono;

struct Tuple {
    uint32_t key;
    uint32_t oid;
};

struct Result {
    uint32_t left_oid;
    uint32_t right_oid;
};

int main(int argc, char* argv[]) {

    if (argc < 5) {
        cerr << "Usage: ./join_bench N B CONTROL_FIFO ACK_FIFO\n";
        return 1;
    }

    uint64_t N = stoull(argv[1]);
    int B = stoi(argv[2]);
    const char* fifo = argv[3];
    const char* ackfifo = argv[4];

    if (N == 0 || N > UINT32_MAX || B < 1 || B > 25) {
        cerr << "Invalid N or B\n";
        return 1;
    }

    uint64_t H = 1ULL << B;
    uint64_t mask = H - 1;

    cerr << "Preparing relations: N=" << N
     << ", B=" << B << ", H=" << H << endl;

    // ------------------------------------------------
    // STEP 1: Generate relation L
    // ------------------------------------------------

    vector<Tuple> L(N);
    vector<Tuple> R(N);

    for (uint64_t i = 0; i < N; i++) {
        L[i] = {
            static_cast<uint32_t>(i),
            static_cast<uint32_t>(i)
        };
    }

    mt19937_64 rng(123456789 + N + B);

    // Randomize relation L.
    shuffle(L.begin(), L.end(), rng);

    // Relation R contains the same keys but in
    // an independently randomized order.
    R = L;

    shuffle(R.begin(), R.end(), rng);

    // ------------------------------------------------
    // STEP 2: Radix clustering (OUTSIDE measurement)
    // ------------------------------------------------

    auto bucket_compare = [mask](const Tuple& a,
                                 const Tuple& b) {
        return (a.key & mask) < (b.key & mask);
    };

    sort(L.begin(), L.end(), bucket_compare);
    sort(R.begin(), R.end(), bucket_compare);

    // ------------------------------------------------
    // STEP 3: Allocate result storage
    // ------------------------------------------------

    vector<Result> output(N);

    uint64_t comparisons = 0;
    uint64_t matches = 0;

    // ------------------------------------------------
    // STEP 4: Connect to perf control FIFO
    // ------------------------------------------------
    int ctl = open(fifo, O_RDWR);
    

    if (ctl < 0) {
        perror("Opening perf control FIFO");
        return 1;
    }
    int ack = open(ackfifo, O_RDWR);
    if (ack < 0) { perror("Opening ack FIFO"); return 1; }
    consume_startup_ack(ack);
    // ------------------------------------------------
    // STEP 5: ISOLATED RADIX JOIN
    // ------------------------------------------------
    perf_command(ctl, ack, "enable");

    auto start = steady_clock::now();


    uint64_t i = 0;
    uint64_t j = 0;

    while (i < N && j < N) {

        uint64_t bucketL = L[i].key & mask;
        uint64_t bucketR = R[j].key & mask;

        // Find corresponding cluster.
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

        // Both relations have the same radix cluster.
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

        // Nested-loop join on corresponding clusters.
        for (uint64_t x = i; x < i_end; x++) {

            for (uint64_t y = j; y < j_end; y++) {

                comparisons++;

                if (L[x].key == R[y].key) {

                    output[matches++] = {
                        L[x].oid,
                        R[y].oid
                    };
                }
            }
        }

        i = i_end;
        j = j_end;
    }

    auto stop = steady_clock::now();

    // Stop counters immediately after the join.
    perf_command(ctl, ack, "disable");
    close(ack);
    close(ctl);


    double elapsed_ms =
        duration<double, milli>(stop - start).count();

    // ------------------------------------------------
    // STEP 6: Validate result
    // ------------------------------------------------

    uint64_t checksum = 0;

    for (uint64_t k = 0; k < matches; k++) {
        checksum += output[k].left_oid;
        checksum += output[k].right_oid;
    }

    // ------------------------------------------------
    // STEP 7: Print CSV-compatible result
    // ------------------------------------------------

    cout << "RESULT,"
         << N << ","
         << B << ","
         << H << ","
         << (double)N / H << ","
         << comparisons << ","
         << matches << ","
         << elapsed_ms << ","
         << checksum
         << endl;

    if (matches != N) {
        cerr << "ERROR: Incorrect join result!\n";
        return 2;
    }

    return 0;
}
