from typing import cast, Optional

from sebs.aws.s3 import S3
from sebs.faas.benchmark import Function


class LambdaFunction(Function):
    def __init__(
        self,
        name: str,
        benchmark: str,
        arn: str,
        code_package_hash: str,
        timeout: int,
        memory: int,
        runtime: str,
        role: str,
        bucket: Optional[str] = None,
    ):
        super().__init__(benchmark, name, code_package_hash)
        self.arn = arn
        self.timeout = timeout
        self.memory = memory
        self.runtime = runtime
        self.role = role
        self.bucket = bucket

    @staticmethod
    def typename() -> str:
        return "AWS.LambdaFunction"

    def serialize(self) -> dict:
        return {
            **super().serialize(),
            "arn": self.arn,
            "timeout": self.timeout,
            "memory": self.memory,
            "runtime": self.runtime,
            "role": self.role,
            "bucket": self.bucket,
        }

    @staticmethod
    def deserialize(cached_config: dict) -> "LambdaFunction":
        from sebs.faas.benchmark import Trigger
        from sebs.aws.triggers import FunctionLibraryTrigger, HTTPTrigger

        ret = LambdaFunction(
            cached_config["name"],
            cached_config["code_package"],
            cached_config["arn"],
            cached_config["hash"],
            cached_config["timeout"],
            cached_config["memory"],
            cached_config["runtime"],
            cached_config["role"],
            cached_config["bucket"],
        )
        for trigger in cached_config["triggers"]:
            trigger_type = cast(
                Trigger,
                {"Library": FunctionLibraryTrigger, "HTTP": HTTPTrigger}.get(trigger["type"]),
            )
            assert trigger_type, "Unknown trigger type {}".format(trigger["type"])
            ret.add_trigger(trigger_type.deserialize(trigger))
        return ret

    def code_bucket(self, benchmark: str, storage_client: S3):
        self.bucket, idx = storage_client.add_input_bucket(benchmark)
        return self.bucket
