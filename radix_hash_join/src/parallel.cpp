#include "common.h"
#include "partition.h"
#include "timer.h"
#include <thread>
#include <atomic>
#include <unordered_map>
#include <algorithm>

PartitionResult radix_cluster_parallel(const std::vector<Tuple>& input,
                                       int B, int P, int T) {
    const size_t n = input.size();
    const size_t chunk = (n + T - 1) / T;
    std::vector<PartitionResult> parts(T);

    auto worker = [&](int tid) {
        size_t lo = tid * chunk;
        size_t hi = std::min(n, lo + chunk);
        if (lo >= hi) return;
        std::vector<Tuple> sub(input.begin() + lo, input.begin() + hi);
        parts[tid] = radix_cluster(std::move(sub), B, P);
    };

    std::vector<std::thread> th;
    for (int i = 0; i < T; ++i) th.emplace_back(worker, i);
    for (auto& t : th) t.join();

    const size_t H = size_t(1) << B;
    std::vector<size_t> off(H + 1, 0);
    for (int t = 0; t < T; ++t)
        for (size_t h = 0; h < H; ++h)
            off[h+1] += parts[t].offsets[h+1] - parts[t].offsets[h];
    for (size_t h = 1; h <= H; ++h) off[h] += off[h-1];

    std::vector<Tuple> out(n);
    std::vector<size_t> cur = off;
    for (int t = 0; t < T; ++t) {
        for (size_t h = 0; h < H; ++h) {
            size_t lo = parts[t].offsets[h], hi = parts[t].offsets[h+1];
            for (size_t i = lo; i < hi; ++i) out[cur[h]++] = parts[t].data[i];
        }
    }
    return { std::move(out), std::move(off) };
}

void run_parallel_experiment(const std::string& out_csv) {
    const size_t C = 16ull * 1024 * 1024;
    auto R = make_relation(C, 7);
    auto S = make_probe(C, C, 8);
    const int B = 16, P = 4;

    std::vector<std::vector<std::string>> rows;
    for (int T : {1, 2, 4}) {
        double best_part = 1e18;
        for (int r = 0; r < 3; ++r) {
            auto t0 = Clock::now();
            auto Rp = radix_cluster_parallel(R, B, P, T);
            double t = ms_since(t0);
            if (t < best_part) best_part = t;
        }

        auto Rp = radix_cluster(R, B, P);
        auto Sp = radix_cluster(S, B, P);
        const size_t H = size_t(1) << B;

        auto t0 = Clock::now();
        std::vector<std::unordered_map<uint64_t, uint64_t>> ht(H);   // <-- fixed
        for (size_t p = 0; p < H; ++p) {
            size_t lo = Rp.offsets[p], hi = Rp.offsets[p+1];
            ht[p].reserve((hi - lo) * 2 + 1);
            for (size_t i = lo; i < hi; ++i)
                ht[p][Rp.data[i].key] = Rp.data[i].payload;
        }
        double build = ms_since(t0);

        t0 = Clock::now();
        size_t hits = 0;
        for (size_t p = 0; p < H; ++p) {
            size_t lo = Sp.offsets[p], hi = Sp.offsets[p+1];
            for (size_t i = lo; i < hi; ++i) {
                auto it = ht[p].find(Sp.data[i].key);
                if (it != ht[p].end()) ++hits;
            }
        }
        double probe = ms_since(t0);

        rows.push_back({std::to_string(T),
                        std::to_string(best_part),
                        std::to_string(build),
                        std::to_string(probe),
                        std::to_string(best_part + build + probe),
                        std::to_string(hits)});
        std::printf("T=%d partition=%.2f build=%.2f probe=%.2f total=%.2f hits=%zu\n",
                    T, best_part, build, probe, best_part + build + probe, hits);
    }
    write_csv(out_csv,
              {"threads","partition_ms","build_ms","probe_ms","total_ms","hits"},
              rows);
}