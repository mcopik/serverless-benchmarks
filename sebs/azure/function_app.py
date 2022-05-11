from sebs.azure.config import AzureResources
from sebs.faas.benchmark import Benchmark, Function, Workflow

from typing import cast


class FunctionApp(Benchmark):
    def __init__(
        self,
        name: str,
        benchmark: str,
        code_hash: str,
        function_storage: AzureResources.Storage,
    ):
        super().__init__(benchmark, name, code_hash)
        self.function_storage = function_storage

    def serialize(self) -> dict:
        return {
            **super().serialize(),
            "function_storage": self.function_storage.serialize(),
        }

    @staticmethod
    def deserialize(cached_config: dict) -> "FunctionApp":
        ret = FunctionApp(
            cached_config["name"],
            cached_config["code_package"],
            cached_config["hash"],
            AzureResources.Storage.deserialize(cached_config["function_storage"]),
        )
        from sebs.azure.triggers import HTTPTrigger

        for trigger in cached_config["triggers"]:
            trigger_type = {"HTTP": HTTPTrigger}.get(trigger["type"])
            assert trigger_type, "Unknown trigger type {}".format(trigger["type"])
            ret.add_trigger(trigger_type.deserialize(trigger))
        return ret


class AzureFunction(Function, FunctionApp):
    @staticmethod
    def deserialize(cached_config: dict) -> "AzureFunction":
        return cast(AzureFunction, FunctionApp.deserialize(cached_config))


class AzureWorkflow(Workflow, FunctionApp):
    @staticmethod
    def deserialize(cached_config: dict) -> "AzureWorkflow":
        return cast(AzureWorkflow, FunctionApp.deserialize(cached_config))
