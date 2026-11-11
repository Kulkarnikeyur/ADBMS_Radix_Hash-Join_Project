cmake_minimum_required(VERSION 3.16)
project(radixjoin CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG")
find_package(Threads REQUIRED)

add_executable(radixjoin
  src/main.cpp src/scan.cpp src/partition.cpp src/join.cpp src/parallel.cpp)
target_link_libraries(radixjoin Threads::Threads)
