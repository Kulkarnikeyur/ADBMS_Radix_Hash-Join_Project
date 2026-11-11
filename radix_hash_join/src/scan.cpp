#include "common.h"
#include "timer.h"
#include <cstdio>

// Byte-strided scan: accesses buffer[i*s] for i in [0, N/s).
// Sum is accumulated so the compiler can't eliminate loads.
uint64_t strided_scan(const uint8_t* buf, size_t N, size_t stride) {
    uint64_t acc = 0;
    for (size_t i = 0; i * stride < N; ++i)
        acc += buf[i * stride];
    return acc;
}

// Tuple-strided scan: touches every Tuple whose (index % stride_elems)==0.
uint64_t tuple_strided_scan(const Tuple* t, size_t N, size_t stride_elems) {
    uint64_t acc = 0;
    for (size_t i = 0; i < N; i += stride_elems)
        acc += t[i].key + t[i].payload;
    return acc;
}

void run_scan_experiment(const std::string& out_csv) {
    const size_t N = 64ull * 1024 * 1024;         // 64 MB buffer
    std::vector<uint8_t> buf(N);
    for (size_t i = 0; i < N; ++i) buf[i] = (uint8_t)i;

    std::vector<size_t> strides = {1,2,4,8,16,32,64,128,256,512,1024,4096};
    std::vector<std::vector<std::string>> rows;

    for (size_t s : strides) {
        // warm-up
        volatile uint64_t sink = strided_scan(buf.data(), N, s);
        (void)sink;
        // timed, repeat to reduce noise
        const int REP = 5;
        double best = 1e18;
        for (int r = 0; r < REP; ++r) {
            auto t0 = Clock::now();
            sink = strided_scan(buf.data(), N, s);
            double t = ms_since(t0);
            if (t < best) best = t;
        }
        double bytes = double(N / s);
        double ns_per_access = (best * 1e6) / bytes;
        rows.push_back({std::to_string(s), std::to_string(best),
                        std::to_string(ns_per_access)});
        std::printf("stride=%4zu  time=%8.3f ms  ns/access=%6.2f\n",
                    s, best, ns_per_access);
    }
    write_csv(out_csv, {"stride_bytes","time_ms","ns_per_access"}, rows);
}