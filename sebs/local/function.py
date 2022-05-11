import concurrent.futures
import docker
import json

from sebs.faas.benchmark import ExecutionResult, Function, Trigger


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

    @classmethod
    def deserialize(cls, obj: dict) -> Trigger:
        return HTTPTrigger(obj["url"])


class LocalFunction(Function):
    def __init__(
        self,
        docker_container,
        port: int,
        name: str,
        benchmark: str,
        code_package_hash: str,
    ):
        super().__init__(benchmark, name, code_package_hash)
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
            return LocalFunction(
                instance,
                cached_config["port"],
                cached_config["name"],
                cached_config["benchmark"],
                cached_config["hash"],
            )
        except docker.errors.NotFound:
            raise RuntimeError(f"Cached container {instance_id} not available anymore!")

    def stop(self):
        self.logging.info(f"Stopping function container {self._instance_id}")
        self._instance.stop(timeout=0)
        self.logging.info(f"Function container {self._instance_id} stopped succesfully")
