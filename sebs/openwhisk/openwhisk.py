import json
import os
import shutil
import subprocess
from typing import Dict, List, Tuple

import docker

from sebs.benchmark import Benchmark
from sebs.cache import Cache
from sebs.faas import System, PersistentStorage
from sebs.faas.function import Function, ExecutionResult, Trigger
from .minio import Minio
from sebs.openwhisk.triggers import LibraryTrigger, HTTPTrigger
from sebs.utils import PROJECT_DIR, LoggingHandlers
from .config import OpenWhiskConfig
from .function import OpenwhiskFunction
from ..config import SeBSConfig


class OpenWhisk(System):
    _config: OpenWhiskConfig
    storage: Minio

    def __init__(self, system_config: SeBSConfig, config: OpenWhiskConfig, cache_client: Cache,
                 docker_client: docker.client, logger_handlers: LoggingHandlers):
        super().__init__(system_config, cache_client, docker_client)
        self._config = config
        self.logging_handlers = logger_handlers

    @property
    def config(self) -> OpenWhiskConfig:
        return self._config

    def get_storage(self, replace_existing: bool = False) -> PersistentStorage:
        if not hasattr(self, "storage"):
            self.storage = Minio(self.docker_client, self.cache_client, replace_existing)
            self.storage.logging_handlers = self.logging_handlers
            self.storage.start()
        else:
            self.storage.replace_existing = replace_existing
        return self.storage

    def shutdown(self) -> None:
        if self.storage and self.config.shutdown_storage:
            self.storage.stop()
        if self.config.removeCluster:
            from tools.openwhisk_preparation import delete_cluster
            delete_cluster()

    @staticmethod
    def name() -> str:
        return "openwhisk"

    @staticmethod
    def typename():
        return "OpenWhisk"

    @staticmethod
    def function_type() -> "Type[Function]":
        return OpenwhiskFunction

    def benchmark_base_image(self, benchmark: str, language_name: str, language_version: str):
        return f'spcleth/serverless-benchmarks:{self.name()}-{benchmark}-{language_name}-{language_version}'

    def build_base_image(self, directory: str, language_name: str, language_version: str, benchmark: str):
        build_dir = os.path.join(directory, 'docker')
        os.makedirs(build_dir)
        shutil.copy(
            os.path.join(PROJECT_DIR, 'docker', f'Dockerfile.run.{self.name()}.{language_name}'),
            os.path.join(build_dir, 'Dockerfile'))

        for fn in os.listdir(directory):
            if fn not in ('index.js', '__main__.py'):
                file = os.path.join(directory, fn)
                shutil.move(file, build_dir)

        with open(os.path.join(build_dir, '.dockerignore'), 'w') as f:
            f.write('Dockerfile')

        builder_image = self.system_config.benchmark_base_images(self.name(), language_name)[language_version]
        tag = self.benchmark_base_image(benchmark, language_name, language_version)
        image, _ = self.docker_client.images.build(
            tag=tag,
            path=build_dir,
            buildargs={
                'BASE_IMAGE': builder_image,
            })

        # shutil.rmtree(build_dir)

    def package_code(self, directory: str, language_name: str, language_version: str, benchmark: str) -> Tuple[str, int]:
        node = 'nodejs'
        node_handler = 'index.js'
        CONFIG_FILES = {
            'python': ['__main__.py'],
            node: [node_handler]
        }
        package_config = CONFIG_FILES[language_name]

        with open(os.path.join(directory, 'minioConfig.json'), 'w+') as minio_config:
            storage = self.get_storage()
            minio_config_json = {
                'access_key': storage._access_key,
                'secret_key': storage._secret_key,
                'url': storage._url,
            }
            minio_config.write(json.dumps(minio_config_json))

        self.build_base_image(directory, language_name, language_version, benchmark)
        os.chdir(directory)
        benchmark_archive = os.path.join(directory, f"{benchmark}.zip")
        subprocess.run(['zip', benchmark_archive] + package_config,
            stdout=subprocess.DEVNULL,
        )
        self.logging.info(f"Created {benchmark_archive} archive")
        bytes_size = os.path.getsize(benchmark_archive)
        return benchmark_archive, bytes_size

    def create_function(self, code_package: Benchmark, func_name: str) -> "OpenwhiskFunction":
        self.logging.info("Creating action on openwhisk")
        try:
            actions = subprocess.run(
                "wsk -i action list".split(),
                stderr=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
            )
            subprocess.run(
                f"grep {func_name}".split(),
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                input=actions.stdout,
                check=True,
            )
            self.logging.info(f"Function {func_name} already exist")

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logging.error(f"ERROR: {e}")
            try:
                docker_image = self.benchmark_base_image(code_package.benchmark, code_package.language_name,
                                                         code_package.language_version)
                subprocess.run(['wsk', '-i', 'action', 'create', func_name,
                                '--web', 'true',
                                '--docker', docker_image,
                                '--memory', str(code_package.benchmark_config.memory),
                                code_package.code_location
                                ],
                               stderr=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,
                               check=True,
                               )
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                self.logging.error(f"Cannot create action {func_name}, reason: {e}")
                exit(1)

        res = OpenwhiskFunction(func_name, code_package.benchmark, code_package.hash)

        # Add LibraryTrigger to a new function
        trigger = LibraryTrigger(func_name)
        trigger.logging_handlers = self.logging_handlers
        res.add_trigger(trigger)

        return res

    def update_function(self, function: Function, code_package: Benchmark):
        with open(code_package.code_location) as f:
            image_tag = f.read()
        subprocess.run(['wsk', '-i', 'action', 'update', function.name,
                        '--docker', image_tag,
                        '--memory', str(code_package.benchmark_config.memory)],
                       stderr=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL,
                       check=True,
                       )

    def default_function_name(self, code_package: Benchmark) -> str:
        return f"{code_package.benchmark}-{code_package.language_name}-{code_package.benchmark_config.memory}"

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
            return HTTPTrigger(function.name)
        else:
            raise RuntimeError("Not supported!")

    def shutdown(self) -> None:
        super().shutdown()

    def cached_function(self, function: Function):
        pass
