#include <string>
#include <cstring>
void run_scan_experiment(const std::string&);
void run_partition_experiment(const std::string&);
void run_join_experiment(const std::string&);
void run_parallel_experiment(const std::string&);

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s scan|partition|join|parallel <out.csv>\n", argv[0]);
        return 1;
    }
    std::string mode = argv[1];
    std::string out = (argc >= 3) ? argv[2] : ("results/" + mode + ".csv");
    if (mode == "scan")            run_scan_experiment(out);
    else if (mode == "partition")  run_partition_experiment(out);
    else if (mode == "join")       run_join_experiment(out);
    else if (mode == "parallel")   run_parallel_experiment(out);
    else { fprintf(stderr, "unknown mode\n"); return 1; }
    return 0;
}