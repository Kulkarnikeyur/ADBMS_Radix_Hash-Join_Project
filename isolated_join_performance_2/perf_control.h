
#pragma once

#include <iostream>
#include <string>
#include <unistd.h>
#include <cstdlib>
#include <cerrno>
#include <cctype>

inline void perf_command(int ctl, int ack, const std::string& command) {
    std::string msg = command + "\n";

    ssize_t written = write(ctl, msg.c_str(), msg.size());

    if (written != (ssize_t)msg.size()) {
        perror("Writing perf command");
        exit(1);
    }

    std::string response;
    char c;

    while (true) {
        ssize_t n = read(ack, &c, 1);

        if (n == 1) {
            if (c == '\n') break;

            // Ignore NUL bytes sent by perf's FIFO protocol
            if (c == '\0') continue;

            response += c;
        } else if (n == 0) {
            std::cerr << "ACK FIFO closed unexpectedly\n";
            exit(1);
        } else {
            if (errno == EINTR) continue;
            perror("Reading perf acknowledgement");
            exit(1);
        }
    }

    // Remove trailing whitespace
    while (!response.empty() &&
           std::isspace((unsigned char)response.back())) {
        response.pop_back();
    }

    if (response != "ack") {
        std::cerr << "Unexpected perf acknowledgement: '"
                  << response << "' (len=" << response.size() << ")\n";

        std::cerr << "Bytes:";
        for (unsigned char ch : response) {
            std::cerr << " " << (int)ch;
        }
        std::cerr << "\n";

        exit(1);
    }
}
