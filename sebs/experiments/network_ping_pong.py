import csv
import socket
import os
import time
import glob
import pandas as pd
from datetime import datetime
from itertools import repeat
from typing import Dict, TYPE_CHECKING
from multiprocessing.dummy import Pool as ThreadPool

from sebs.faas.system import System as FaaSSystem
from sebs.faas.benchmark import Trigger
from sebs.experiments.experiment import Experiment
from sebs.experiments.config import Config as ExperimentConfig

# import cycle
if TYPE_CHECKING:
    from sebs import SeBS


class NetworkPingPong(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)

    def prepare(self, sebs_client: "SeBS", deployment_client: FaaSSystem):

        benchmark = sebs_client.get_benchmark(
            "020.network-benchmark", deployment_client, self.config
        )
        self._function = deployment_client.get_function(benchmark)
        self._storage = deployment_client.get_storage(replace_existing=True)
        self.benchmark_input = benchmark.prepare_input(storage=self._storage, size="test")
        self._out_dir = os.path.join(sebs_client.output_dir, "network-ping-pong")
        if not os.path.exists(self._out_dir):
            # shutil.rmtree(self._out_dir)
            os.mkdir(self._out_dir)

        triggers = self._function.triggers(Trigger.TriggerType.HTTP)
        if len(triggers) == 0:
            deployment_client.create_trigger(self._function, Trigger.TriggerType.HTTP)

    def run(self):

        from requests import get

        ip = get("http://checkip.amazonaws.com/").text.rstrip()
        settings = self.config.experiment_settings(self.name())
        invocations = settings["invocations"]
        repetitions = settings["repetitions"]
        threads = settings["threads"]

        pool = ThreadPool(threads)
        ports = range(12000, 12000 + invocations)
        pool.starmap(
            self.receive_datagrams,
            zip(repeat(repetitions, invocations), ports, repeat(ip, invocations)),
        )

        # give functions time to finish and upload result
        time.sleep(5)
        self._storage.download_bucket(self.benchmark_input["output-bucket"], self._out_dir)

    def process(self, directory: str):

        full_data: Dict[str, pd.Dataframe] = {}
        for f in glob.glob(os.path.join(directory, "network-ping-pong", "*.csv")):

            request_id = os.path.basename(f).split("-", 1)[1].split(".")[0]
            data = pd.read_csv(f, sep=",").drop(["id"], axis=1)
            if request_id in full_data:
                full_data[request_id] = pd.concat([full_data[request_id], data], axis=1)
            else:
                full_data[request_id] = data
        df = pd.concat(full_data.values()).reset_index(drop=True)
        df["rtt"] = (df["server_rcv"] - df["client_send"]) + (df["client_rcv"] - df["server_send"])
        print("Rows: ", df.shape[0])
        print("Mean: ", df["rtt"].mean())
        print("STD: ", df["rtt"].std())
        print("CV: ", df["rtt"].std() / df["rtt"].mean())
        print("P50: ", df["rtt"].quantile(0.5))
        print("P75: ", df["rtt"].quantile(0.75))
        print("P95: ", df["rtt"].quantile(0.95))
        print("P99: ", df["rtt"].quantile(0.99))
        print("P99,9: ", df["rtt"].quantile(0.999))
        ax = df["rtt"].hist(bins=2000)
        # ax.set_xlim([0.01, 0.04])
        fig = ax.get_figure()
        fig.savefig(os.path.join(directory, "histogram.png"))

    def receive_datagrams(self, repetitions: int, port: int, ip: str):

        print(f"Starting invocation with {repetitions} repetitions on port {port}")
        socket.setdefaulttimeout(2)
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind(("", port))

        input_benchmark = {
            "server-address": ip,
            "server-port": port,
            "repetitions": repetitions,
            **self.benchmark_input,
        }
        self._function.triggers(Trigger.TriggerType.HTTP)[0].async_invoke(input_benchmark)

        begin = datetime.now()
        times = []
        i = 0
        j = 0
        update_counter = int(repetitions / 10)
        while i < repetitions + 1:
            try:
                message, address = server_socket.recvfrom(1024)
                timestamp_rcv = datetime.now().timestamp()
                timestamp_send = datetime.now().timestamp()
                server_socket.sendto(message, address)
            except socket.timeout:
                i += 1
                print("Packet loss!")
                continue
            if i > 0:
                times.append([i, timestamp_rcv, timestamp_send])
            if j == update_counter:
                print(f"Invocation on port {port} processed {i} requests.")
                j = 0
            i += 1
            j += 1
        request_id = message.decode()
        end = datetime.now()
        print(f"Finished {request_id} in {end - begin} [s]")

        output_file = os.path.join(self._out_dir, f"server-{request_id}.csv")
        with open(output_file, "w") as csvfile:
            writer = csv.writer(csvfile, delimiter=",")
            writer.writerow(["id", "server_rcv", "server_send"])
            for row in times:
                writer.writerow(row)

    @staticmethod
    def name() -> str:
        return "network-ping-pong"

    @staticmethod
    def typename() -> str:
        return "Experiment.NetworkPingPong"
