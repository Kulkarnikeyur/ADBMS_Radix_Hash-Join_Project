#include "common.h"
#include "timer.h"
#include "partition.h"       // <-- add this
#include <unordered_map>
#include <unordered_map>

// ---- Simple (non-partitioned) hash join -------------------------------
size_t simple_hash_join(const std::vector<Tuple>& R,
                        const std::vector<Tuple>& S) {
    std::unordered_map<uint64_t, std::vector<uint64_t>> ht;
    ht.reserve(R.size() * 2);
    for (const auto& t : R) ht[t.key].push_back(t.payload);
    size_t hits = 0;
    for (const auto& t : S) {
        auto it = ht.find(t.key);
        if (it != ht.end()) hits += it->second.size();
    }
    return hits;
}

// ---- Radix hash join (partition–build–probe, fully in memory) ---------
struct RadixJoinStats {
    double partition_ms = 0, build_ms = 0, probe_ms = 0;
    size_t hits = 0;
};

RadixJoinStats radix_hash_join(const std::vector<Tuple>& R,
                               const std::vector<Tuple>& S,
                               int B, int P) {
    RadixJoinStats st;
    auto t0 = Clock::now();
    auto Rp = radix_cluster(R, B, P);
    auto Sp = radix_cluster(S, B, P);
    st.partition_ms = ms_since(t0);

    const size_t H = size_t(1) << B;

    t0 = Clock::now();
    // Build phase: one local hash table per partition of R
    std::vector<std::unordered_map<uint64_t, uint64_t>> local_ht(H);
    for (size_t p = 0; p < H; ++p) {
        const size_t lo = Rp.offsets[p], hi = Rp.offsets[p+1];
        local_ht[p].reserve((hi - lo) * 2 + 1);
        for (size_t i = lo; i < hi; ++i)
            local_ht[p][Rp.data[i].key] = Rp.data[i].payload;
    }
    st.build_ms = ms_since(t0);

    t0 = Clock::now();
    for (size_t p = 0; p < H; ++p) {
        const size_t lo = Sp.offsets[p], hi = Sp.offsets[p+1];
        for (size_t i = lo; i < hi; ++i) {
            auto it = local_ht[p].find(Sp.data[i].key);
            if (it != local_ht[p].end()) ++st.hits;
        }
    }
    st.probe_ms = ms_since(t0);
    return st;
}

void run_join_experiment(const std::string& out_csv) {
    std::vector<std::vector<std::string>> rows;
    std::vector<size_t> cards = {1u<<16, 1u<<18, 1u<<20, 1u<<22, 1u<<24};

    for (size_t C : cards) {
        auto R = make_relation(C, 1);
        auto S = make_probe(C, C, 2);

        // --- simple hash join (baseline) ---
        double best_simple = 1e18;
        for (int r = 0; r < 3; ++r) {
            auto t0 = Clock::now();
            volatile size_t h = simple_hash_join(R, S);
            (void)h;
            double t = ms_since(t0);
            if (t < best_simple) best_simple = t;
        }

        // --- radix hash join at a few (B, P) settings ---
        // Pick B so mean partition size ~ L1 (32 KB = 4096 tuples of 8 B)
        // and P so that 2^(B/P) <= ~1536 (typical L1 TLB is 64/512).
        // Candidates below cover the phash-L2, phash-TLB, phash-L1, radix opt.
        struct Setting { int B, P; const char* name; };
        std::vector<Setting> settings = {
            { (int)std::log2(C * 12.0 / (1024*1024)), 1, "phash_L2" },   // L2-sized
            { (int)std::log2(C * 12.0 / (256*1024)),  1, "phash_L3" },
            { (int)std::log2(C * 12.0 / ( 32*1024)),  2, "phash_L1" },
            { (int)std::log2(C / 8.0),                4, "radix_opt" },
        };

        for (auto& s : settings) {
            if (s.B < 1 || s.B > 24) continue;
            double best = 1e18;
            RadixJoinStats best_stats;
            for (int r = 0; r < 3; ++r) {
                auto st = radix_hash_join(R, S, s.B, s.P);
                double t = st.partition_ms + st.build_ms + st.probe_ms;
                if (t < best) { best = t; best_stats = st; }
            }
            rows.push_back({std::to_string(C), s.name,
                            std::to_string(s.B), std::to_string(s.P),
                            std::to_string(best),
                            std::to_string(best_stats.partition_ms),
                            std::to_string(best_stats.build_ms),
                            std::to_string(best_stats.probe_ms)});
            std::printf("C=%8zu %-10s B=%2d P=%d total=%8.3fms (part=%.2f build=%.2f probe=%.2f)\n",
                        C, s.name, s.B, s.P, best,
                        best_stats.partition_ms, best_stats.build_ms, best_stats.probe_ms);
        }
        rows.push_back({std::to_string(C), "simple", "0", "0",
                        std::to_string(best_simple), "0","0","0"});
        std::printf("C=%8zu simple    total=%8.3fms\n", C, best_simple);
    }
    write_csv(out_csv, {"cardinality","algorithm","B","P","total_ms",
                        "partition_ms","build_ms","probe_ms"}, rows);
}