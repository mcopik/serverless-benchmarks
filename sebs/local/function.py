import concurrent.futures
import docker
import json
from typing import Optional

from sebs.faas.function import ExecutionResult, Function, FunctionConfig, Trigger


class HTTPTrigger(Trigger):
    def __init__(self, url: str):
        super().__init__()
        self.url = url

    @staticmethod
    def typename() -> str:
        return "Local.HTTPTrigger"

    @staticmethod
    def trigger_type() -> Trigger.TriggerType:
        return Trigger.TriggerType.HTTP

    def sync_invoke(self, payload: dict) -> ExecutionResult:
        self.logging.debug(f"Invoke function {self.url}")
        return self._http_invoke(payload, self.url)

    def async_invoke(self, payload: dict) -> concurrent.futures.Future:
        pool = concurrent.futures.ThreadPoolExecutor()
        fut = pool.submit(self.sync_invoke, payload)
        return fut

    def serialize(self) -> dict:
        return {"type": "HTTP", "url": self.url}

    @staticmethod
    def deserialize(obj: dict) -> Trigger:
        return HTTPTrigger(obj["url"])


class LocalFunction(Function):
    def __init__(
        self,
        docker_container,
        port: int,
        name: str,
        benchmark: str,
        code_package_hash: str,
        config: FunctionConfig,
        measurement_pid: Optional[int] = None,
    ):
        super().__init__(benchmark, name, code_package_hash, config)
        self._instance = docker_container
        self._instance_id = docker_container.id
        self._instance.reload()
        networks = self._instance.attrs["NetworkSettings"]["Networks"]
        self._port = port
        self._url = "{IPAddress}:{Port}".format(
            IPAddress=networks["bridge"]["IPAddress"], Port=port
        )
        if not self._url:
            self.logging.error(
                f"Couldn't read the IP address of container from attributes "
                f"{json.dumps(self._instance.attrs, indent=2)}"
            )
            raise RuntimeError(
                f"Incorrect detection of IP address for container with id {self._instance_id}"
            )

        self._measurement_pid = measurement_pid

    @property
    def container(self) -> docker.models.containers.Container:
        return self._instance

    @container.setter
    def container(self, instance: docker.models.containers.Container):
        self._instance = instance

    @property
    def url(self) -> str:
        return self._url

    @property
    def memory_measurement_pid(self) -> Optional[int]:
        return self._measurement_pid

    @staticmethod
    def typename() -> str:
        return "Local.LocalFunction"

    def serialize(self) -> dict:
        return {
            **super().serialize(),
            "instance_id": self._instance_id,
            "url": self._url,
            "port": self._port,
        }

    @staticmethod
    def deserialize(cached_config: dict) -> "LocalFunction":
        try:
            instance_id = cached_config["instance_id"]
            instance = docker.from_env().containers.get(instance_id)
            cfg = FunctionConfig.deserialize(cached_config["config"])
            return LocalFunction(
                instance,
                cached_config["port"],
                cached_config["name"],
                cached_config["benchmark"],
                cached_config["hash"],
                cfg,
            )
        except docker.errors.NotFound:
            raise RuntimeError(f"Cached container {instance_id} not available anymore!")

    def stop(self):
        self.logging.info(f"Stopping function container {self._instance_id}")
        self._instance.stop(timeout=0)
        self.logging.info(f"Function container {self._instance_id} stopped succesfully")
