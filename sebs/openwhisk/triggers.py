import concurrent.futures
import datetime
import json
import subprocess
from typing import Dict, List, Optional  # noqa

from sebs.faas.function import ExecutionResult, Trigger


class LibraryTrigger(Trigger):
    def __init__(self, fname: str):
        super().__init__()
        self.fname = fname

    @staticmethod
    def trigger_type() -> "Trigger.TriggerType":
        return Trigger.TriggerType.LIBRARY

    @staticmethod
    def __add_params__(command: List[str], payload: dict) -> List[str]:
        for key, value in payload.items():
            command.append("--param")
            command.append(key)
            command.append(json.dumps(value))
        return command

    def sync_invoke(self, payload: dict) -> ExecutionResult:
        command = self.__add_params__(['wsk', '-i', 'action', 'invoke', '--result', self.fname], payload)
        error = None
        try:
            self.logging.info(f"Executing {command}")
            begin = datetime.datetime.now()
            response = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            end = datetime.datetime.now()
            response = response.stdout.decode("utf-8")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            end = datetime.datetime.now()
            error = e

        openwhisk_result = ExecutionResult.from_times(begin, end)
        if error is not None:
            self.logging.error("Invocation of {} failed!".format(self.fname))
            openwhisk_result.stats.failure = True
            return openwhisk_result

        return_content = json.loads(response)
        self.logging.info(f"{return_content}")

        openwhisk_result.parse_benchmark_output(return_content)
        return openwhisk_result

    def async_invoke(self, payload: dict) -> concurrent.futures.Future:
        pool = concurrent.futures.ThreadPoolExecutor()
        fut = pool.submit(self.sync_invoke, payload)
        return fut

    def serialize(self) -> dict:
        return {"type": "Library", "name": self.fname}

    @staticmethod
    def deserialize(obj: dict) -> Trigger:
        return LibraryTrigger(obj["name"])

    @staticmethod
    def typename() -> str:
        return "OpenWhisk.LibraryTrigger"


class HTTPTrigger(Trigger):
    def __init__(self, fname: str):
        super().__init__()
        self.fname = fname
        response = subprocess.run(['wsk', '-i', 'action', 'get', fname, '--url'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        stdout = response.stdout.decode("utf-8")
        self.url = stdout.strip().split('\n')[-1] + '.json'

    @staticmethod
    def typename() -> str:
        return "OpenWhisk.HTTPTrigger"

    @staticmethod
    def trigger_type() -> Trigger.TriggerType:
        return Trigger.TriggerType.HTTP

    def sync_invoke(self, payload: dict) -> ExecutionResult:
        self.logging.debug(f"Invoke function {self.url}")
        return self._http_invoke(payload, self.url, False)

    def async_invoke(self, payload: dict) -> concurrent.futures.Future:
        pool = concurrent.futures.ThreadPoolExecutor()
        fut = pool.submit(self.sync_invoke, payload)
        return fut

    def serialize(self) -> dict:
        return {"type": "HTTP", "fname": self.fname}

    @staticmethod
    def deserialize(obj: dict) -> Trigger:
        return HTTPTrigger(obj["fname"])
