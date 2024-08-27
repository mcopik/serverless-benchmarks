import os
from typing import Optional, Dict, Type

import docker

from sebs import types
from sebs.local import Local
from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.benchmark import Benchmark
from sebs.faas.system import System as FaaSSystem
from sebs.faas.storage import PersistentStorage
from sebs.faas.nosql import NoSQLStorage
from sebs.faas.config import Config
from sebs.storage import minio, config, scylladb
from sebs.utils import has_platform, LoggingHandlers, LoggingBase

from sebs.experiments.config import Config as ExperimentConfig
from sebs.experiments import Experiment


class SeBS(LoggingBase):
    @property
    def cache_client(self) -> Cache:
        return self._cache_client

    @property
    def docker_client(self) -> docker.client:
        return self._docker_client

    @property
    def output_dir(self) -> str:
        return self._output_dir

    @property
    def verbose(self) -> bool:
        return self._verbose

    @property
    def logging_filename(self) -> Optional[str]:
        return self._logging_filename

    @property
    def config(self) -> SeBSConfig:
        return self._config

    def generate_logging_handlers(self, logging_filename: Optional[str] = None) -> LoggingHandlers:
        filename = logging_filename if logging_filename else self.logging_filename
        if filename in self._handlers:
            return self._handlers[filename]
        else:
            handlers = LoggingHandlers(verbose=self.verbose, filename=filename)
            self._handlers[filename] = handlers
            return handlers

    def __init__(
        self,
        cache_dir: str,
        output_dir: str,
        verbose: bool = False,
        logging_filename: Optional[str] = None,
    ):
        super().__init__()
        self._cache_client = Cache(cache_dir)
        self._docker_client = docker.from_env()
        self._config = SeBSConfig()
        self._output_dir = output_dir
        self._verbose = verbose
        self._logging_filename = logging_filename
        self._handlers: Dict[Optional[str], LoggingHandlers] = {}
        self.logging_handlers = self.generate_logging_handlers()

        os.makedirs(self.output_dir, exist_ok=True)

    def ignore_cache(self):
        """
        The cache will only store code packages,
        and won't update new functions and storage.
        """
        self._cache_client.ignore_storage = True
        self._cache_client.ignore_functions = True

    def get_deployment(
        self,
        config: dict,
        logging_filename: Optional[str] = None,
        deployment_config: Optional[Config] = None,
    ) -> FaaSSystem:
        name = config["name"]
        implementations: Dict[str, Type[FaaSSystem]] = {"local": Local}

        if has_platform("aws"):
            from sebs.aws import AWS

            implementations["aws"] = AWS
        if has_platform("azure"):
            from sebs.azure.azure import Azure

            implementations["azure"] = Azure
        if has_platform("gcp"):
            from sebs.gcp import GCP

            implementations["gcp"] = GCP
        if has_platform("openwhisk"):
            from sebs.openwhisk import OpenWhisk

            implementations["openwhisk"] = OpenWhisk

        if name not in implementations:
            raise RuntimeError("Deployment {name} not supported!".format(name=name))

        # FIXME: future annotations, requires Python 3.7+
        handlers = self.generate_logging_handlers(logging_filename)
        if not deployment_config:
            deployment_config = Config.deserialize(config, self.cache_client, handlers)
        deployment_client = implementations[name](
            self._config,
            deployment_config,  # type: ignore
            self.cache_client,
            self.docker_client,
            handlers,
        )
        return deployment_client

    def get_deployment_config(
        self,
        config: dict,
        logging_filename: Optional[str] = None,
    ) -> Config:
        handlers = self.generate_logging_handlers(logging_filename)
        return Config.deserialize(config, self.cache_client, handlers)

    def get_experiment_config(self, config: dict) -> ExperimentConfig:
        return ExperimentConfig.deserialize(config)

    def get_experiment(
        self, experiment_type: str, config: dict, logging_filename: Optional[str] = None
    ) -> Experiment:
        from sebs.experiments import (
            Experiment,
            PerfCost,
            NetworkPingPong,
            InvocationOverhead,
            EvictionModel,
        )

        implementations: Dict[str, Type[Experiment]] = {
            "perf-cost": PerfCost,
            "network-ping-pong": NetworkPingPong,
            "invocation-overhead": InvocationOverhead,
            "eviction-model": EvictionModel,
        }
        if experiment_type not in implementations:
            raise RuntimeError(f"Experiment {experiment_type} not supported!")
        experiment = implementations[experiment_type](self.get_experiment_config(config))
        experiment.logging_handlers = self.generate_logging_handlers(
            logging_filename=logging_filename
        )
        return experiment

    def get_benchmark(
        self,
        name: str,
        deployment: FaaSSystem,
        config: ExperimentConfig,
        logging_filename: Optional[str] = None,
    ) -> Benchmark:
        benchmark = Benchmark(
            name,
            deployment.name(),
            config,
            self._config,
            self._output_dir,
            self.cache_client,
            self.docker_client,
        )
        benchmark.logging_handlers = self.generate_logging_handlers(
            logging_filename=logging_filename
        )
        return benchmark

    @staticmethod
    def get_storage_implementation(storage_type: types.Storage) -> Type[PersistentStorage]:
        _storage_implementations = {types.Storage.MINIO: minio.Minio}
        impl = _storage_implementations.get(storage_type)
        assert impl
        return impl

    @staticmethod
    def get_nosql_implementation(storage_type: types.NoSQLStorage) -> Type[NoSQLStorage]:
        _storage_implementations = {types.NoSQLStorage.SCYLLADB: scylladb.ScyllaDB}
        impl = _storage_implementations.get(storage_type)
        assert impl
        return impl

    @staticmethod
    def get_storage_config_implementation(storage_type: types.Storage):
        _storage_implementations = {types.Storage.MINIO: config.MinioConfig}
        impl = _storage_implementations.get(storage_type)
        assert impl
        return impl

    @staticmethod
    def get_nosql_config_implementation(storage_type: types.NoSQLStorage):
        _storage_implementations = {types.NoSQLStorage.SCYLLADB: config.ScyllaDBConfig}
        impl = _storage_implementations.get(storage_type)
        assert impl
        return impl

    def shutdown(self):
        self.cache_client.shutdown()

    def __enter__(self):
        return self

    def __exit__(self):
        self.shutdown()
