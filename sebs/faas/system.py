from abc import ABC
from abc import abstractmethod
from random import randrange
from typing import Dict, List, Optional, Tuple, Type

import docker

from sebs.benchmark import Benchmark
from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.faas.function import Function, Trigger, ExecutionResult
from sebs.faas.storage import PersistentStorage
from sebs.utils import LoggingBase
from .config import Config

"""
    This class provides basic abstractions for the FaaS system.
    It provides the interface for initialization of the system and storage
    services, creation and update of serverless functions and querying
    logging and measurements services to obtain error messages and performance
    measurements.
"""


class System(ABC, LoggingBase):
    def __init__(
        self,
        system_config: SeBSConfig,
        cache_client: Cache,
        docker_client: docker.client,
    ):
        super().__init__()
        self._system_config = system_config
        self._docker_client = docker_client
        self._cache_client = cache_client
        self._cold_start_counter = randrange(100)

    @property
    def system_config(self) -> SeBSConfig:
        return self._system_config

    @property
    def docker_client(self) -> docker.client:
        return self._docker_client

    @property
    def cache_client(self) -> Cache:
        return self._cache_client

    @property
    def cold_start_counter(self) -> int:
        return self._cold_start_counter

    @cold_start_counter.setter
    def cold_start_counter(self, val: int):
        self._cold_start_counter = val

    @property
    @abstractmethod
    def config(self) -> Config:
        pass

    @staticmethod
    @abstractmethod
    def function_type() -> "Type[Function]":
        pass

    """
        Initialize the system. After the call the local or remot
        FaaS system should be ready to allocate functions, manage
        storage resources and invoke functions.

        :param config: systems-specific parameters
    """

    def initialize(self, config: Dict[str, str] = {}):
        pass

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    @abstractmethod
    def get_storage(self, replace_existing: bool) -> PersistentStorage:
        pass

    """
        Apply the system-specific code packaging routine to build benchmark.
        The benchmark creates a code directory with the following structure:
        - [benchmark sources]
        - [benchmark resources]
        - [dependence specification], e.g. requirements.txt or package.json
        - [handlers implementation for the language and deployment]

        This step allows us to change the structure above to fit different
        deployment requirements, Example: a zip file for AWS or a specific
        directory structure for Azure.

        :return: path to packaged code and its size
    """

    @abstractmethod
    def package_code(self, directory: str, language_name: str,  language_version: str, benchmark: str) -> Tuple[str, int]:
        pass

    @abstractmethod
    def create_function(self, code_package: Benchmark, func_name: str) -> Function:
        pass

    @abstractmethod
    def cached_function(self, function: Function):
        pass

    @abstractmethod
    def update_function(self, function: Function, code_package: Benchmark):
        pass

    """
        a)  if a cached function with given name is present and code has not changed,
            then just return function name
        b)  if a cached function is present and the cloud code has a different
            code version, then upload new code
        c)  if no cached function is present, then create code package and
            either create new function or update an existing but uncached one

        Benchmark rebuild is requested but will be skipped if source code is
        not changed and user didn't request update.

    """

    def get_function(self, code_package: Benchmark, func_name: Optional[str] = None) -> Function:

        if code_package.language_version not in self.system_config.supported_language_versions(
            self.name(), code_package.language_name
        ):
            raise Exception(
                "Unsupported {language} version {version} in {system}!".format(
                    language=code_package.language_name,
                    version=code_package.language_version,
                    system=self.name(),
                )
            )

        if not func_name:
            func_name = self.default_function_name(code_package)
        rebuilt, _ = code_package.build(self.package_code)

        """
            There's no function with that name?
            a) yes -> create new function. Implementation might check if a function
            with that name already exists in the cloud and update its code.
            b) no -> retrieve function from the cache. Function code in cloud will
            be updated if the local version is different.
        """
        functions = code_package.functions
        if not functions or func_name not in functions:
            msg = (
                "function name not provided."
                if not func_name
                else "function {} not found in cache.".format(func_name)
            )
            self.logging.info("Creating new function! Reason: " + msg)
            function = self.create_function(code_package, func_name)
            self.cache_client.add_function(
                deployment_name=self.name(),
                language_name=code_package.language_name,
                code_package=code_package,
                function=function,
            )
            code_package.query_cache()
            return function
        else:
            # retrieve function
            cached_function = functions[func_name]
            code_location = code_package.code_location
            function = self.function_type().deserialize(cached_function)
            self.cached_function(function)
            self.logging.info(
                "Using cached function {fname} in {loc}".format(fname=func_name, loc=code_location)
            )
            # is the function up-to-date?
            if function.code_package_hash != code_package.hash or rebuilt:
                self.logging.info(
                    f"Cached function {func_name} with hash "
                    f"{function.code_package_hash} is not up to date with "
                    f"current build {code_package.hash} in "
                    f"{code_location}, updating cloud version!"
                )
                self.update_function(function, code_package)
                function.code_package_hash = code_package.hash
                function.updated_code = True
                self.cache_client.add_function(
                    deployment_name=self.name(),
                    language_name=code_package.language_name,
                    code_package=code_package,
                    function=function,
                )
                code_package.query_cache()
            return function

    @abstractmethod
    def default_function_name(self, code_package: Benchmark) -> str:
        pass

    @abstractmethod
    def enforce_cold_start(self, functions: List[Function], code_package: Benchmark):
        pass

    @abstractmethod
    def download_metrics(
        self,
        function_name: str,
        start_time: int,
        end_time: int,
        requests: Dict[str, ExecutionResult],
        metrics: dict,
    ):
        pass

    @abstractmethod
    def create_trigger(self, function: Function, trigger_type: Trigger.TriggerType) -> Trigger:
        pass

    # @abstractmethod
    # def get_invocation_error(self, function_name: str,
    #   start_time: int, end_time: int):
    #    pass

    """
        Shutdown local FaaS instances, connections and clients.
    """

    @abstractmethod
    def shutdown(self) -> None:
        try:
            self.cache_client.lock()
            self.config.update_cache(self.cache_client)
        finally:
            self.cache_client.unlock()

    @staticmethod
    @abstractmethod
    def name() -> str:
        pass
