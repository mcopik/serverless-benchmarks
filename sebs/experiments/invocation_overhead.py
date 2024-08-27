import csv
import os
import random
import time
from datetime import datetime
from typing import Dict, TYPE_CHECKING

from sebs.benchmark import Benchmark
from sebs.faas.system import System as FaaSSystem
from sebs.experiments.experiment import Experiment
from sebs.experiments.config import Config as ExperimentConfig

if TYPE_CHECKING:
    from sebs import SeBS


class CodePackageSize:
    def __init__(self, deployment_client: FaaSSystem, benchmark: Benchmark, settings: dict):
        import math
        from numpy import linspace

        points = linspace(
            settings["code_package_begin"],
            settings["code_package_end"],
            settings["code_package_points"],
        )
        from sebs.utils import find_benchmark

        self._benchmark_path = find_benchmark("030.clock-synchronization", "benchmarks")
        self._benchmark = benchmark
        random.seed(1410)

        # estimate the size after zip compression
        self.pts = [int(pt) - 4 * 1024 for pt in points]
        self.pts = [math.floor((pt - 123) * 3 / 4) for pt in points]

        self._deployment_client = deployment_client
        self._benchmark = benchmark

    def before_sample(self, size: int, input_benchmark: dict):
        arr = bytearray((random.getrandbits(8) for i in range(size)))
        self._benchmark.code_package_modify("randomdata.bin", bytes(arr))
        function = self._deployment_client.get_function(self._benchmark)
        self._deployment_client.update_function(function, self._benchmark)


class PayloadSize:
    def __init__(self, settings: dict):
        from numpy import linspace

        points = linspace(
            settings["payload_begin"],
            settings["payload_end"],
            settings["payload_points"],
        )
        self.pts = [int(pt) for pt in points]

    def before_sample(self, size: int, input_benchmark: dict):
        import base64
        from io import BytesIO

        f = BytesIO()
        f.write(bytearray(size))
        input_benchmark["data"] = base64.b64encode(f.getvalue()).decode()


class InvocationOverhead(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)
        self.settings = self.config.experiment_settings(self.name())

    def prepare(self, sebs_client: "SeBS", deployment_client: FaaSSystem):

        # deploy network test function
        from sebs import SeBS  # noqa
        from sebs.faas.function import Trigger

        self._benchmark = sebs_client.get_benchmark(
            "030.clock-synchronization", deployment_client, self.config
        )

        self.benchmark_input = self._benchmark.prepare_input(
            deployment_client.system_resources, size="test", replace_existing=True
        )
        self._storage = deployment_client.system_resources.get_storage(replace_existing=True)

        self._function = deployment_client.get_function(self._benchmark)

        triggers = self._function.triggers(Trigger.TriggerType.HTTP)
        if len(triggers) == 0:
            self._trigger = deployment_client.create_trigger(
                self._function, Trigger.TriggerType.HTTP
            )
        else:
            self._trigger = triggers[0]

        self._out_dir = os.path.join(
            sebs_client.output_dir, "invocation-overhead", self.settings["type"]
        )
        if not os.path.exists(self._out_dir):
            os.makedirs(self._out_dir)

        self._deployment_client = deployment_client

    def run(self):

        from requests import get

        ip = get("http://checkip.amazonaws.com/").text.rstrip()
        repetitions = self.settings["repetitions"]
        N = self.settings["N"]

        if self.settings["type"] == "code":
            experiment = CodePackageSize(self._deployment_client, self._benchmark, self.settings)
        else:
            experiment = PayloadSize(self.settings)

        input_benchmark = {
            "server-address": ip,
            "repetitions": N,
            **self.benchmark_input,
        }

        output_file = os.path.join(self._out_dir, "result.csv")
        with open(output_file, "w") as csvfile:
            writer = csv.writer(csvfile, delimiter=",")
            writer.writerow(
                [
                    "size",
                    "repetition",
                    "is_cold",
                    "connection_time",
                    "start_timestamp",
                    "finish_timestamp",
                    "request_id",
                ]
            )

            for result_type in ["warm", "cold"]:
                # warm up
                if result_type == "warm":
                    self.logging.info("Warm up invocation!")
                    self.receive_datagrams(input_benchmark, N, 12000, ip)
                for size in experiment.pts:
                    experiment.before_sample(size, input_benchmark)

                    for i in range(repetitions):
                        succesful = False
                        while not succesful:
                            self.logging.info(f"Starting with {size} bytes, repetition {i}")
                            if result_type == "cold":
                                self._deployment_client.enforce_cold_start([self._function])
                                time.sleep(1)
                            row = self.receive_datagrams(input_benchmark, N, 12000, ip)
                            if result_type == "cold":
                                if not row[0]:
                                    self.logging.info("Not cold!")
                                    continue
                            else:
                                if row[0]:
                                    self.logging.info("cold!")
                                    continue
                            writer.writerow([size, i] + row)
                            succesful = True

        time.sleep(5)
        self._storage.download_bucket(self.benchmark_input["output-bucket"], self._out_dir)

    def process(
        self,
        sebs_client: "SeBS",
        deployment_client,
        directory: str,
        logging_filename: str,
    ):
        import pandas as pd
        import glob
        from sebs import SeBS  # noqa

        full_data: Dict[str, pd.Dataframe] = {}
        for f in glob.glob(
            os.path.join(directory, "invocation-overhead", self.settings["type"], "*.csv")
        ):

            if "result.csv" in f or "result-processed.csv" in f:
                continue
            request_id = os.path.basename(f).split("-", 1)[1].split(".")[0]
            data = pd.read_csv(f, sep=",").drop(["id"], axis=1)
            if request_id in full_data:
                full_data[request_id] = pd.concat([full_data[request_id], data], axis=1)
                full_data[request_id]["id"] = request_id
            else:
                full_data[request_id] = data
        df = pd.concat(full_data.values()).reset_index(drop=True)
        df["rtt"] = (df["server_rcv"] - df["client_send"]) + (df["client_rcv"] - df["server_send"])
        df["clock_drift"] = (
            (df["client_send"] - df["server_rcv"]) + (df["client_rcv"] - df["server_send"])
        ) / 2

        with open(
            os.path.join(directory, "invocation-overhead", self.settings["type"], "result.csv")
        ) as csvfile:
            with open(
                os.path.join(
                    directory,
                    "invocation-overhead",
                    self.settings["type"],
                    "result-processed.csv",
                ),
                "w",
            ) as csvfile2:
                reader = csv.reader(csvfile, delimiter=",")
                writer = csv.writer(csvfile2, delimiter=",")
                writer.writerow(
                    [
                        "payload_size",
                        "repetition",
                        "is_cold",
                        "connection_time",
                        "start_timestamp",
                        "finish_timestamp",
                        "request_id",
                        "clock_drift_mean",
                        "clock_drift_std",
                        "invocation_time",
                    ]
                )
                iter2 = iter(reader)
                for row in iter2:
                    request_id = row[-1]
                    clock_drift = df[df["id"] == request_id]["clock_drift"].mean()
                    clock_drift_std = df[df["id"] == request_id]["clock_drift"].std()
                    invocation_time = float(row[5]) - float(row[4]) - float(row[3]) + clock_drift
                    writer.writerow(row + [clock_drift, clock_drift_std, invocation_time])

    def receive_datagrams(self, input_benchmark: dict, repetitions: int, port: int, ip: str):

        import socket

        input_benchmark["server-port"] = port
        self.logging.info(f"Starting invocation with {repetitions} repetitions on port {port}")
        socket.setdefaulttimeout(4)
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind(("", port))

        fut = self._trigger.async_invoke(input_benchmark)

        begin = datetime.now()
        times = []
        i = 0
        j = 0
        while True:
            try:
                message, address = server_socket.recvfrom(1024)
                timestamp_rcv = datetime.now().timestamp()
                if message.decode() == "stop":
                    break
                timestamp_send = datetime.now().timestamp()
                server_socket.sendto(message, address)
                j = 0
            except socket.timeout:
                j += 1
                self.logging.warning("Packet loss!")
                # stop after 5 attempts
                if j == 5:
                    self.logging.error(
                        "Failing after 5 unsuccesfull attempts to " "communicate with the function!"
                    )
                    break
                # check if function invocation failed, and if yes: raise the exception
                if fut.done():
                    raise RuntimeError("Function invocation failed") from None
                # continue to next iteration
                continue
            if i > 0:
                times.append([i, timestamp_rcv, timestamp_send])
            i += 1
            j += 1
        end = datetime.now()

        # Save results even in case of failure - it might have happened in n-th iteration
        res = fut.result()
        server_timestamp = res.output["result"]["result"]["timestamp"]
        request_id = res.output["request_id"]
        is_cold = 1 if res.output["is_cold"] else 0
        output_file = os.path.join(self._out_dir, f"server-{request_id}.csv")
        with open(output_file, "w") as csvfile:
            writer = csv.writer(csvfile, delimiter=",")
            writer.writerow(["id", "server_rcv", "server_send"])
            for row in times:
                writer.writerow(row)

        self.logging.info(f"Finished {request_id} in {end - begin} [s]")

        return [
            is_cold,
            res.times.http_startup,
            res.times.client_begin.timestamp(),
            server_timestamp,
            request_id,
        ]

    @staticmethod
    def name() -> str:
        return "invocation-overhead"

    @staticmethod
    def typename() -> str:
        return "Experiment.InvocOverhead"
