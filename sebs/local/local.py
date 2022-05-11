import os
import shutil
from typing import cast, Dict, List, Optional, Type, Tuple  # noqa

import docker

# from sebs.local.minio import Minio
from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.utils import LoggingHandlers
from sebs.local.config import LocalConfig
from sebs.local.storage import Minio
from sebs.local.function import LocalFunction
from sebs.faas.benchmark import Benchmark, Function, Workflow, ExecutionResult, Trigger
from sebs.faas.storage import PersistentStorage
from sebs.faas.system import System
from sebs.code_package import CodePackage


class Local(System):

    DEFAULT_PORT = 9000

    @staticmethod
    def name():
        return "local"

    @staticmethod
    def typename():
        return "Local"

    @staticmethod
    def function_type() -> "Type[Function]":
        return LocalFunction

    @staticmethod
    def workflow_type() -> "Type[Workflow]":
        raise NotImplementedError()

    @property
    def config(self) -> LocalConfig:
        return self._config

    @property
    def remove_containers(self) -> bool:
        return self._remove_containers

    @remove_containers.setter
    def remove_containers(self, val: bool):
        self._remove_containers = val

    @property
    def shutdown_storage(self) -> bool:
        return self._shutdown_storage

    @shutdown_storage.setter
    def shutdown_storage(self, val: bool):
        self._shutdown_storage = val

    def __init__(
        self,
        sebs_config: SeBSConfig,
        config: LocalConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logger_handlers: LoggingHandlers,
    ):
        super().__init__(sebs_config, cache_client, docker_client)
        self.logging_handlers = logger_handlers
        self._config = config
        self._storage_instance: Optional[Minio] = None
        self._remove_containers = True
        self._shutdown_storage = True

    """
        Create wrapper object for minio storage and fill buckets.
        Starts minio as a Docker instance, using always fresh buckets.

        :param benchmark:
        :param buckets: number of input and output buckets
        :param replace_existing: not used.
        :return: Azure storage instance
    """

    def get_storage(self, replace_existing: bool = False) -> PersistentStorage:
        if not self._storage_instance:
            self._storage_instance = Minio(
                self._docker_client, self._cache_client, replace_existing
            )
            self._storage_instance.logging_handlers = self.logging_handlers
            self._storage_instance.start()
        else:
            self._storage_instance.replace_existing = replace_existing
        return self._storage_instance

    """
        Shut down minio storage instance.
    """

    def shutdown(self):
        if self._storage_instance and self.shutdown_storage:
            self._storage_instance.stop()

    """
        It would be sufficient to just pack the code and ship it as zip to AWS.
        However, to have a compatible function implementation across providers,
        we create a small module.
        Issue: relative imports in Python when using storage wrapper.
        Azure expects a relative import inside a module.

        Structure:
        function
        - function.py
        - storage.py
        - resources
        handler.py

        dir: directory where code is located
        benchmark: benchmark name
    """

    def package_code(
        self, code_package: CodePackage, directory: str, is_workflow: bool
    ) -> Tuple[str, int]:

        CONFIG_FILES = {
            "python": ["handler.py", "requirements.txt", ".python_packages"],
            "nodejs": ["handler.js", "package.json", "node_modules"],
        }
        package_config = CONFIG_FILES[code_package.language_name]
        function_dir = os.path.join(directory, "function")
        os.makedirs(function_dir)
        # move all files to 'function' except handler.py
        for file in os.listdir(directory):
            if file not in package_config:
                file = os.path.join(directory, file)
                shutil.move(file, function_dir)

        bytes_size = os.path.getsize(directory)
        mbytes = bytes_size / 1024.0 / 1024.0
        self.logging.info("Function size {:2f} MB".format(mbytes))

        return directory, bytes_size

    def create_function(self, code_package: CodePackage, func_name: str) -> "LocalFunction":

        home_dir = os.path.join(
            "/home",
            self._system_config.username(self.name(), code_package.language_name),
        )
        container_name = "{}:run.local.{}.{}".format(
            self._system_config.docker_repository(),
            code_package.language_name,
            code_package.language_version,
        )
        environment: Dict[str, str] = {}
        if self._storage_instance:
            environment = {
                "MINIO_ADDRESS": self._storage_instance._url,
                "MINIO_ACCESS_KEY": self._storage_instance._access_key,
                "MINIO_SECRET_KEY": self._storage_instance._secret_key,
            }
        container = self._docker_client.containers.run(
            image=container_name,
            command=f"python3 server.py {self.DEFAULT_PORT}",
            volumes={
                code_package.code_location: {
                    "bind": os.path.join(home_dir, "code"),
                    "mode": "ro",
                }
            },
            environment=environment,
            # FIXME: make CPUs configurable
            # cpuset_cpus=cpuset,
            # required to access perf counters
            # alternative: use custom seccomp profile
            privileged=True,
            user=os.getuid(),
            security_opt=["seccomp:unconfined"],
            network_mode="bridge",
            # somehow removal of containers prevents checkpointing from working?
            remove=self.remove_containers,
            stdout=True,
            stderr=True,
            detach=True,
            # tty=True,
        )
        func = LocalFunction(
            container,
            self.DEFAULT_PORT,
            func_name,
            code_package.name,
            code_package.hash,
        )
        self.logging.info(
            f"Started {func_name} function at container {container.id} , running on {func._url}"
        )
        return func

    """
        FIXME: restart Docker?
    """

    def update_function(self, function: Function, code_package: CodePackage):
        pass

    """
        For local functions, we don't need to do anything for a cached function.
        There's only one trigger - HTTP.
    """

    def create_function_trigger(self, func: Function, trigger_type: Trigger.TriggerType) -> Trigger:
        from sebs.local.function import HTTPTrigger

        function = cast(LocalFunction, func)
        if trigger_type == Trigger.TriggerType.HTTP:
            trigger = HTTPTrigger(function._url)
            trigger.logging_handlers = self.logging_handlers
        else:
            raise RuntimeError("Not supported!")

        function.add_trigger(trigger)
        self.cache_client.update_benchmark(function)
        return trigger

    def cached_benchmark(self, benchmark: Benchmark):
        pass

    def download_metrics(
        self,
        function_name: str,
        start_time: int,
        end_time: int,
        requests: Dict[str, ExecutionResult],
        metrics: dict,
    ):
        pass

    def enforce_cold_start(self, functions: List[Function], code_package: CodePackage):
        raise NotImplementedError()

    @staticmethod
    def default_benchmark_name(code_package: CodePackage) -> str:
        # Create function name
        func_name = "{}-{}-{}".format(
            code_package.name,
            code_package.language_name,
            code_package.config.memory,
        )
        return func_name

    @staticmethod
    def format_function_name(func_name: str) -> str:
        return func_name

    def create_workflow(self, code_package: CodePackage, workflow_name: str) -> Workflow:
        raise NotImplementedError()

    def create_workflow_trigger(
        self, workflow: Workflow, trigger_type: Trigger.TriggerType
    ) -> Trigger:
        raise NotImplementedError()

    def update_workflow(self, workflow: Workflow, code_package: CodePackage):
        raise NotImplementedError()
