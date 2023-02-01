import docker
import os
import logging
import re
import shutil
import time
import math
import zipfile
from datetime import datetime, timezone
from typing import cast, Dict, Optional, Tuple, List, Type

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import monitoring_v3

from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.benchmark import Benchmark
from ..faas.function import Function, FunctionConfig, Trigger
from .storage import PersistentStorage
from ..faas.system import System
from sebs.gcp.config import GCPConfig
from sebs.gcp.storage import GCPStorage
from sebs.gcp.function import GCPFunction
from sebs.utils import LoggingHandlers
from sebs.types import Language

"""
    This class provides basic abstractions for the FaaS system.
    It provides the interface for initialization of the system and storage
    services, creation and update of serverless functions and querying
    logging and measurements services to obtain error messages and performance
    measurements.
"""


class GCP(System):
    def __init__(
        self,
        system_config: SeBSConfig,
        config: GCPConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logging_handlers: LoggingHandlers,
    ):
        super().__init__(system_config, cache_client, docker_client)
        self._config = config
        self.storage: Optional[GCPStorage] = None
        self.logging_handlers = logging_handlers

    @property
    def config(self) -> GCPConfig:
        return self._config

    @staticmethod
    def name():
        return "gcp"

    @staticmethod
    def typename():
        return "GCP"

    @staticmethod
    def function_type() -> "Type[Function]":
        return GCPFunction

    """
        Initialize the system. After the call the local or remote
        FaaS system should be ready to allocate functions, manage
        storage resources and invoke functions.

        :param config: systems-specific parameters
    """

    def initialize(self, config: Dict[str, str] = {}):
        self.function_client = build("cloudfunctions", "v1", cache_discovery=False)
        self.get_storage()

    def get_function_client(self):
        return self.function_client

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    def get_storage(
        self,
        replace_existing: bool = False,
        benchmark=None,
        buckets=None,
    ) -> PersistentStorage:
        if not self.storage:
            self.storage = GCPStorage(self.config.region, self.cache_client, replace_existing)
            self.storage.logging_handlers = self.logging_handlers
        else:
            self.storage.replace_existing = replace_existing
        return self.storage

    @staticmethod
    def default_function_name(code_package: Benchmark) -> str:
        # Create function name
        func_name = "{}-{}-{}".format(
            code_package.benchmark, code_package.language_name, code_package.language_version
        )
        return GCP.format_function_name(func_name)

    @staticmethod
    def format_function_name(func_name: str) -> str:
        # GCP functions must begin with a letter
        func_name = func_name.replace("-", "_")
        func_name = func_name.replace(".", "_")
        return f"function-{func_name}"

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

    def package_code(
        self,
        directory: str,
        language: Language,
        language_version: str,
        benchmark: str,
        is_cached: bool,
    ) -> Tuple[str, int]:

        CONFIG_FILES = {
            Language.PYTHON: ["handler.py", ".python_packages"],
            Language.NODEJS: ["handler.js", "node_modules"],
        }
        HANDLER = {
            Language.PYTHON: ("handler.py", "main.py"),
            Language.NODEJS: ("handler.js", "index.js"),
        }
        package_config = CONFIG_FILES[language]
        function_dir = os.path.join(directory, "function")
        os.makedirs(function_dir)
        for file in os.listdir(directory):
            if file not in package_config:
                file = os.path.join(directory, file)
                shutil.move(file, function_dir)

        requirements = open(os.path.join(directory, "requirements.txt"), "w")
        requirements.write("google-cloud-storage")
        requirements.close()

        # rename handler function.py since in gcp it has to be caled main.py
        old_name, new_name = HANDLER[language]
        old_path = os.path.join(directory, old_name)
        new_path = os.path.join(directory, new_name)
        shutil.move(old_path, new_path)

        """
            zip the whole directroy (the zip-file gets uploaded to gcp later)

            Note that the function GCP.recusive_zip is slower than the use of e.g.
            `utils.execute("zip -qu -r9 {}.zip * .".format(benchmark), shell=True)`
            or `shutil.make_archive(benchmark_archive, direcory, directory)`
            But both of the two alternatives need a chance of directory
            (shutil.make_archive does the directorychange internaly)
            which leads to a "race condition" when running several benchmarks
            in parallel, since a change of the current directory is NOT Thread specfic.
        """
        benchmark_archive = "{}.zip".format(os.path.join(directory, benchmark))
        GCP.recursive_zip(directory, benchmark_archive)
        logging.info("Created {} archive".format(benchmark_archive))

        bytes_size = os.path.getsize(benchmark_archive)
        mbytes = bytes_size / 1024.0 / 1024.0
        logging.info("Zip archive size {:2f} MB".format(mbytes))

        # rename the main.py back to handler.py
        shutil.move(new_path, old_path)

        return os.path.join(directory, "{}.zip".format(benchmark)), bytes_size

    def create_function(self, code_package: Benchmark, func_name: str) -> "GCPFunction":

        package = code_package.code_location
        benchmark = code_package.benchmark
        language_runtime = code_package.language_version
        timeout = code_package.benchmark_config.timeout
        memory = code_package.benchmark_config.memory
        code_bucket: Optional[str] = None
        storage_client = self.get_storage()
        location = self.config.region
        project_name = self.config.project_name
        function_cfg = FunctionConfig.from_benchmark(code_package)

        code_package_name = cast(str, os.path.basename(package))
        code_bucket, idx = storage_client.add_input_bucket(benchmark)
        storage_client.upload(code_bucket, package, code_package_name)
        self.logging.info("Uploading function {} code to {}".format(func_name, code_bucket))

        full_func_name = GCP.get_full_function_name(project_name, location, func_name)
        get_req = self.function_client.projects().locations().functions().get(name=full_func_name)

        try:
            get_req.execute()
        except HttpError:
            create_req = (
                self.function_client.projects()
                .locations()
                .functions()
                .create(
                    location="projects/{project_name}/locations/{location}".format(
                        project_name=project_name, location=location
                    ),
                    body={
                        "name": full_func_name,
                        "entryPoint": "handler",
                        "runtime": code_package.language_name + language_runtime.replace(".", ""),
                        "availableMemoryMb": memory,
                        "timeout": str(timeout) + "s",
                        "httpsTrigger": {},
                        "ingressSettings": "ALLOW_ALL",
                        "sourceArchiveUrl": "gs://" + code_bucket + "/" + code_package_name,
                    },
                )
            )
            create_req.execute()
            self.logging.info(f"Function {func_name} has been created!")
            allow_unauthenticated_req = (
                self.function_client.projects()
                .locations()
                .functions()
                .setIamPolicy(
                    resource=full_func_name,
                    body={
                        "policy": {
                            "bindings": [
                                {"role": "roles/cloudfunctions.invoker", "members": ["allUsers"]}
                            ]
                        }
                    },
                )
            )
            allow_unauthenticated_req.execute()
            self.logging.info(f"Function {func_name} accepts now unauthenticated invocations!")

            function = GCPFunction(
                func_name, benchmark, code_package.hash, function_cfg, code_bucket
            )
        else:
            # if result is not empty, then function does exists
            self.logging.info("Function {} exists on GCP, update the instance.".format(func_name))

            function = GCPFunction(
                name=func_name,
                benchmark=benchmark,
                code_package_hash=code_package.hash,
                cfg=function_cfg,
                bucket=code_bucket,
            )
            self.update_function(function, code_package)

        # Add LibraryTrigger to a new function
        from sebs.gcp.triggers import LibraryTrigger

        trigger = LibraryTrigger(func_name, self)
        trigger.logging_handlers = self.logging_handlers
        function.add_trigger(trigger)

        return function

    def create_trigger(self, function: Function, trigger_type: Trigger.TriggerType) -> Trigger:
        from sebs.gcp.triggers import HTTPTrigger

        if trigger_type == Trigger.TriggerType.HTTP:

            location = self.config.region
            project_name = self.config.project_name
            full_func_name = GCP.get_full_function_name(project_name, location, function.name)
            self.logging.info(f"Function {function.name} - waiting for deployment...")
            our_function_req = (
                self.function_client.projects().locations().functions().get(name=full_func_name)
            )
            deployed = False
            while not deployed:
                status_res = our_function_req.execute()
                if status_res["status"] == "ACTIVE":
                    deployed = True
                else:
                    time.sleep(3)
            self.logging.info(f"Function {function.name} - deployed!")
            invoke_url = status_res["httpsTrigger"]["url"]

            trigger = HTTPTrigger(invoke_url)
        else:
            raise RuntimeError("Not supported!")

        trigger.logging_handlers = self.logging_handlers
        function.add_trigger(trigger)
        self.cache_client.update_function(function)
        return trigger

    def cached_function(self, function: Function):

        from sebs.faas.function import Trigger
        from sebs.gcp.triggers import LibraryTrigger

        for trigger in function.triggers(Trigger.TriggerType.LIBRARY):
            gcp_trigger = cast(LibraryTrigger, trigger)
            gcp_trigger.logging_handlers = self.logging_handlers
            gcp_trigger.deployment_client = self

    def update_function(self, function: Function, code_package: Benchmark):

        function = cast(GCPFunction, function)
        language_runtime = code_package.language_version
        code_package_name = os.path.basename(code_package.code_location)
        storage = cast(GCPStorage, self.get_storage())

        bucket = function.code_bucket(code_package.benchmark, storage)
        storage.upload(bucket, code_package.code_location, code_package_name)
        self.logging.info(f"Uploaded new code package to {bucket}/{code_package_name}")
        full_func_name = GCP.get_full_function_name(
            self.config.project_name, self.config.region, function.name
        )
        req = (
            self.function_client.projects()
            .locations()
            .functions()
            .patch(
                name=full_func_name,
                body={
                    "name": full_func_name,
                    "entryPoint": "handler",
                    "runtime": code_package.language_name + language_runtime.replace(".", ""),
                    "availableMemoryMb": function.config.memory,
                    "timeout": str(function.config.timeout) + "s",
                    "httpsTrigger": {},
                    "sourceArchiveUrl": "gs://" + bucket + "/" + code_package_name,
                },
            )
        )
        res = req.execute()
        versionId = res["metadata"]["versionId"]
        while True:
            if not self.is_deployed(function.name, versionId):
                time.sleep(5)
            else:
                break
        self.logging.info("Published new function code and configuration.")

    def update_function_configuration(self, function: Function, benchmark: Benchmark):
        function = cast(GCPFunction, function)
        full_func_name = GCP.get_full_function_name(
            self.config.project_name, self.config.region, function.name
        )
        req = (
            self.function_client.projects()
            .locations()
            .functions()
            .patch(
                name=full_func_name,
                updateMask="availableMemoryMb,timeout",
                body={
                    "availableMemoryMb": function.config.memory,
                    "timeout": str(function.config.timeout) + "s",
                },
            )
        )
        res = req.execute()
        versionId = res["metadata"]["versionId"]
        while True:
            if not self.is_deployed(function.name, versionId):
                time.sleep(5)
            else:
                break
        self.logging.info("Published new function configuration.")

    @staticmethod
    def get_full_function_name(project_name: str, location: str, func_name: str):
        return f"projects/{project_name}/locations/{location}/functions/{func_name}"

    def prepare_experiment(self, benchmark):
        logs_bucket = self.storage.add_output_bucket(benchmark, suffix="logs")
        return logs_bucket

    def shutdown(self) -> None:
        super().shutdown()

    def download_metrics(
        self, function_name: str, start_time: int, end_time: int, requests: dict, metrics: dict
    ):

        from google.api_core import exceptions
        from time import sleep

        def wrapper(gen):
            while True:
                try:
                    yield next(gen)
                except StopIteration:
                    break
                except exceptions.ResourceExhausted:
                    self.logging.info("Google Cloud resources exhausted, sleeping 30s")
                    sleep(30)

        """
            Use GCP's logging system to find execution time of each function invocation.

            There shouldn't be problem of waiting for complete results,
            since logs appear very quickly here.
        """
        from google.cloud import logging as gcp_logging

        logging_client = gcp_logging.Client()
        logger = logging_client.logger("cloudfunctions.googleapis.com%2Fcloud-functions")

        """
            GCP accepts only single date format: 'YYYY-MM-DDTHH:MM:SSZ'.
            Thus, we first convert timestamp to UTC timezone.
            Then, we generate correct format.

            Add 1 second to end time to ensure that removing
            milliseconds doesn't affect query.
        """
        timestamps = []
        for timestamp in [start_time, end_time + 1]:
            utc_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            timestamps.append(utc_date.strftime("%Y-%m-%dT%H:%M:%SZ"))

        invocations = logger.list_entries(
            filter_=(
                f'resource.labels.function_name = "{function_name}" '
                f'timestamp >= "{timestamps[0]}" '
                f'timestamp <= "{timestamps[1]}"'
            ),
            page_size=1000,
        )
        invocations_processed = 0
        if hasattr(invocations, "pages"):
            pages = list(wrapper(invocations.pages))
        else:
            pages = [list(wrapper(invocations))]
        entries = 0
        for page in pages:  # invocations.pages:
            for invoc in page:
                entries += 1
                if "execution took" in invoc.payload:
                    execution_id = invoc.labels["execution_id"]
                    # might happen that we get invocation from another experiment
                    if execution_id not in requests:
                        continue
                    # find number of miliseconds
                    regex_result = re.search(r"\d+ ms", invoc.payload)
                    assert regex_result
                    exec_time = regex_result.group().split()[0]
                    # convert into microseconds
                    requests[execution_id].provider_times.execution = int(exec_time) * 1000
                    invocations_processed += 1
        self.logging.info(
            f"GCP: Received {entries} entries, found time metrics for {invocations_processed} "
            f"out of {len(requests.keys())} invocations."
        )

        """
            Use metrics to find estimated values for maximum memory used, active instances
            and network traffic.
            https://cloud.google.com/monitoring/api/metrics_gcp#gcp-cloudfunctions
        """

        # Set expected metrics here
        available_metrics = ["execution_times", "user_memory_bytes", "network_egress"]

        client = monitoring_v3.MetricServiceClient()
        project_name = client.common_project_path(self.config.project_name)

        end_time_nanos, end_time_seconds = math.modf(end_time)
        start_time_nanos, start_time_seconds = math.modf(start_time)

        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(end_time_seconds) + 60},
                "start_time": {"seconds": int(start_time_seconds)},
            }
        )

        for metric in available_metrics:

            metrics[metric] = []

            list_request = monitoring_v3.ListTimeSeriesRequest(
                name=project_name,
                filter='metric.type = "cloudfunctions.googleapis.com/function/{}"'.format(metric),
                interval=interval,
            )

            results = client.list_time_series(list_request)
            for result in results:
                if result.resource.labels.get("function_name") == function_name:
                    for point in result.points:
                        metrics[metric] += [
                            {
                                "mean_value": point.value.distribution_value.mean,
                                "executions_count": point.value.distribution_value.count,
                            }
                        ]

    def _enforce_cold_start(self, function: Function):

        name = GCP.get_full_function_name(
            self.config.project_name, self.config.region, function.name
        )
        self.cold_start_counter += 1
        req = (
            self.function_client.projects()
            .locations()
            .functions()
            .patch(
                name=name,
                updateMask="environmentVariables",
                body={"environmentVariables": {"cold_start": str(self.cold_start_counter)}},
            )
        )
        res = req.execute()
        new_version = res["metadata"]["versionId"]

        return new_version

    def enforce_cold_start(self, functions: List[Function], code_package: Benchmark):

        new_versions = []
        for func in functions:
            new_versions.append((self._enforce_cold_start(func), func))
            self.cold_start_counter -= 1

        # verify deployment
        undeployed_functions = []
        deployment_done = False
        while not deployment_done:
            for versionId, func in new_versions:
                if not self.is_deployed(func.name, versionId):
                    undeployed_functions.append((versionId, func))
            deployed = len(new_versions) - len(undeployed_functions)
            self.logging.info(f"Redeployed {deployed} out of {len(new_versions)}")
            if deployed == len(new_versions):
                deployment_done = True
                break
            time.sleep(5)
            new_versions = undeployed_functions
            undeployed_functions = []

        self.cold_start_counter += 1

    def get_functions(self, code_package: Benchmark, function_names: List[str]) -> List["Function"]:

        functions: List["Function"] = []
        undeployed_functions_before = []
        for func_name in function_names:
            func = self.get_function(code_package, func_name)
            functions.append(func)
            undeployed_functions_before.append(func)

        # verify deployment
        undeployed_functions = []
        deployment_done = False
        while not deployment_done:
            for func in undeployed_functions_before:
                if not self.is_deployed(func.name):
                    undeployed_functions.append(func)
            deployed = len(undeployed_functions_before) - len(undeployed_functions)
            self.logging.info(f"Deployed {deployed} out of {len(undeployed_functions_before)}")
            if deployed == len(undeployed_functions_before):
                deployment_done = True
                break
            time.sleep(5)
            undeployed_functions_before = undeployed_functions
            undeployed_functions = []
            self.logging.info(f"Waiting on {undeployed_functions_before}")

        return functions

    def is_deployed(self, func_name: str, versionId: int = -1) -> bool:
        name = GCP.get_full_function_name(self.config.project_name, self.config.region, func_name)
        function_client = self.get_function_client()
        status_req = function_client.projects().locations().functions().get(name=name)
        status_res = status_req.execute()
        if versionId == -1:
            return status_res["status"] == "ACTIVE"
        else:
            return status_res["versionId"] == versionId

    def deployment_version(self, func: Function) -> int:
        name = GCP.get_full_function_name(self.config.project_name, self.config.region, func.name)
        function_client = self.get_function_client()
        status_req = function_client.projects().locations().functions().get(name=name)
        status_res = status_req.execute()
        return int(status_res["versionId"])

    # @abstractmethod
    # def get_invocation_error(self, function_name: str,
    #   start_time: int, end_time: int):
    #    pass

    # @abstractmethod
    # def download_metrics(self):
    #    pass

    """
       Helper method for recursive_zip

       :param base_directory: path to directory to be zipped
       :param path: path to file of subdirecotry to be zipped
       :param archive: ZipFile object
    """

    @staticmethod
    def helper_zip(base_directory: str, path: str, archive: zipfile.ZipFile):
        paths = os.listdir(path)
        for p in paths:
            directory = os.path.join(path, p)
            if os.path.isdir(directory):
                GCP.helper_zip(base_directory, directory, archive)
            else:
                if directory != archive.filename:  # prevent form including itself
                    archive.write(directory, os.path.relpath(directory, base_directory))

    """
       https://gist.github.com/felixSchl/d38b455df8bf83a78d3d

       Zip directory with relative paths given an absolute path
       If the archive exists only new files are added and updated.
       If the archive does not exist a new one is created.

       :param path: absolute path to the direcotry to be zipped
       :param archname: path to the zip file
    """

    @staticmethod
    def recursive_zip(directory: str, archname: str):
        archive = zipfile.ZipFile(archname, "w", zipfile.ZIP_DEFLATED, compresslevel=9)
        if os.path.isdir(directory):
            GCP.helper_zip(directory, directory, archive)
        else:
            # if the passed direcotry is acually a file we just add the file to the zip archive
            _, name = os.path.split(directory)
            archive.write(directory, name)
        archive.close()
        return True
