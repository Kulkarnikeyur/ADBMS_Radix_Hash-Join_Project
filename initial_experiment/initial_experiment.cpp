#include <iostream>
#include <vector>
#include <chrono>
#include <cstdint>
#include <cstdlib>

using namespace std;
using namespace chrono;

int main(int argc, char *argv[])
{

    // // Experiment configuration
    // const size_t iterations = 200000;
    // const size_t buffer_size = 64 * 1024 * 1024;
    // const int repetitions = 10;

    // // Stride values in bytes
    // vector<size_t> strides = {
    //     1, 2, 4, 8, 16, 32, 64, 128, 256};

    // // Allocate memory buffer
    // vector<uint8_t> buffer(buffer_size);

    // // Initialize buffer with varying values
    // for (size_t i = 0; i < buffer_size; i++)
    // {
    //     buffer[i] = (i * 131 + 17) % 256;
    // }

    // uint64_t checksum = 0;

    // // Experiment for each stride
    // for (size_t stride : strides)
    // {

    //     cout << "\nTesting stride: " << stride << " bytes\n";

    //     for (int run = 1; run <= repetitions; run++)
    //     {

    //         uint64_t local_checksum = 0;

    //         auto start = high_resolution_clock::now();

    //         // Sequential scan with varying stride
    //         for (size_t i = 0; i < iterations; i++)
    //         {
    //             local_checksum += buffer[i * stride];
    //         }

    //         auto end = high_resolution_clock::now();

    //         double elapsed =
    //             duration<double, milli>(end - start).count();

    //         checksum += local_checksum;

    //         cout << "Run " << run
    //              << ": " << elapsed << " ms\n";
    //     }
    // }

    // cout << "\nFinal checksum: " << checksum << '\n';

    // problem with above code: consequently, repeated runs might measure mostly cache accesses rather than main-memory accesses.
    // The original paper used older hardware with substantially smaller caches. Our modern processor requires additional care to make the memory-access bottleneck observable.

    // Experiment configuration
    const size_t iterations = 200000;
    const size_t buffer_size = 64 * 1024 * 1024;
    const int repetitions = 10;

    // Stride values in bytes
    // vector<size_t> strides = {
    //     1, 2, 4, 8, 16, 32, 64, 128, 256}; // as we are gonna start from 32 to reproduce actual paper's graph
    vector<size_t> strides = {32, 48, 64,
        80, 96, 128, 160, 192, 224, 256};

    // Allocate benchmark buffer
    vector<uint8_t> buffer(buffer_size);

    // Allocate cache eviction buffer
    vector<uint8_t> eviction_buffer(buffer_size);

    // Initialize both buffers
    for (size_t i = 0; i < buffer_size; i++)
    {
        buffer[i] = (i * 131 + 17) % 256;
        eviction_buffer[i] = (i * 73 + 29) % 256;
    }

    uint64_t checksum = 0;

    // Experiment for each stride
    for (size_t stride : strides)
    {
        if (argc > 1 &&
            stride != static_cast<size_t>(strtoull(argv[1], nullptr, 10)))
        {
            continue;
        }

        cout << "\nTesting stride: "
             << stride << " bytes\n";

        // for (int run = 1; run <= repetitions; run++)
        // {

        //     // Evict previously cached data
        //     uint64_t eviction_checksum = 0;

        //     for (size_t i = 0; i < buffer_size; i += 64)
        //     {
        //         eviction_checksum += eviction_buffer[i];
        //     }

        //     checksum += eviction_checksum;

        //     uint64_t local_checksum = 0;

        //     // Start timing
        //     auto start = steady_clock::now();

        //     // Strided memory scan
        //     for (size_t i = 0; i < iterations; i++)
        //     {
        //         local_checksum += buffer[i * stride];
        //     }

        //     // Stop timing
        //     auto end = steady_clock::now();

        //     double elapsed =
        //         duration<double, milli>(end - start).count();

        //     checksum += local_checksum;

        //     cout << "Run " << run
        //          << ": " << elapsed << " ms\n";
        // }

        // due to these previous stride results are too small ie. 0.1,1, 2-3 ms for 1, 64, 256 strides we are doing this below
        for (int run = 1; run <= repetitions; run++)
        {
            // Warm-up scan (not included in measurements)
            uint64_t warmup_checksum = 0;

            for (size_t i = 0; i < iterations; i++) {
                warmup_checksum += buffer[i * stride];
            }

            checksum += warmup_checksum; //added for warm_up version

            double total_time = 0.0;

            uint64_t local_checksum = 0;
            // 100 -> 10 for final_warm_up
            const int scans_per_trial = 10;

            for (int scan = 0; scan < scans_per_trial; scan++)
            {
                // Evict previously cached data
                // uint64_t eviction_checksum = 0;

                // for (size_t i = 0; i < buffer_size; i += 64) {
                //     eviction_checksum += eviction_buffer[i];
                // }

                // checksum += eviction_checksum; // removed for warm_up version

                // Start timing
                auto start = steady_clock::now();

                // Strided memory scan
                for (size_t i = 0; i < iterations; i++)
                {
                    local_checksum += buffer[i * stride];
                }

                // Stop timing
                auto end = steady_clock::now();

                total_time +=
                    duration<double, milli>(end - start).count();
            }

            checksum += local_checksum;

            double average_time = total_time / scans_per_trial;

            cout << "Run " << run
                 << ": " << average_time << " ms (average of "
                 << scans_per_trial << " scans)\n";
        }
    }

    cout << "\nFinal checksum: " << checksum << '\n';

    return 0;
}
