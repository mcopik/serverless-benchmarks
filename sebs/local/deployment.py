import json
from typing import List, Optional

from sebs.cache import Cache
from sebs.local.function import LocalFunction
from sebs.local.storage import Minio
from sebs.utils import serialize


class Deployment:
    def __init__(self):
        self._functions: List[LocalFunction] = []
        self._storage: Optional[Minio]
        self._inputs: List[dict] = []

    def add_function(self, func: LocalFunction):
        self._functions.append(func)

    def add_input(self, func_input: dict):
        self._inputs.append(func_input)

    def set_storage(self, storage: Minio):
        self._storage = storage

    def serialize(self, path: str):
        with open(path, "w") as out:
            out.write(
                serialize(
                    {
                        "functions": self._functions,
                        "storage": self._storage,
                        "inputs": self._inputs,
                    }
                )
            )

    @staticmethod
    def deserialize(path: str, cache_client: Cache) -> "Deployment":
        with open(path, "r") as in_f:
            input_data = json.load(in_f)
            deployment = Deployment()
            for input_cfg in input_data["inputs"]:
                deployment._inputs.append(input_cfg)
            for func in input_data["functions"]:
                deployment._functions.append(LocalFunction.deserialize(func))
            deployment._storage = Minio.deserialize(input_data["storage"], cache_client)
            return deployment

    def shutdown(self):
        for func in self._functions:
            func.stop()
        self._storage.stop()
