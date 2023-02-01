
#include "utils.hpp"

uint64_t timeSinceEpochMillisec()
{
  auto now = std::chrono::high_resolution_clock::now();
  auto time = now.time_since_epoch();
  return std::chrono::duration_cast< std::chrono::microseconds >(time).count();
}

