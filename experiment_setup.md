# Initial Experiment: Strided Memory-Access Benchmark

## 1. Purpose

The purpose of this experiment is to study how the distance between
consecutive memory accesses (the **stride**) affects the time taken to
scan an in-memory buffer.

This experiment is based on Section 2, **"Initial Experiment,"** of
Boncz, Manegold and Kersten's VLDB 1999 paper. The paper uses a simple
scan to illustrate how memory-access cost and data locality affect
database operations.

The experiment models a database operation that reads one byte from each
record. The record width is represented by the stride: after reading one
byte, the next read occurs `stride` bytes later.

The main question is:

> How does scan execution time change as the stride between consecutive
> memory accesses increases?

## 2. Idea behind the experiment

Suppose the stride is 1 byte. The program reads:

``` text
buffer[0], buffer[1], buffer[2], buffer[3], ...
```

If the stride is 8 bytes, it reads:

``` text
buffer[0], buffer[8], buffer[16], buffer[24], ...
```

If the stride is 64 bytes, it reads:

``` text
buffer[0], buffer[64], buffer[128], buffer[192], ...
```

Processors transfer data between memory and cache in cache-line-sized
blocks, rather than fetching only the requested byte. When consecutive
accesses are close together, several accesses may use bytes from the
same cache line. This is called **spatial locality**.

As the stride increases, consecutive accesses are farther apart. The
program may use less of each fetched cache line, potentially increasing
cache misses and memory-access time.

The experiment measures the resulting change in elapsed time. The timing
results alone do not identify which cache level caused a delay; they
show the overall effect of changing the access pattern.

## 3. Experimental machine

The benchmark was run on the following machine:

  Component             Specification
  --------------------- ----------------------
  Processor             Intel Core i5-10310U
  CPU cores / threads   4 cores / 8 threads
  L1 data cache         32 KB per core
  L2 cache              256 KB per core
  L3 cache              6 MB shared
  Cache-line size       64 bytes
  Operating system      Ubuntu Linux, x86-64
  C++ compiler          GCC 12.3.0

These specifications describe the machine on which the experiment was
run. They are useful context for interpreting the results; they are not
the same hardware used in the original 1999 paper.

## 4. Benchmark configuration

The C++ program uses the following parameters:

  Parameter                                                   Value
  ------------------------ ----------------------------------------
  Buffer size                                                64 MiB
  Iterations in one scan                                    200,000
  Stride values              1, 2, 4, 8, 16, 32, 64, 128, 256 bytes
  Trials per stride                                              10
  Scans per trial                                               100
  Compiler optimisation                                       `-O2`
  C++ standard                                                C++17

For each stride, the benchmark performs 10 trials. Each trial contains
100 scans. Each scan performs 200,000 byte reads, with the address of
the read calculated as:

``` cpp
buffer[i * stride]
```

where `i` ranges from 0 to 199,999.

The elapsed time of each individual scan is measured using
`std::chrono::steady_clock`. The 100 scan times in a trial are added and
divided by 100. Therefore, each printed trial result is the **average
time for one scan**, in milliseconds.

The CSV file stores the 10 trial averages for every stride. The graph
plots the mean of those 10 trial averages.

## 5. How to understand one benchmark iteration

For a particular stride, the program visits 200,000 positions in the
buffer. For example, with stride 4, the accessed positions are:

``` text
0, 4, 8, 12, 16, ...
```

The number of bytes explicitly read during a scan is always 200,000.
What changes with the stride is the distance between the accessed
positions and therefore the span of the buffer covered by the scan.

The approximate address span is:

``` text
(iterations - 1) * stride + 1
```

For example:

       Stride   Approximate address span
  ----------- --------------------------
       1 byte              200,000 bytes
     16 bytes            3,199,985 bytes
     32 bytes            6,399,969 bytes
     64 bytes           12,799,937 bytes
    128 bytes           25,599,873 bytes
    256 bytes           51,199,745 bytes

This distinction matters: a scan always reads the same number of bytes,
but a larger stride spreads those reads over a larger region of memory.

## 6. Measurement procedure

The experiment was carried out as follows:

1.  Allocate a 64 MiB byte buffer.
2.  Initialise the buffer with deterministic, varying byte values.
3.  Select a stride from the configured list.
4.  Start a trial for that stride.
5.  Perform 100 scans. For each scan:
    -   Start the timer.
    -   Read 200,000 bytes using `buffer[i * stride]`.
    -   Stop the timer.
    -   Add the elapsed time to the trial's total.
6.  Divide the trial's total elapsed time by 100 to obtain the average
    time per scan.
7.  Repeat for 10 trials.
8.  Move to the next stride and repeat the procedure.
9.  Save the timing results and calculate the mean across the 10 trials
    for each stride.

A checksum is accumulated from the values read by the benchmark. This
makes the read results observable to the program and helps prevent the
scan from being treated as unused work by the compiler.

### Important note about cache state

The current timing implementation does **not** perform a guaranteed
cache flush before every scan. It also does not implement a controlled
cold-cache protocol. Repeated scans can reuse data already present in
the cache.

Consequently, these measurements should be described as repeated
in-memory scans under the cache behaviour of this machine---not as a
verified measurement of main-memory-only access latency.

The original paper states that its buffer was in memory but not in the
memory caches. Our implementation does not guarantee that same
condition. This is an experimental limitation and should be kept
explicit when comparing our graph with the paper.

## 7. Compilation and execution

From the `initial_experiment` directory, compile the program with:

``` bash
g++ -O2 -std=c++17 -Wall -Wextra initial_experiment.cpp -o initial_experiment
```

Run the complete benchmark and save its output:

``` bash
./initial_experiment | tee final_warm_run.txt
```

The program's output contains 10 average scan times for each stride.

To run only one selected stride, the stride-selection version of the
program accepts a command-line argument. For example:

``` bash
./initial_experiment 64
```

This runs only the 64-byte stride. The per-stride selection was used for
optional `perf` checks; the main timing graph uses the complete
benchmark output.

## 8. Results processing and graph

The 10 trial averages for each stride are stored in `results.csv`. Each
row contains:

-   `stride_bytes`: stride used for that trial.
-   `trial`: trial number (1--10).
-   `average_scan_time_ms`: average time per scan in that trial.
-   `scans_per_trial`: 100.
-   `iterations_per_scan`: 200,000.

The plotting script, `plot_results.py`, groups the CSV rows by stride
and calculates:

-   The mean execution time across the 10 trials.
-   The standard deviation across the 10 trial averages.

The graph displays the mean execution time with standard-deviation error
bars. The horizontal axis uses a base-2 logarithmic scale because the
stride values are powers of two. This makes the stride labels evenly
spaced and readable.

## 9. Observations from the measured data

The mean scan times calculated from `final_warm_run.txt` are:

    Stride (bytes)   Mean time per scan (ms)
  ---------------- -------------------------
                 1                    0.0728
                 2                    0.0726
                 4                    0.0817
                 8                    0.0873
                16                    0.0931
                32                    0.3000
                64                    1.3135
               128                    2.5696
               256                    3.6424

The broad trend is that scan time increases as stride increases. The
increase is especially visible from stride 32 onward.

A likely explanation is reduced spatial locality: with larger strides,
each access is farther from the previous one, so the program makes less
use of the other bytes brought in with a cache line. The accessed
address span also grows with stride.

These results are consistent with the paper's central observation that
memory-access performance depends on record width and data locality.
They do not, by themselves, establish the exact cache level responsible
for each increase.

Some trial-to-trial variation is visible, particularly for the larger
strides. The error bars show this variation and should be considered
when interpreting the mean values.

## 10. Optional `perf` measurements

Linux `perf` was also used to collect aggregate hardware-counter
statistics and to check selected individual strides. These checks were
supplementary.

The generic events `cache-references` and `cache-misses` are hardware-
and platform-dependent. They should not automatically be interpreted as
specific L1, L2, or L3 miss counts. The project brief does not require
exact reproduction of the paper's cache-miss counts, so the main result
of this part is the elapsed-time-versus-stride experiment.

## 11. Limitations and comparison with the paper

The experiment follows the paper's basic idea: read one byte repeatedly
from an in-memory buffer while varying the stride, and measure elapsed
time.

There are important differences:

1.  The original paper used different, older workstation hardware. Our
    cache sizes, cache-line size, CPU architecture, and memory subsystem
    are different.
2.  The paper states that its buffer was not present in memory caches.
    Our implementation does not guarantee cache eviction before each
    scan.
3.  The current results average repeated scans, so cache reuse can
    affect the measurements.
4.  The selected stride values and iteration count follow the benchmark
    configuration used in this implementation; the paper's figure
    reports the cost of 200,000 iterations over varying strides.
5.  The generic `perf` events are not a direct reproduction of the
    paper's per-level cache-miss measurements.

Therefore, the goal is to observe the broad effect of stride and
locality on the current machine, not to reproduce the original paper's
absolute timings or exact cache-miss counts.

## 12. Files produced

The `initial_experiment` directory should contain:

``` text
initial_experiment/
├── initial_experiment.cpp
├── initial_experiment
├── create_csv.py
├── results.csv
├── plot_results.py
├── stride_vs_time.png
├── final_warm_run.txt
└── experiment_setup.md
```

The executable and output files may be regenerated by following the
compilation and execution commands above.

## 13. Main takeaway

The experiment demonstrates that changing only the stride---the distance
between consecutive byte reads---can substantially change scan execution
time. Small strides make better use of nearby bytes in cache lines,
while larger strides reduce spatial locality and increase the time
required for the scan.

This supports the paper's broader argument that memory hierarchy and
data layout are important to database performance. The results must,
however, be interpreted in the context of the modern test machine and
the warmed/repeated-scan measurement method used here.
