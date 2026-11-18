
#include <bits/stdc++.h>
using namespace std;

using ll = long long;
using Clock = chrono::steady_clock;

volatile ll global_sink = 0;

mt19937 rng(42);

ll random_number(ll low, ll high) {
    return uniform_int_distribution<ll>(low, high)(rng);
}

template <typename F>
double benchmark(F function, int repetitions = 5) {
    vector<double> times;

    for (int i = 0; i < repetitions; i++) {
        auto start = Clock::now();

        ll result = function();
        global_sink = global_sink ^ result;

        auto end = Clock::now();

        double elapsed =
            chrono::duration<double, milli>(end - start).count();

        times.push_back(elapsed);
    }

    sort(times.begin(), times.end());
    return times[times.size() / 2];
}

// --------------------------------------------------
// DATA GENERATION
// --------------------------------------------------

vector<int> generate_data(int n, int domain) {
    vector<int> data(n);

    for (int &x : data) {
        x = random_number(0, domain - 1);
    }

    return data;
}

// --------------------------------------------------
// 1. SELECTION
// --------------------------------------------------

// Sequential scan selection
ll scan_select(const vector<int>& data, int threshold) {
    ll count = 0;

    for (int x : data) {
        if (x < threshold)
            count++;
    }

    return count;
}

// Sorted-array index selection.
// This is an experimental proxy for an ordered index,
// not an implementation of the paper's T-tree/B-tree.

ll indexed_select(const vector<int>& sorted_index,
                  int threshold) {

    return lower_bound(
        sorted_index.begin(),
        sorted_index.end(),
        threshold
    ) - sorted_index.begin();
}

// --------------------------------------------------
// 2. GROUPING AND AGGREGATION
// --------------------------------------------------

// Hash grouping
ll hash_group(const vector<int>& data) {
    unordered_map<int, ll> groups;

    groups.reserve(data.size());

    for (int x : data) {
        groups[x]++;
    }

    ll checksum = 0;

    for (auto &entry : groups) {
        checksum += 1LL * entry.first * entry.second;
    }

    return checksum;
}

// Sort / merge grouping
ll sort_group(vector<int> data) {
    sort(data.begin(), data.end());

    ll checksum = 0;

    for (int i = 0; i < (int)data.size();) {
        int key = data[i];
        ll count = 0;

        while (i < (int)data.size() && data[i] == key) {
            count++;
            i++;
        }

        checksum += 1LL * key * count;
    }

    return checksum;
}

// --------------------------------------------------
// 3. EQUI-JOIN
// --------------------------------------------------

// Hash join: build hash table on smaller relation

ll hash_join(const vector<int>& A,
             const vector<int>& B) {

    const vector<int> *inner = &A;
    const vector<int> *outer = &B;

    if (A.size() > B.size()) {
        inner = &B;
        outer = &A;
    }

    unordered_map<int, ll> hash_table;
    hash_table.reserve(inner->size());

    // Build phase
    for (int x : *inner) {
        hash_table[x]++;
    }

    // Probe phase
    ll matches = 0;

    for (int x : *outer) {
        auto it = hash_table.find(x);

        if (it != hash_table.end()) {
            matches += it->second;
        }
    }

    return matches;
}

// Sort-merge join
ll merge_join(vector<int> A, vector<int> B) {
    sort(A.begin(), A.end());
    sort(B.begin(), B.end());

    int i = 0, j = 0;
    ll matches = 0;

    while (i < (int)A.size() &&
           j < (int)B.size()) {

        if (A[i] < B[j]) {
            i++;
        }
        else if (A[i] > B[j]) {
            j++;
        }
        else {
            int key = A[i];

            ll countA = 0;
            ll countB = 0;

            while (i < (int)A.size() && A[i] == key) {
                countA++;
                i++;
            }

            while (j < (int)B.size() && B[j] == key) {
                countB++;
                j++;
            }

            matches += countA * countB;
        }
    }

    return matches;
}

// --------------------------------------------------
// CSV OUTPUT
// --------------------------------------------------

void write_header(const string& filename) {
    ofstream file(filename);
    file << "N,Algorithm,Time_ms\n";
}

void write_result(const string& filename,
                  int n,
                  const string& algorithm,
                  double time) {

    ofstream file(filename, ios::app);

    file << n << ","
         << algorithm << ","
         << fixed << setprecision(4)
         << time << "\n";
}

// --------------------------------------------------
// MAIN EXPERIMENT
// --------------------------------------------------

int main() {

    write_header("results/selection.csv");
    write_header("results/grouping.csv");
    write_header("results/join.csv");

    // Adjust sizes depending on available RAM.
    vector<int> sizes = {
        100000,
        500000,
        1000000,
        2000000
    };

    const int DOMAIN = 1000000;

    cout << "Starting Query Processing Experiments\n";

    for (int n : sizes) {

        cout << "\nDataset size: " << n << endl;

        // Generate relations
        vector<int> A = generate_data(n, DOMAIN);
        vector<int> B = generate_data(n, DOMAIN);

        // ==========================================
        // EXPERIMENT 1: SELECTION
        // ==========================================

        cout << "Running selection experiments...\n";

        vector<int> sorted_index = A;

        sort(sorted_index.begin(), sorted_index.end());

        vector<double> selectivities = {
            0.01, 0.10, 0.50, 0.90
        };

        for (double s : selectivities) {

            int threshold = (int)(DOMAIN * s);

            string scan_name =
                "Scan_Select_" + to_string((int)(s * 100)) + "pct";

            string index_name =
                "Sorted_Index_" + to_string((int)(s * 100)) + "pct";

            double scan_time = benchmark([&]() {
                return scan_select(A, threshold);
            });

            double index_time = benchmark([&]() {
                return indexed_select(sorted_index, threshold);
            });

            ll scan_result = scan_select(A, threshold);
            ll index_result = indexed_select(sorted_index, threshold);

            if (scan_result != index_result) {
                cerr << "Selection correctness error!\n";
                return 1;
            }

            write_result(
                "results/selection.csv",
                n, scan_name, scan_time
            );

            write_result(
                "results/selection.csv",
                n, index_name, index_time
            );
        }

        // ==========================================
        // EXPERIMENT 2: GROUPING
        // ==========================================

        cout << "Running grouping experiments...\n";

        ll hash_result = hash_group(A);
        ll sort_result = sort_group(A);

        if (hash_result != sort_result) {
            cerr << "Grouping correctness error!\n";
            return 1;
        }

        double hash_time = benchmark([&]() {
            return hash_group(A);
        });

        double sort_time = benchmark([&]() {
            return sort_group(A);
        });

        write_result(
            "results/grouping.csv",
            n, "Hash_Grouping", hash_time
        );

        write_result(
            "results/grouping.csv",
            n, "Sort_Merge_Grouping", sort_time
        );

        // ==========================================
        // EXPERIMENT 3: EQUI-JOIN
        // ==========================================

        cout << "Running join experiments...\n";

        ll hash_join_result = hash_join(A, B);
        ll merge_join_result = merge_join(A, B);

        if (hash_join_result != merge_join_result) {
            cerr << "Join correctness error!\n";
            return 1;
        }

        double hash_join_time = benchmark([&]() {
            return hash_join(A, B);
        });

        double merge_join_time = benchmark([&]() {
            return merge_join(A, B);
        });

        write_result(
            "results/join.csv",
            n, "Hash_Join", hash_join_time
        );

        write_result(
            "results/join.csv",
            n, "Sort_Merge_Join", merge_join_time
        );

        cout << "Completed dataset size: " << n << endl;
    }

    cout << "\nAll experiments completed successfully!\n";
    cout << "Results saved inside results/\n";

    return 0;
}
