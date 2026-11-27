#pragma once

#include <iostream>
#include <string>
#include <unistd.h>
#include <cstdlib>
#include <cerrno>
#include <fcntl.h>
#include <poll.h>

// Wait up to timeout_ms for at least one byte on the ACK FIFO,
// then drain everything available. We do NOT parse content.
inline bool wait_for_ack(int ack, int timeout_ms) {
    struct pollfd pfd { ack, POLLIN, 0 };
    int pr = poll(&pfd, 1, timeout_ms);
    if (pr <= 0) return false;

    char buf[512];
    // Drain whatever is available (at least one byte).
    ssize_t n = read(ack, buf, sizeof(buf));
    if (n <= 0) return false;
    return true;
}

// Perf emits ONE ACK at startup for its initial "disable".
inline void consume_startup_ack(int ack) {
    wait_for_ack(ack, 5000);
}

inline void perf_command(int ctl, int ack, const std::string& command) {
    std::string msg = command + "\n";
    ssize_t written = write(ctl, msg.c_str(), msg.size());
    if (written != static_cast<ssize_t>(msg.size())) {
        perror("Writing perf command");
        exit(1);
    }

    if (!wait_for_ack(ack, 5000)) {
        std::cerr << "Timed out waiting for ACK for '" << command << "'\n";
        exit(1);
    }
    // Optionally drain any extra bytes perf may have batched (status lines).
    wait_for_ack(ack, 50);   // short second poll; ignore result
}