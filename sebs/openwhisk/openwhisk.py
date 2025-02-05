import os
import subprocess
from typing import cast, Dict, List, Optional, Tuple, Type

import docker

from sebs.benchmark import Benchmark
from sebs.cache import Cache
from sebs.faas import System, PersistentStorage
from sebs.faas.function import Function, ExecutionResult, Trigger
from sebs.openwhisk.container import OpenWhiskContainer
from sebs.openwhisk.storage import Minio
from sebs.openwhisk.triggers import LibraryTrigger, HTTPTrigger
from sebs.utils import LoggingHandlers
from sebs.faas.config import Resources
from .config import OpenWhiskConfig
from .function import OpenWhiskFunction, OpenWhiskFunctionConfig
from ..config import SeBSConfig


class OpenWhisk(System):
    _config: OpenWhiskConfig

    def __init__(
        self,
        system_config: SeBSConfig,
        config: OpenWhiskConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logger_handlers: LoggingHandlers,
    ):
        super().__init__(system_config, cache_client, docker_client)
        self._config = config
        self.logging_handlers = logger_handlers

        self.container_client = OpenWhiskContainer(
            self.system_config, self.config, self.docker_client, self.config.experimentalManifest
        )

        if self.config.resources.docker_username:
            if self.config.resources.docker_registry:
                docker_client.login(
                    username=self.config.resources.docker_username,
                    password=self.config.resources.docker_password,
                    registry=self.config.resources.docker_registry,
                )
            else:
                docker_client.login(
                    username=self.config.resources.docker_username,
                    password=self.config.resources.docker_password,
                )

    def initialize(self, config: Dict[str, str] = {}, resource_prefix: Optional[str] = None):
        self.initialize_resources(select_prefix=resource_prefix)

    @property
    def config(self) -> OpenWhiskConfig:
        return self._config

    def get_storage(self, replace_existing: bool = False) -> PersistentStorage:
        if not hasattr(self, "storage"):

            if not self.config.resources.storage_config:
                raise RuntimeError(
                    "OpenWhisk is missing the configuration of pre-allocated storage!"
                )
            self.storage = Minio.deserialize(
                self.config.resources.storage_config, self.cache_client, self.config.resources
            )
            self.storage.logging_handlers = self.logging_handlers
        else:
            self.storage.replace_existing = replace_existing
        return self.storage

    def shutdown(self) -> None:
        if hasattr(self, "storage") and self.config.shutdownStorage:
            self.storage.stop()
        if self.config.removeCluster:
            from tools.openwhisk_preparation import delete_cluster  # type: ignore

            delete_cluster()
        super().shutdown()

    @staticmethod
    def name() -> str:
        return "openwhisk"

    @staticmethod
    def typename():
        return "OpenWhisk"

    @staticmethod
    def function_type() -> "Type[Function]":
        return OpenWhiskFunction

    def get_wsk_cmd(self) -> List[str]:
        cmd = [self.config.wsk_exec]
        if self.config.wsk_bypass_security:
            cmd.append("-i")
        return cmd

    def package_code(
        self,
        directory: str,
        language_name: str,
        language_version: str,
        architecture: str,
        benchmark: str,
        is_cached: bool,
        container_deployment: bool,
    ) -> Tuple[str, int, str]:

        # Regardless of Docker image status, we need to create .zip file
        # to allow registration of function with OpenWhisk
        _, image_uri = self.container_client.build_base_image(
            directory, language_name, language_version, architecture, benchmark, is_cached
        )

        # We deploy Minio config in code package since this depends on local
        # deployment - it cannnot be a part of Docker image
        CONFIG_FILES = {
            "python": ["__main__.py"],
            "nodejs": ["index.js"],
        }
        package_config = CONFIG_FILES[language_name]

        benchmark_archive = os.path.join(directory, f"{benchmark}.zip")
        subprocess.run(
            ["zip", benchmark_archive] + package_config, stdout=subprocess.DEVNULL, cwd=directory
        )
        self.logging.info(f"Created {benchmark_archive} archive")
        bytes_size = os.path.getsize(benchmark_archive)
        self.logging.info("Zip archive size {:2f} MB".format(bytes_size / 1024.0 / 1024.0))
        return benchmark_archive, bytes_size, image_uri

    def storage_arguments(self) -> List[str]:
        storage = cast(Minio, self.get_storage())
        return [
            "-p",
            "MINIO_STORAGE_SECRET_KEY",
            storage.config.secret_key,
            "-p",
            "MINIO_STORAGE_ACCESS_KEY",
            storage.config.access_key,
            "-p",
            "MINIO_STORAGE_CONNECTION_URL",
            storage.config.address,
        ]

    def create_function(
        self,
        code_package: Benchmark,
        func_name: str,
        container_deployment: bool,
        container_uri: str,
    ) -> "OpenWhiskFunction":
        self.logging.info("Creating function as an action in OpenWhisk.")
        try:
            actions = subprocess.run(
                [*self.get_wsk_cmd(), "action", "list"],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
            )

            function_found = False
            docker_image = ""
            for line in actions.stdout.decode().split("\n"):
                if line and func_name in line.split()[0]:
                    function_found = True
                    break

            function_cfg = OpenWhiskFunctionConfig.from_benchmark(code_package)
            function_cfg.storage = cast(Minio, self.get_storage()).config
            if function_found:
                # docker image is overwritten by the update
                res = OpenWhiskFunction(
                    func_name, code_package.benchmark, code_package.hash, function_cfg
                )
                # Update function - we don't know what version is stored
                self.logging.info(f"Retrieved existing OpenWhisk action {func_name}.")
                self.update_function(res, code_package, container_deployment, container_uri)
            else:
                try:
                    self.logging.info(f"Creating new OpenWhisk action {func_name}")
                    docker_image = self.system_config.benchmark_image_name(
                        self.name(),
                        code_package.benchmark,
                        code_package.language_name,
                        code_package.language_version,
                        code_package.architecture,
                    )
                    subprocess.run(
                        [
                            *self.get_wsk_cmd(),
                            "action",
                            "create",
                            func_name,
                            "--web",
                            "true",
                            "--docker",
                            docker_image,
                            "--memory",
                            str(code_package.benchmark_config.memory),
                            "--timeout",
                            str(code_package.benchmark_config.timeout * 1000),
                            *self.storage_arguments(),
                            code_package.code_location,
                        ],
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        check=True,
                    )
                    function_cfg.docker_image = docker_image
                    res = OpenWhiskFunction(
                        func_name, code_package.benchmark, code_package.hash, function_cfg
                    )
                except subprocess.CalledProcessError as e:
                    self.logging.error(f"Cannot create action {func_name}.")
                    self.logging.error(f"Output: {e.stderr.decode('utf-8')}")
                    raise RuntimeError(e)

        except FileNotFoundError:
            self.logging.error("Could not retrieve OpenWhisk functions - is path to wsk correct?")
            raise RuntimeError("Failed to access wsk binary")

        # Add LibraryTrigger to a new function
        trigger = LibraryTrigger(func_name, self.get_wsk_cmd())
        trigger.logging_handlers = self.logging_handlers
        res.add_trigger(trigger)

        return res

    def update_function(
        self,
        function: Function,
        code_package: Benchmark,
        container_deployment: bool,
        container_uri: str,
    ):
        self.logging.info(f"Update an existing OpenWhisk action {function.name}.")
        function = cast(OpenWhiskFunction, function)
        docker_image = self.system_config.benchmark_image_name(
            self.name(),
            code_package.benchmark,
            code_package.language_name,
            code_package.language_version,
            code_package.architecture,
        )
        try:
            subprocess.run(
                [
                    *self.get_wsk_cmd(),
                    "action",
                    "update",
                    function.name,
                    "--web",
                    "true",
                    "--docker",
                    docker_image,
                    "--memory",
                    str(code_package.benchmark_config.memory),
                    "--timeout",
                    str(code_package.benchmark_config.timeout * 1000),
                    *self.storage_arguments(),
                    code_package.code_location,
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                check=True,
            )
            function.config.docker_image = docker_image

        except FileNotFoundError as e:
            self.logging.error("Could not update OpenWhisk function - is path to wsk correct?")
            raise RuntimeError(e)
        except subprocess.CalledProcessError as e:
            self.logging.error(f"Unknown error when running function update: {e}!")
            self.logging.error("Make sure to remove SeBS cache after restarting OpenWhisk!")
            self.logging.error(f"Output: {e.stderr.decode('utf-8')}")
            raise RuntimeError(e)

    def update_function_configuration(self, function: Function, code_package: Benchmark):
        self.logging.info(f"Update configuration of an existing OpenWhisk action {function.name}.")
        try:
            subprocess.run(
                [
                    *self.get_wsk_cmd(),
                    "action",
                    "update",
                    function.name,
                    "--memory",
                    str(code_package.benchmark_config.memory),
                    "--timeout",
                    str(code_package.benchmark_config.timeout * 1000),
                    *self.storage_arguments(),
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                check=True,
            )
        except FileNotFoundError as e:
            self.logging.error("Could not update OpenWhisk function - is path to wsk correct?")
            raise RuntimeError(e)
        except subprocess.CalledProcessError as e:
            self.logging.error(f"Unknown error when running function update: {e}!")
            self.logging.error("Make sure to remove SeBS cache after restarting OpenWhisk!")
            self.logging.error(f"Output: {e.stderr.decode('utf-8')}")
            raise RuntimeError(e)

    def is_configuration_changed(self, cached_function: Function, benchmark: Benchmark) -> bool:
        changed = super().is_configuration_changed(cached_function, benchmark)

        storage = cast(Minio, self.get_storage())
        function = cast(OpenWhiskFunction, cached_function)
        # check if now we're using a new storage
        if function.config.storage != storage.config:
            self.logging.info(
                "Updating function configuration due to changed storage configuration."
            )
            changed = True
            function.config.storage = storage.config

        return changed

    def default_function_name(
        self, code_package: Benchmark, resources: Optional[Resources] = None
    ) -> str:
        if resources is not None:
            return (
                f"{code_package.benchmark}-{code_package.language_name}-"
                f"{code_package.language_version}-{resources.resources_id}"
            )
        return (
            f"{code_package.benchmark}-{code_package.language_name}-"
            f"{code_package.language_version}"
        )

    def enforce_cold_start(self, functions: List[Function], code_package: Benchmark):
        raise NotImplementedError()

    def download_metrics(
        self,
        function_name: str,
        start_time: int,
        end_time: int,
        requests: Dict[str, ExecutionResult],
        metrics: dict,
    ):
        pass

    def create_trigger(self, function: Function, trigger_type: Trigger.TriggerType) -> Trigger:
        if trigger_type == Trigger.TriggerType.LIBRARY:
            return function.triggers(Trigger.TriggerType.LIBRARY)[0]
        elif trigger_type == Trigger.TriggerType.HTTP:
            try:
                response = subprocess.run(
                    [*self.get_wsk_cmd(), "action", "get", function.name, "--url"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
            except FileNotFoundError as e:
                self.logging.error(
                    "Could not retrieve OpenWhisk configuration - is path to wsk correct?"
                )
                raise RuntimeError(e)
            stdout = response.stdout.decode("utf-8")
            url = stdout.strip().split("\n")[-1] + ".json"
            trigger = HTTPTrigger(function.name, url)
            trigger.logging_handlers = self.logging_handlers
            function.add_trigger(trigger)
            self.cache_client.update_function(function)
            return trigger
        else:
            raise RuntimeError("Not supported!")

    def cached_function(self, function: Function):
        for trigger in function.triggers(Trigger.TriggerType.LIBRARY):
            trigger.logging_handlers = self.logging_handlers
            cast(LibraryTrigger, trigger).wsk_cmd = self.get_wsk_cmd()
        for trigger in function.triggers(Trigger.TriggerType.HTTP):
            trigger.logging_handlers = self.logging_handlers

    def disable_rich_output(self):
        self.container_client.disable_rich_output = True
