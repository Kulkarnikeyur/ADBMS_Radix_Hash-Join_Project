#include "common.h"
#include "timer.h"
#include <cstring>

struct PartitionResult {
    std::vector<Tuple> data;
    // bucket start offsets for the final B bits (size 2^B + 1)
    std::vector<size_t> offsets;
};

// One radix pass over `src` using bits [bit_lo, bit_lo+bits).
static void one_pass(const std::vector<Tuple>& src,
                     std::vector<Tuple>& dst,
                     std::vector<size_t>& bucket_start, // out
                     int bits, int bit_lo) {
    const size_t H = size_t(1) << bits;
    const size_t MASK = H - 1;
    std::vector<size_t> cnt(H + 1, 0);
    for (const auto& t : src) cnt[((t.key >> bit_lo) & MASK) + 1]++;
    for (size_t i = 1; i <= H; ++i) cnt[i] += cnt[i-1];
    bucket_start = cnt;

    // scatter into destination using a shadow cursor
    std::vector<size_t> cur(H);
    for (size_t i = 0; i < H; ++i) cur[i] = cnt[i];
    for (const auto& t : src) {
        size_t h = (t.key >> bit_lo) & MASK;
        dst[cur[h]++] = t;
    }
}

PartitionResult radix_cluster(std::vector<Tuple> input, int B, int P) {
    if (B <= 0 || P <= 0 || P > B) return { std::move(input), {} };
    const int bp = B / P;
    const int bits_left = B - bp * (P - 1);
    std::vector<Tuple> a = std::move(input);
    std::vector<Tuple> b(a.size());
    int bit_lo = 0;
    for (int pass = 0; pass < P; ++pass) {
        int bits = (pass == P - 1) ? bits_left : bp;
        std::vector<size_t> bs;
        one_pass(a, b, bs, bits, bit_lo);
        a.swap(b);
        bit_lo += bits;
    }
    // final pass boundaries over the full B bits
    const size_t H = size_t(1) << B;
    std::vector<size_t> off(H + 1, 0);
    for (const auto& t : a) off[(t.key & (H-1)) + 1]++;
    for (size_t i = 1; i <= H; ++i) off[i] += off[i-1];
    return { std::move(a), std::move(off) };
}

void run_partition_experiment(const std::string& out_csv) {
    const size_t C = 8ull * 1024 * 1024;   // 8M tuples
    auto base = make_relation(C, 42);
    std::vector<std::vector<std::string>> rows;

    std::vector<int> bits_list = {2,4,6,8,10,12,14,16,18,20};
    for (int B : bits_list) {
        for (int P : {1,2,3,4}) {
            if (P > B) continue;
            // warm up
            auto warm = radix_cluster(base, B, P);
            (void)warm;

            double best = 1e18;
            for (int r = 0; r < 3; ++r) {
                auto t0 = Clock::now();
                auto out = radix_cluster(base, B, P);
                double t = ms_since(t0);
                if (t < best) best = t;
            }
            double per_elem_ns = best * 1e6 / C;
            rows.push_back({std::to_string(B), std::to_string(P),
                            std::to_string(best), std::to_string(per_elem_ns)});
            std::printf("B=%2d P=%d  time=%8.3f ms  ns/tuple=%6.2f\n",
                        B, P, best, per_elem_ns);
        }
    }
    write_csv(out_csv, {"B","P","time_ms","ns_per_tuple"}, rows);
}