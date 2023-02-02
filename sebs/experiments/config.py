from typing import Dict

from sebs.faas.function import Runtime


class Config:
    def __init__(self):
        self._update_code: bool = False
        self._update_storage: bool = False
        self._download_results: bool = False
        self._flags: Dict[str, bool] = {}
        self._experiment_configs: Dict[str, dict] = {}
        self._runtime = Runtime(None, None)

    @property
    def update_code(self) -> bool:
        return self._update_code

    @update_code.setter
    def update_code(self, val: bool):
        self._update_code = val

    @property
    def update_storage(self) -> bool:
        return self._update_storage

    def check_flag(self, key: str) -> bool:
        return False if key not in self._flags else self._flags[key]

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    def experiment_settings(self, name: str) -> dict:
        return self._experiment_configs[name]

    def serialize(self) -> dict:
        out = {
            "update_code": self._update_code,
            "update_storage": self._update_storage,
            "download_results": self._download_results,
            "runtime": self._runtime.serialize(),
            "flags": self._flags,
            "experiments": self._experiment_configs,
        }
        return out

    # FIXME: 3.7+ python with future annotations
    @staticmethod
    def deserialize(config: dict) -> "Config":

        cfg = Config()
        cfg._update_code = config["update_code"]
        cfg._update_storage = config["update_storage"]
        cfg._download_results = config["download_results"]
        cfg._runtime = Runtime.deserialize(config["runtime"])
        cfg._flags = config["flags"] if "flags" in config else {}

        from sebs.experiments import (
            NetworkPingPong,
            PerfCost,
            InvocationOverhead,
            EvictionModel,
            CommunicationP2P,
        )

        for exp in [NetworkPingPong, PerfCost, InvocationOverhead, EvictionModel, CommunicationP2P]:
            if exp.name() in config:
                cfg._experiment_configs[exp.name()] = config[exp.name()]

        return cfg
