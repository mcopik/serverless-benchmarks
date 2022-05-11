import json
from abc import ABC
from abc import abstractmethod
import concurrent.futures
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional  # noqa

from google.cloud.workflows.executions_v1beta.types import Execution

from sebs.utils import LoggingBase

"""
    Times are reported in microseconds.
"""


class ExecutionTimes:

    client: int
    client_begin: datetime
    client_end: datetime
    benchmark: int
    initialization: int
    http_startup: int
    http_first_byte_return: int

    def __init__(self):
        self.client = 0
        self.initialization = 0
        self.benchmark = 0

    @staticmethod
    def deserialize(cached_obj: dict) -> "ExecutionTimes":
        ret = ExecutionTimes()
        ret.__dict__.update(cached_obj)
        return ret


class ProviderTimes:

    initialization: int
    execution: int

    def __init__(self):
        self.execution = 0
        self.initialization = 0

    @staticmethod
    def deserialize(cached_obj: dict) -> "ProviderTimes":
        ret = ProviderTimes()
        ret.__dict__.update(cached_obj)
        return ret


class ExecutionStats:

    memory_used: Optional[float]
    cold_start: bool
    failure: bool

    def __init__(self):
        self.memory_used = None
        self.cold_start = False
        self.failure = False

    @staticmethod
    def deserialize(cached_obj: dict) -> "ExecutionStats":
        ret = ExecutionStats()
        ret.__dict__.update(cached_obj)
        return ret


class ExecutionBilling:

    _memory: Optional[int]
    _billed_time: Optional[int]
    _gb_seconds: int

    def __init__(self):
        self.memory = None
        self.billed_time = None
        self.gb_seconds = 0

    @property
    def memory(self) -> Optional[int]:
        return self._memory

    @memory.setter
    def memory(self, val: int):
        self._memory = val

    @property
    def billed_time(self) -> Optional[int]:
        return self._billed_time

    @billed_time.setter
    def billed_time(self, val: int):
        self._billed_time = val

    @property
    def gb_seconds(self) -> int:
        return self._gb_seconds

    @gb_seconds.setter
    def gb_seconds(self, val: int):
        self._gb_seconds = val

    @staticmethod
    def deserialize(cached_obj: dict) -> "ExecutionBilling":
        ret = ExecutionBilling()
        ret.__dict__.update(cached_obj)
        return ret


class ExecutionResult:

    output: dict
    request_id: str
    times: ExecutionTimes
    provider_times: ProviderTimes
    stats: ExecutionStats
    billing: ExecutionBilling

    def __init__(self):
        self.output = {}
        self.request_id = ""
        self.times = ExecutionTimes()
        self.provider_times = ProviderTimes()
        self.stats = ExecutionStats()
        self.billing = ExecutionBilling()

    @staticmethod
    def from_times(client_time_begin: datetime, client_time_end: datetime) -> "ExecutionResult":
        ret = ExecutionResult()
        ret.times.client_begin = client_time_begin
        ret.times.client_end = client_time_end
        ret.times.client = int((client_time_end - client_time_begin) / timedelta(microseconds=1))
        return ret

    def parse_benchmark_output(self, output: dict):
        self.output = output
        self.stats.cold_start = self.output["is_cold"]
        self.times.benchmark = int(
            (
                datetime.fromtimestamp(float(self.output["end"]))
                - datetime.fromtimestamp(float(self.output["begin"]))
            )
            / timedelta(microseconds=1)
        )

    def parse_benchmark_execution(self, execution: Execution):
        self.output = json.loads(execution.result)
        self.times.benchmark = int(
            (execution.start_time - execution.end_time) / timedelta(microseconds=1)
        )

    @staticmethod
    def deserialize(cached_config: dict) -> "ExecutionResult":
        ret = ExecutionResult()
        ret.times = ExecutionTimes.deserialize(cached_config["times"])
        ret.billing = ExecutionBilling.deserialize(cached_config["billing"])
        ret.provider_times = ProviderTimes.deserialize(cached_config["provider_times"])
        ret.stats = ExecutionStats.deserialize(cached_config["stats"])
        ret.request_id = cached_config["request_id"]
        ret.output = cached_config["output"]
        return ret


"""
    Function trigger and implementation of invocation.

    FIXME: implement a generic HTTP invocation and specialize input and output
    processing in classes.
"""


class Trigger(ABC, LoggingBase):
    class TriggerType(Enum):
        HTTP = "http"
        LIBRARY = "library"
        STORAGE = "storage"

        @staticmethod
        def get(name: str) -> "Trigger.TriggerType":
            for member in Trigger.TriggerType:
                if member.value.lower() == name.lower():
                    return member
            raise Exception("Unknown trigger type {}".format(member))

    def _http_invoke(self, payload: dict, url: str) -> ExecutionResult:
        import pycurl
        from io import BytesIO

        c = pycurl.Curl()
        c.setopt(pycurl.HTTPHEADER, ["Content-Type: application/json"])
        c.setopt(pycurl.POST, 1)
        c.setopt(pycurl.URL, url)
        data = BytesIO()
        c.setopt(pycurl.WRITEFUNCTION, data.write)

        c.setopt(pycurl.POSTFIELDS, json.dumps(payload))
        begin = datetime.now()
        c.perform()
        end = datetime.now()
        status_code = c.getinfo(pycurl.RESPONSE_CODE)
        conn_time = c.getinfo(pycurl.PRETRANSFER_TIME)
        receive_time = c.getinfo(pycurl.STARTTRANSFER_TIME)

        try:
            output = json.loads(data.getvalue())

            if status_code != 200:
                self.logging.error(
                    "Invocation on URL {} failed with status code {}!".format(url, status_code)
                )
                self.logging.error("Output: {}".format(output))
                raise RuntimeError(f"Failed invocation of function! Output: {output}")

            self.logging.debug("Invoke of function was successful")
            result = ExecutionResult.from_times(begin, end)
            result.times.http_startup = conn_time
            result.times.http_first_byte_return = receive_time
            result.request_id = output["request_id"]
            # General benchmark output parsing
            result.parse_benchmark_output(output)
            return result
        except json.decoder.JSONDecodeError:
            self.logging.error(
                "Invocation on URL {} failed with status code {}!".format(url, status_code)
            )
            self.logging.error("Output: {}".format(data.getvalue().decode()))
            raise RuntimeError(f"Failed invocation of function! Output: {data.getvalue().decode()}")

    # FIXME: 3.7+, future annotations
    @staticmethod
    @abstractmethod
    def trigger_type() -> "Trigger.TriggerType":
        pass

    @abstractmethod
    def sync_invoke(self, payload: dict) -> ExecutionResult:
        pass

    @abstractmethod
    def async_invoke(self, payload: dict) -> concurrent.futures.Future:
        pass

    @abstractmethod
    def serialize(self) -> dict:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, cached_config: dict) -> "Trigger":
        pass


"""
    Abstraction base class for FaaS benchmarks. Contains a list of associated triggers
    and might implement non-trigger execution if supported by the SDK.
    Example: direct function invocation through AWS boto3 SDK.
"""


class Benchmark(LoggingBase):
    def __init__(self, code_package: str, name: str, code_hash: str):
        super().__init__()
        self._code_package = code_package
        self._name = name
        self._code_package_hash = code_hash
        self._updated_code = False
        self._triggers: Dict[Trigger.TriggerType, List[Trigger]] = {}

    @property
    def name(self):
        return self._name

    @property
    def code_package(self):
        return self._code_package

    @property
    def code_package_hash(self):
        return self._code_package_hash

    @code_package_hash.setter
    def code_package_hash(self, new_hash: str):
        self._code_package_hash = new_hash

    @property
    def updated_code(self) -> bool:
        return self._updated_code

    @updated_code.setter
    def updated_code(self, val: bool):
        self._updated_code = val

    def triggers_all(self) -> List[Trigger]:
        return [trig for trigger_type, triggers in self._triggers.items() for trig in triggers]

    def triggers(self, trigger_type: Trigger.TriggerType) -> List[Trigger]:
        try:
            return self._triggers[trigger_type]
        except KeyError:
            return []

    def add_trigger(self, trigger: Trigger):
        if trigger.trigger_type() not in self._triggers:
            self._triggers[trigger.trigger_type()] = [trigger]
        else:
            self._triggers[trigger.trigger_type()].append(trigger)

    def serialize(self) -> dict:
        return {
            "name": self._name,
            "hash": self._code_package_hash,
            "code_package": self._code_package,
            "triggers": [
                obj.serialize() for t_type, triggers in self._triggers.items() for obj in triggers
            ],
        }

    @staticmethod
    @abstractmethod
    def deserialize(cached_config: dict) -> "Benchmark":
        pass


class Function(Benchmark):
    @staticmethod
    @abstractmethod
    def deserialize(cached_config: dict) -> "Function":
        pass


class Workflow(Benchmark):
    @staticmethod
    @abstractmethod
    def deserialize(cached_config: dict) -> "Workflow":
        pass
