from abc import ABC
from abc import abstractmethod
from random import randrange
from typing import Dict, List, Optional, Tuple, Type
import uuid

import docker

from sebs.benchmark import Benchmark
from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.faas.config import Resources
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

    def find_deployments(self) -> List[str]:

        """
        Default implementation that uses storage buckets.
        data storage accounts.
        This can be overriden, e.g., in Azure that looks for unique
        """

        return self.get_storage().find_deployments()

    def initialize_resources(self, select_prefix: Optional[str]):

        # User provided resources or found in cache
        if self.config.resources.has_resources_id:
            self.logging.info(
                f"Using existing resource name: {self.config.resources.resources_id}."
            )
            return

        # Now search for existing resources
        deployments = self.find_deployments()

        # If a prefix is specified, we find the first matching resource ID
        if select_prefix is not None:

            for dep in deployments:
                if select_prefix in dep:
                    self.logging.info(
                        f"Using existing deployment {dep} that matches prefix {select_prefix}!"
                    )
                    self.config.resources.resources_id = dep
                    return

        # We warn users that we create a new resource ID
        # They can use them with a new config
        if len(deployments) > 0:
            self.logging.warning(
                f"We found {len(deployments)} existing deployments! "
                "If you want to use any of them, please abort, and "
                "provide the resource id in your input config."
            )
            self.logging.warning("Deployment resource IDs in the cloud: " f"{deployments}")

        # create
        res_id = ""
        if select_prefix is not None:
            res_id = f"{select_prefix}-{str(uuid.uuid1())[0:8]}"
        else:
            res_id = str(uuid.uuid1())[0:8]
        self.config.resources.resources_id = res_id
        self.logging.info(f"Generating unique resource name {res_id}")
        # ensure that the bucket is created - this allocates the new resource
        self.get_storage().get_bucket(Resources.StorageBucketType.BENCHMARKS)

    """
        Initialize the system. After the call the local or remote
        FaaS system should be ready to allocate functions, manage
        storage resources and invoke functions.

        :param config: systems-specific parameters
    """

    def initialize(self, config: Dict[str, str] = {}, resource_prefix: Optional[str] = None):
        pass

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    @abstractmethod
    def get_storage(self, replace_existing: bool = False) -> PersistentStorage:
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

        Args:
            directory: Path to the code directory
            language_name: Programming language name
            language_version: Programming language version
            architecture: Target architecture (e.g., 'x64', 'arm64')
            benchmark: Benchmark name
            is_cached: Whether the code is cached
            container_deployment: Whether to package for container deployment

        Returns:
            Tuple containing:
            - Path to packaged code
            - Size of the package
            - Container URI
    """

    @abstractmethod
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
        pass

    @abstractmethod
    def create_function(
        self,
        code_package: Benchmark,
        func_name: str,
        container_deployment: bool,
        container_uri: str,
    ) -> Function:

        """
        Create a new function in the FaaS platform.
        The implementation is responsible for creating all necessary
        cloud resources.

        Args:
            code_package: Benchmark containing the function code
            func_name: Name of the function
            container_deployment: Whether to deploy as a container
            container_uri: URI of the container image

        Returns:
            Function: Created function instance

        Raises:
            NotImplementedError: If container deployment is requested but not supported
        """
        pass

    @abstractmethod
    def cached_function(self, function: Function):
        pass

    @abstractmethod
    def update_function(
        self,
        function: Function,
        code_package: Benchmark,
        container_deployment: bool,
        container_uri: str,
    ):
        """
        Update an existing function in the FaaS platform.

        Args:
            function: Existing function instance to update
            code_package: New benchmark containing the function code
            container_deployment: Whether to deploy as a container
            container_uri: URI of the container image

        Raises:
            NotImplementedError: If container deployment is requested but not supported
        """
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
            self.name(), code_package.language_name, code_package.architecture
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
        rebuilt, _, container_deployment, container_uri = code_package.build(self.package_code)

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
            function = self.create_function(
                code_package, func_name, container_deployment, container_uri
            )
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
                if function.code_package_hash != code_package.hash:
                    self.logging.info(
                        f"Cached function {func_name} with hash "
                        f"{function.code_package_hash} is not up to date with "
                        f"current build {code_package.hash} in "
                        f"{code_location}, updating cloud version!"
                    )
                if rebuilt:
                    self.logging.info(
                        f"Enforcing rebuild and update of of cached function "
                        f"{func_name} with hash {function.code_package_hash}."
                    )
                self.update_function(function, code_package, container_deployment, container_uri)
                function.code_package_hash = code_package.hash
                function.updated_code = True
                self.cache_client.add_function(
                    deployment_name=self.name(),
                    language_name=code_package.language_name,
                    code_package=code_package,
                    function=function,
                )
                code_package.query_cache()
            # code up to date, but configuration needs to be updated
            # FIXME: detect change in function config
            elif self.is_configuration_changed(function, code_package):
                self.update_function_configuration(function, code_package)
                self.cache_client.update_function(function)
                code_package.query_cache()
            else:
                self.logging.info(f"Cached function {func_name} is up to date.")
            return function

    @abstractmethod
    def update_function_configuration(self, cached_function: Function, benchmark: Benchmark):
        pass

    """
        This function checks for common function parameters to verify if their value is
        still up to date.
    """

    def is_configuration_changed(self, cached_function: Function, benchmark: Benchmark) -> bool:

        changed = False
        for attr in ["timeout", "memory"]:
            new_val = getattr(benchmark.benchmark_config, attr)
            old_val = getattr(cached_function.config, attr)
            if new_val != old_val:
                self.logging.info(
                    f"Updating function configuration due to changed attribute {attr}: "
                    f"cached function has value {old_val} whereas {new_val} has been requested."
                )
                changed = True
                setattr(cached_function.config, attr, new_val)

        for lang_attr in [["language"] * 2, ["language_version", "version"]]:
            new_val = getattr(benchmark, lang_attr[0])
            old_val = getattr(cached_function.config.runtime, lang_attr[1])
            if new_val != old_val:
                # FIXME: should this even happen? we should never pick the function with
                # different runtime - that should be encoded in the name
                self.logging.info(
                    f"Updating function configuration due to changed runtime attribute {attr}: "
                    f"cached function has value {old_val} whereas {new_val} has been requested."
                )
                changed = True
                setattr(cached_function.config.runtime, lang_attr[1], new_val)

        return changed

    @abstractmethod
    def default_function_name(
        self, code_package: Benchmark, resources: Optional[Resources] = None
    ) -> str:
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

    def disable_rich_output(self):
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
