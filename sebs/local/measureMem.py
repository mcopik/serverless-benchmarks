"""
Measure memory consumption of a specified docker container.

Specifically, the pseudofile memory.current from the cgroup
pseudo-filesystem is read by a shell command (cat) every few
milliseconds while the container is running.
"""
import subprocess
import time
import argparse
import sys

# change filename to write to. serialize in
def measure(container_id: str, measure_interval: int) -> None:
    f = open("measurements_temp_file.txt", "w")
    while True:
        time_start = time.perf_counter_ns()
        longId = "docker-" + container_id + ".scope"
        # try:

        cmd = f"cat /sys/fs/cgroup/system.slice/{longId}/memory.current"
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, shell=True)
        f.write(
                f"{container_id} {int(p.communicate()[0].decode())}\n"
        )
        # except:
        #     cmd = "cat /sys/fs/cgroup/memory/system.slice/{id:}/memory.current".format(id=longId)
        #     p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
        #                          stdout=subprocess.PIPE, shell=True)
        #     f.write(f"{int(p.communicate()[0].decode())}")
        iter_duration = time.perf_counter_ns() - time_start
        # if iter_duration * 10e6 > measure_interval and measure_interval > 0:
            # not good. not enough precision. print a warning.
            # do something here
        """that shit doesnt work"""
        time.sleep(max(0, (measure_interval - iter_duration*10e6)/1000))


"""
 Parse container ID and measure interval and start memory measurement process.
"""
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-container_id", type=str)
    parser.add_argument("-measure_interval", type=int)
    args, unknown = parser.parse_known_args()
    sys.exit(measure(args.container_id, args.measure_interval))
