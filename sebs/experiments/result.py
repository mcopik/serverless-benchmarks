from datetime import datetime
from typing import Dict, List, Optional, Tuple  # noqa

from sebs.cache import Cache
from sebs.faas.config import Config as DeploymentConfig
from sebs.faas.benchmark import Function, ExecutionResult
from sebs.utils import LoggingHandlers
from sebs.experiments.config import Config as ExperimentConfig


class Result:
    def __init__(
        self,
        experiment_config: ExperimentConfig,
        deployment_config: DeploymentConfig,
        invocations: Optional[Dict[str, Dict[str, ExecutionResult]]] = None,
        metrics: Optional[Dict[str, dict]] = None,
        result_bucket: Optional[str] = None,
    ):
        self.config = {
            "experiments": experiment_config,
            "deployment": deployment_config,
        }
        if not invocations:
            self._invocations = {}
        else:
            self._invocations = invocations
        if not metrics:
            self._metrics = {}
        else:
            self._metrics = metrics
        self.result_bucket = result_bucket

    def begin(self):
        self.begin_time = datetime.now().timestamp()

    def end(self):
        self.end_time = datetime.now().timestamp()

    def times(self) -> Tuple[int, int]:
        return self.begin_time, self.end_time

    def add_result_bucket(self, result_bucket: str):
        self.result_bucket = result_bucket

    def add_invocation(self, func: Function, invocation: ExecutionResult):
        if func.name in self._invocations:
            self._invocations.get(func.name)[invocation.request_id] = invocation  # type: ignore
        else:
            self._invocations[func.name] = {invocation.request_id: invocation}

    def functions(self) -> List[str]:
        return list(self._invocations.keys())

    def invocations(self, func: str) -> Dict[str, ExecutionResult]:
        return self._invocations[func]

    def metrics(self, func: str) -> dict:
        if func not in self._metrics:
            self._metrics[func] = {}
        return self._metrics[func]

    @staticmethod
    def deserialize(cached_config: dict, cache: Cache, handlers: LoggingHandlers) -> "Result":
        invocations: Dict[str, dict] = {}
        for func, func_invocations in cached_config["_invocations"].items():
            invocations[func] = {}
            for invoc_id, invoc in func_invocations.items():
                invocations[func][invoc_id] = ExecutionResult.deserialize(invoc)
        ret = Result(
            ExperimentConfig.deserialize(cached_config["config"]["experiments"]),
            DeploymentConfig.deserialize(cached_config["config"]["deployment"], cache, handlers),
            invocations,
            # FIXME: compatibility with old results
            cached_config["metrics"] if "metrics" in cached_config else {},
            cached_config["result_bucket"],
        )
        ret.begin_time = cached_config["begin_time"]
        ret.end_time = cached_config["end_time"]
        return ret
