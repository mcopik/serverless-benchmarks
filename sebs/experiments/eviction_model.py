import logging
import os
import time
from datetime import datetime
from typing import List, Optional, Tuple, TYPE_CHECKING
import multiprocessing
from multiprocessing.pool import AsyncResult, ThreadPool

from sebs.faas.system import System as FaaSSystem
from sebs.faas.benchmark import Function, Trigger
from sebs.experiments import Experiment, ExperimentResult
from sebs.experiments.config import Config as ExperimentConfig
from sebs.utils import serialize

if TYPE_CHECKING:
    from sebs import SeBS


class EvictionModel(Experiment):

    times = [
        1,
        # 2,
        # 4,
        # 8,
        # 15,
        # 30,
        # 60,
        # 120,
        # 180,
        # 240,
        # 300,
        # 360,
        # 480,
        # 600,
        # 720,
        # 900,
        # 1080,
        # 1200,
    ]
    # TODO: temporal fix
    # function_copies_per_time = 5
    function_copies_per_time = 1

    def __init__(self, config: ExperimentConfig):
        super().__init__(config)

    @staticmethod
    def name() -> str:
        return "eviction-model"

    @staticmethod
    def typename() -> str:
        return "Experiment.EvictionModel"

    @staticmethod
    def accept_replies(port: int, invocations: int):

        with open(f"server_{invocations}.log", "w") as f:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(("", port))
            s.listen(invocations + 1)

            print(f"Listen on {port} and wait for {invocations}", file=f)
            # First repetition
            connections: List[Tuple[socket.socket, str]] = []
            # wait for functions to connect
            while len(connections) < invocations:
                c, addr = s.accept()
                print(f"Accept connection from {addr}", file=f)
                connections.append((c, addr))

            for connection, addr in connections:
                print(f"Send message to {addr}", file=f)
                connection.send(b"accepted")
                connection.close()

            # Second repetition
            connections = []
            # wait for functions to connect
            while len(connections) < invocations:
                c, addr = s.accept()
                print(f"Accept connection from {addr}", file=f)
                connections.append((c, addr))

            for connection, addr in connections:
                print(f"Send message to {addr}", file=f)
                connection.send(b"accepted")
                connection.close()

            s.close()

    @staticmethod
    def execute_instance(sleep_time: int, pid: int, tid: int, func: Function, payload: dict):

        try:
            print(f"Process {pid} Thread {tid} Invoke function {func.name} with {payload} now!")
            begin = datetime.now()
            res = func.triggers(Trigger.TriggerType.HTTP)[0].sync_invoke(payload)
            end = datetime.now()
            if not res.stats.cold_start:
                logging.error(
                    f"First invocation not cold on func {func.name} time {sleep_time} "
                    f"pid {pid} tid {tid} id {res.request_id}"
                )
        except Exception as e:
            logging.error(f"First Invocation Failed at function {func.name}, {e}")
            raise RuntimeError()

        time_spent = float(datetime.now().strftime("%s.%f")) - float(end.strftime("%s.%f"))
        seconds_sleep = sleep_time - time_spent
        print(f"PID {pid} TID {tid} with time {time}, sleep {seconds_sleep}")
        time.sleep(seconds_sleep)

        try:
            second_begin = datetime.now()
            second_res = func.triggers(Trigger.TriggerType.HTTP)[0].sync_invoke(payload)
            second_end = datetime.now()
        except Exception:
            logging.error(f"Second Invocation Failed at function {func.name}")

        return {
            "first": res,
            "first_times": [begin.timestamp(), end.timestamp()],
            "second": second_res,
            "second_times": [second_begin.timestamp(), second_end.timestamp()],
            "invocation": pid,
        }

    @staticmethod
    def process_function(
        repetition: int,
        pid: int,
        invocations: int,
        functions: List[Function],
        times: List[int],
        payload: dict,
    ):
        b = multiprocessing.Semaphore(invocations)
        print(f"Begin at PID {pid}, repetition {repetition}")

        threads = len(functions)
        final_results: List[dict] = []
        with ThreadPool(threads) as pool:
            results: List[Optional[AsyncResult]] = [None] * threads
            """
                Invoke multiple functions with different sleep times.
                Start with the largest sleep time to overlap executions; total
                time should be equal to maximum execution time.
            """
            for idx in reversed(range(0, len(functions))):
                payload_copy = payload.copy()
                payload_copy["port"] += idx
                b.acquire()
                results[idx] = pool.apply_async(
                    EvictionModel.execute_instance,
                    args=(times[idx], pid, idx, functions[idx], payload_copy),
                )

            failed = False
            for result in results:
                try:
                    assert result
                    res = result.get()
                    res["repetition"] = repetition
                    final_results.append(res)
                except Exception as e:
                    print(e)
                    failed = True
            if failed:
                print("Execution failed!")
                raise RuntimeError()
        return final_results

    def prepare(self, sebs_client: "SeBS", deployment_client: FaaSSystem):

        self._benchmark = sebs_client.get_benchmark(
            "040.server-reply", deployment_client, self.config
        )
        self._deployment_client = deployment_client
        self._result = ExperimentResult(self.config, deployment_client.config)
        name = deployment_client.default_benchmark_name(self._benchmark)
        self.functions_names = [
            f"{name}-{time}-{copy}"
            for time in self.times
            for copy in range(self.function_copies_per_time)
        ]
        self._out_dir = os.path.join(sebs_client.output_dir, "eviction-model")
        if not os.path.exists(self._out_dir):
            os.mkdir(self._out_dir)
        self.functions = []

        for fname in self.functions_names:
            # if self._benchmark.functions and fname in self._benchmark.functions:
            # self.logging.info(f"Skip {fname}, exists already.")
            #    continue
            self.functions.append(deployment_client.get_function(self._benchmark, func_name=fname))

    def run(self):

        settings = self.config.experiment_settings(self.name())
        invocations = settings["invocations"]
        sleep = settings["sleep"]
        repetitions = settings["repetitions"]
        invocation_idx = settings["function_copy_idx"]
        port = settings["client-port"]
        from requests import get

        ip = get("http://checkip.amazonaws.com/").text.rstrip()

        # function_names = self.functions_names[invocation_idx :: self.function_copies_per_time]
        # flake8 issue
        # https://github.com/PyCQA/pycodestyle/issues/373
        functions = self.functions[invocation_idx :: self.function_copies_per_time]  # noqa
        results = {}

        # Disable logging - otherwise we have RLock that can't get be pickled
        for func in functions:
            # func.disable_logging()
            for tr in func.triggers_all():
                del tr._logging_handlers
        # self.disable_logging()
        # del self.logging

        for t in self.times:
            results[t] = []

        fname = f"results_{invocations}_{repetitions}_{sleep}.json"

        """
            Allocate one process for each invocation => process N invocations in parallel.
            Each process uses M threads to execute in parallel invocations,
            with a different time sleep between executions.

            The result: repeated N invocations for M different imes.
        """
        threads = len(self.times)
        with multiprocessing.Pool(processes=(invocations + threads)) as pool:
            for i in range(0, repetitions):
                """
                Attempt to kill all existing containers.
                """
                # for func in functions:
                #    self._deployment_client.enforce_cold_start(func)
                # time.sleep(5)
                for _, t in enumerate(self.times):
                    results[t].append([])
                local_results = []
                servers_results = []

                """
                    Start M server intances. Each one handles one set of invocations.
                """
                for j in range(0, threads):
                    servers_results.append(
                        pool.apply_async(EvictionModel.accept_replies, args=(port + j, invocations))
                    )

                """
                    Start N parallel invocations
                """
                for j in range(0, invocations):
                    payload = {"ip-address": ip, "port": port}
                    print(payload)
                    local_results.append(
                        pool.apply_async(
                            EvictionModel.process_function,
                            args=(i, j, invocations, functions, self.times, payload),
                        )
                    )

                time.sleep(10)
                import sys

                sys.stdout.flush()
                """
                    Rethrow exceptions if appear
                """
                for result in servers_results:
                    ret = result.get()

                for result in local_results:
                    ret = result.get()
                    for i, val in enumerate(ret):
                        results[self.times[i]][-1].append(val)

                """
                    Make sure that parallel invocations are truly parallel,
                    i.e. no execution happens after another one finished.
                """
                # verify_results(results)

            with open(os.path.join(self._out_dir, fname), "w") as out_f:
                # print(results)
                print(f"Write results to {os.path.join(self._out_dir, fname)}")
                out_f.write(serialize(results))
        # func = self._deployment_client.get_function(
        #    self._benchmark, self.functions_names[0]
        # )
        # self._deployment_client.enforce_cold_start(func)
        # ret = func.triggers[0].async_invoke(payload)
        # result = ret.result()
        # print(result.stats.cold_start)
        # self._result.add_invocation(func, result)
        # print(serialize(self._result))
