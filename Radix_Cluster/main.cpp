#include <bits/stdc++.h>

using namespace std;

using ull = uint64_t;
using Clock = chrono::steady_clock;

struct Range {
    size_t begin;
    size_t end;
};

// Distribute B bits as evenly as possible across P passes.
vector<int> distributeBits(int B, int P) {
    vector<int> bits(P);

    for (int i = 0; i < P; i++) {
        bits[i] = B / P + (i < B % P ? 1 : 0);
    }

    return bits;
}

// Generate uniformly random 64-bit values.
// Collisions are negligibly unlikely at our data sizes.
vector<ull> generateData(size_t N) {
    mt19937_64 rng(42);

    vector<ull> data(N);

    for (size_t i = 0; i < N; i++) {
        data[i] = rng();
    }

    return data;
}

// Perform one complete radix-clustering experiment.
void radixCluster(
    vector<ull>& data,
    vector<ull>& temp,
    int B,
    int P
) {
    vector<int> bits = distributeBits(B, P);

    // Initially, the entire relation is one cluster.
    vector<Range> clusters = {{0, data.size()}};

    int shift = 0;

    for (int pass = 0; pass < P; pass++) {

        int bp = bits[pass];

        size_t H = 1ULL << bp;
        ull mask = H - 1;

        vector<Range> nextClusters;

        // Allocate bucket arrays once per pass (not per cluster).
        vector<size_t> count(H, 0);
        vector<size_t> offset(H, 0);
        vector<size_t> position(H, 0);

        // Process each existing cluster independently.
        for (const Range& cluster : clusters) {

            size_t start = cluster.begin;
            size_t end = cluster.end;

            size_t n = end - start;

            if (n == 0) continue;

            // Reset counts for this cluster.
            fill(count.begin(), count.end(), 0);

            // Count tuples belonging to each subcluster.
            for (size_t i = start; i < end; i++) {
                size_t bucket = (data[i] >> shift) & mask;
                count[bucket]++;
            }

            // Calculate starting offsets.
            size_t current = start;

            for (size_t b = 0; b < H; b++) {
                offset[b] = current;
                current += count[b];
            }

            // Temporary write positions.
            copy(offset.begin(), offset.end(), position.begin());

            // Scatter tuples into temp.
            for (size_t i = start; i < end; i++) {
                size_t bucket = (data[i] >> shift) & mask;
                temp[position[bucket]++] = data[i];
            }

            // Record non-empty subclusters.
            for (size_t b = 0; b < H; b++) {
                if (count[b] > 0) {
                    nextClusters.push_back({
                        offset[b],
                        offset[b] + count[b]
                    });
                }
            }
        }

        // Swap buffers ONCE after processing all clusters.
        swap(data, temp);

        clusters.swap(nextClusters);

        shift += bp;
    }
}

// Validate that every resulting cluster contains
// tuples having identical lower B bits.
bool validate(
    const vector<ull>& data,
    const vector<Range>& clusters,
    int B
) {
    ull mask = (1ULL << B) - 1;

    size_t total = 0;

    for (const Range& cluster : clusters) {

        if (cluster.begin >= cluster.end)
            return false;

        ull key = data[cluster.begin] & mask;

        for (size_t i = cluster.begin;
             i < cluster.end; i++) {

            if ((data[i] & mask) != key)
                return false;
        }

        total += cluster.end - cluster.begin;
    }

    return total == data.size();
}

// Return the resulting cluster boundaries.
vector<Range> getClusters(
    vector<ull>& data,
    int B,
    int P
) {
    vector<ull> temp(data.size());

    vector<Range> clusters = {{0, data.size()}};

    vector<int> bits = distributeBits(B, P);

    int shift = 0;

    for (int bp : bits) {

        size_t H = 1ULL << bp;
        ull mask = H - 1;

        vector<Range> next;

        for (const auto& c : clusters) {

            vector<size_t> count(H, 0);

            for (size_t i = c.begin; i < c.end; i++) {
                count[(data[i] >> shift) & mask]++;
            }

            vector<size_t> pos(H);
            size_t current = c.begin;

            for (size_t b = 0; b < H; b++) {
                pos[b] = current;
                current += count[b];
            }

            vector<size_t> write = pos;

            for (size_t i = c.begin; i < c.end; i++) {
                size_t b = (data[i] >> shift) & mask;
                temp[write[b]++] = data[i];
            }

            copy(temp.begin() + c.begin,
                 temp.begin() + c.end,
                 data.begin() + c.begin);

            for (size_t b = 0; b < H; b++) {
                if (count[b]) {
                    next.push_back({
                        pos[b], pos[b] + count[b]
                    });
                }
            }
        }

        clusters.swap(next);
        shift += bp;
    }

    return clusters;
}



int main(int argc, char* argv[]) {

    // Default experimental configuration.
    size_t N = 8000000;
    int repetitions = 1;

    // ========================================================
    // MODE 1: ./radix_cluster B P
    // MODE 2: ./radix_cluster B P N
    // ========================================================
    if (argc == 3 || argc == 4) {

        int B = stoi(argv[1]);
        int P = stoi(argv[2]);

        // argc == 3: use default N = 8,000,000
        // argc == 4: use the provided N
        if (argc == 4)
            N = stoull(argv[3]);

        if (B < 1 || B > 25 || P < 1 || P > 4 || P > B)
            throw invalid_argument("Invalid B/P configuration");

        if (N < 1)
            throw invalid_argument("N must be >= 1");

        // Select output CSV according to mode.
        string csv_path;

        if (argc == 3) {
            filesystem::create_directories("results");
            csv_path = "results/radix_cluster.csv";
        }
        else {
            filesystem::create_directories("results_overall/perf_results");
            csv_path = "results_overall/radix_cluster.csv";
        }

        // Check if CSV already exists.
        bool file_exists = filesystem::exists(csv_path);

        // Append results instead of overwriting.
        ofstream csv(csv_path, ios::app);

        if (!csv) {
            cerr << "Failed to open " << csv_path << "\n";
            return 1;
        }

        // Write header only for a new file.
        if (!file_exists) {
            csv << "N,B,P,bits_per_pass,run,time_ms\n";
        }

        // Generate the input relation.
        cout << "Generating " << N << " tuples...\n";

        vector<ull> original = generateData(N);
        vector<ull> data(N);
        vector<ull> temp(N);

        vector<int> bits = distributeBits(B, P);

        string distribution;

        for (int i = 0; i < P; i++) {
            if (i)
                distribution += "-";

            distribution += to_string(bits[i]);
        }

        cout << "Running B=" << B
             << " P=" << P
             << " N=" << N
             << " Bits=" << distribution << "\n";

        vector<double> times;

        for (int r = 1; r <= repetitions; r++) {

            data = original;

            auto begin = Clock::now();

            radixCluster(data, temp, B, P);

            auto finish = Clock::now();

            double ms =
                chrono::duration<double, milli>(
                    finish - begin
                ).count();

            times.push_back(ms);

            csv << N << ","
                << B << ","
                << P << ","
                << distribution << ","
                << r << ","
                << ms << "\n";

            csv.flush();

            cout << "Run " << r
                 << ": " << ms << " ms\n";
        }

        sort(times.begin(), times.end());

        cout << "Median execution time: "
             << times[times.size() / 2]
             << " ms\n";

        cout << "Saved to: " << csv_path << "\n";

        return 0;  // IMPORTANT: do not fall into full sweep
    }

    // Invalid command-line arguments.
    if (argc != 1) {
        cerr << "Usage:\n"
             << "  ./radix_cluster B P\n"
             << "  ./radix_cluster B P N\n"
             << "  ./radix_cluster\n";

        return 1;
    }

    // ========================================================
    // MODE 3: FULL SWEEP (./radix_cluster)
    // ========================================================

    cout << "Generating " << N << " tuples...\n";

    vector<ull> original = generateData(N);

    vector<ull> data(N);
    vector<ull> temp(N);

    filesystem::create_directories("results");

    ofstream csv("results/radix_cluster.csv");

    csv << "N,B,P,bits_per_pass,run,time_ms\n";

    for (int B = 1; B <= 25; B++) {

        for (int P = 1; P <= min(4, B); P++) {

            vector<int> bits = distributeBits(B, P);

            string distribution;

            for (int i = 0; i < P; i++) {
                if (i)
                    distribution += "-";

                distribution += to_string(bits[i]);
            }

            cout << "Running B=" << B
                 << " P=" << P
                 << " Bits=" << distribution << "\n";

            vector<double> times;

            for (int r = 1; r <= repetitions; r++) {

                data = original;

                auto begin = Clock::now();

                radixCluster(data, temp, B, P);

                auto finish = Clock::now();

                double ms =
                    chrono::duration<double, milli>(
                        finish - begin
                    ).count();

                times.push_back(ms);

                csv << N << ","
                    << B << ","
                    << P << ","
                    << distribution << ","
                    << r << ","
                    << ms << "\n";

                csv.flush();
            }

            sort(times.begin(), times.end());

            cout << "Median execution time: "
                 << times[times.size() / 2]
                 << " ms\n\n";
        }
    }

    csv.close();

    cout << "Full sweep completed.\n";

    return 0;
}
