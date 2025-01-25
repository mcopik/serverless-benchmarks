import numpy as np
import time
import uuid
import os

def test_disc(block_size, file_name):
    a = np.ones(int(block_size / 4), dtype=np.dtype("int32")) * 2  # Create array of specified block size
    t0 = time.perf_counter()  # Start time for write operation
    np.save(file_name, a)  # Save array to disk
    t1 = time.perf_counter()  # End time for write operation
    
    t2 = time.perf_counter()  # Start time for read operation
    loaded_array = np.load(file_name)  # Load array from disk
    t3 = time.perf_counter()  # End time for read operation

    write_time = t1 - t0
    read_time = t3 - t2
    return {
        "block_size": block_size,
        "write_time": write_time,
        "read_time": read_time
    }

# Test configuration
config = {
    "block_size": 1024 * 1024 * 128  # 128 MB
}

result = {}
number = 0

block_size = config.get("block_size", 1024 * 100)  # Default 100 KB
file_name = "/tmp/sebs.npy"

result[str(number)] = test_disc(block_size, file_name)
print(result)
