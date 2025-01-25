import numpy as np
import time

def allocate(size_in_bytes):
    t0 = time.perf_counter()
    arr = np.ones(int(size_in_bytes/4), dtype=np.dtype("int32"))
    t1 = time.perf_counter()
    
    return {
        "time": t1 - t0,
        "size_in_bytes": size_in_bytes
    }

config = {
    "size_in_bytes": 1024 * 1024
}

result = {}
number = 0

size_of_allocated_memory = config.get("size_in_bytes", 1024 * 1024)  # Default 1 MB
result[str(number)] = allocate(size_of_allocated_memory)

print(result)
