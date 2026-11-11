#pragma once
#include <cstdint>
#include <vector>
#include <random>
#include <fstream>
#include <string>
#include <iostream>
#include <algorithm>

struct Tuple { uint64_t key; uint64_t payload; };

// Uniform unique keys — one side of a join
inline std::vector<Tuple> make_relation(size_t n, uint64_t seed) {
    std::mt19937_64 rng(seed);
    std::vector<Tuple> v(n);
    for (size_t i = 0; i < n; ++i) {
        // unique dense keys 0..n-1 shuffled; payload random
        v[i].key = i;
        v[i].payload = rng();
    }
    std::shuffle(v.begin(), v.end(), rng);
    return v;
}

// Build a second relation of size m drawn from the same key domain.
// hit_rate=1.0 -> every key in R appears in S at least once.
inline std::vector<Tuple> make_probe(size_t m, uint64_t domain, uint64_t seed) {
    std::mt19937_64 rng(seed);
    std::vector<Tuple> v(m);
    for (size_t i = 0; i < m; ++i) {
        v[i].key = rng() % domain;
        v[i].payload = rng();
    }
    return v;
}

inline void write_csv(const std::string& path,
                      const std::vector<std::string>& header,
                      const std::vector<std::vector<std::string>>& rows) {
    std::ofstream f(path);
    for (size_t i = 0; i < header.size(); ++i) f << header[i] << (i+1<header.size()?",":"\n");
    for (auto& r : rows) {
        for (size_t i = 0; i < r.size(); ++i) f << r[i] << (i+1<r.size()?",":"\n");
    }
    f.close();
}