import math
import os
import shutil
import time
import uuid
from typing import cast, Dict, List, Optional, Tuple, Type, Union  # noqa

import boto3
import docker

from sebs.aws.s3 import S3
from sebs.aws.function import LambdaFunction
from sebs.aws.config import AWSConfig
from sebs.utils import execute
from sebs.benchmark import Benchmark
from sebs.cache import Cache
from sebs.config import SeBSConfig
from sebs.utils import LoggingHandlers
from sebs.faas.function import Function, ExecutionResult, Trigger, FunctionConfig
from sebs.faas.storage import PersistentStorage
from sebs.faas.system import System
from sebs.types import Language


class AWS(System):
    logs_client = None
    cached = False
    _config: AWSConfig

    @staticmethod
    def name():
        return "aws"

    @staticmethod
    def typename():
        return "AWS"

    @staticmethod
    def function_type() -> "Type[Function]":
        return LambdaFunction

    @property
    def config(self) -> AWSConfig:
        return self._config

    """
        :param cache_client: Function cache instance
        :param config: Experiments config
        :param docker_client: Docker instance
    """

    def __init__(
        self,
        sebs_config: SeBSConfig,
        config: AWSConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logger_handlers: LoggingHandlers,
    ):
        super().__init__(sebs_config, cache_client, docker_client)
        self.logging_handlers = logger_handlers
        self._config = config
        self.storage: Optional[S3] = None

    def initialize(self, config: Dict[str, str] = {}):
        # thread-safe
        self.session = boto3.session.Session(
            aws_access_key_id=self.config.credentials.access_key,
            aws_secret_access_key=self.config.credentials.secret_key,
        )
        self.get_lambda_client()
        self.get_storage()

    def get_lambda_client(self):
        if not hasattr(self, "client"):
            self.client = self.session.client(
                service_name="lambda",
                region_name=self.config.region,
            )
        return self.client

    """
        Create a client instance for cloud storage. When benchmark and buckets
        parameters are passed, then storage is initialized with required number
        of buckets. Buckets may be created or retrieved from cache.

        :param benchmark: benchmark name
        :param buckets: tuple of required input/output buckets
        :param replace_existing: replace existing files in cached buckets?
        :return: storage client
    """

    def get_storage(self, replace_existing: bool = False) -> PersistentStorage:
        if not self.storage:
            self.storage = S3(
                self.session,
                self.cache_client,
                self.config.region,
                access_key=self.config.credentials.access_key,
                secret_key=self.config.credentials.secret_key,
                replace_existing=replace_existing,
            )
            self.storage.logging_handlers = self.logging_handlers
        else:
            self.storage.replace_existing = replace_existing
        return self.storage

    """
        It would be sufficient to just pack the code and ship it as zip to AWS.
        However, to have a compatible function implementation across providers,
        we create a small module.
        Issue: relative imports in Python when using storage wrapper.
        Azure expects a relative import inside a module thus it's easier
        to always create a module.

        Structure:
        function
        - function.py
        - storage.py
        - resources
        handler.py

        benchmark: benchmark name
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
            Language.PYTHON: ["handler.py", "requirements.txt", ".python_packages"],
            Language.NODEJS: ["handler.js", "package.json", "node_modules"],
        }

        if language in [Language.PYTHON, Language.NODEJS]:
            package_config = CONFIG_FILES[language]
            function_dir = os.path.join(directory, "function")
            os.makedirs(function_dir)
            # move all files to 'function' except handler.py
            for file in os.listdir(directory):
                if file not in package_config:
                    file = os.path.join(directory, file)
                    shutil.move(file, function_dir)

            # FIXME: use zipfile
            # create zip with hidden directory but without parent directory
            execute("zip -qu -r9 {}.zip * .".format(benchmark), shell=True, cwd=directory)
            benchmark_archive = "{}.zip".format(os.path.join(directory, benchmark))
            self.logging.info("Created {} archive".format(benchmark_archive))

            bytes_size = os.path.getsize(os.path.join(directory, benchmark_archive))
            mbytes = bytes_size / 1024.0 / 1024.0
            self.logging.info("Zip archive size {:2f} MB".format(mbytes))

            return os.path.join(directory, "{}.zip".format(benchmark)), bytes_size
        elif language == Language.CPP:

            # lambda C++ runtime build scripts create the .zip file in build directory
            benchmark_archive = os.path.join(directory, "build", "benchmark.zip")
            self.logging.info("Created {} archive".format(benchmark_archive))

            bytes_size = os.path.getsize(os.path.join(directory, benchmark_archive))
            mbytes = bytes_size / 1024.0 / 1024.0
            self.logging.info("Zip archive size {:2f} MB".format(mbytes))

            return benchmark_archive, bytes_size
        else:
            raise NotImplementedError()

    def create_function(self, code_package: Benchmark, func_name: str) -> "LambdaFunction":

        package = code_package.code_location
        benchmark = code_package.benchmark
        language = code_package.language
        language_runtime = code_package.language_version
        timeout = code_package.benchmark_config.timeout
        memory = code_package.benchmark_config.memory
        code_size = code_package.code_size
        code_bucket: Optional[str] = None
        func_name = AWS.format_function_name(func_name)
        storage_client = self.get_storage()
        function_cfg = FunctionConfig.from_benchmark(code_package)

        # we can either check for exception or use list_functions
        # there's no API for test
        try:
            ret = self.client.get_function(FunctionName=func_name)
            self.logging.info(
                "Function {} exists on AWS, retrieve configuration.".format(func_name)
            )
            # Here we assume a single Lambda role
            lambda_function = LambdaFunction(
                func_name,
                code_package.benchmark,
                ret["Configuration"]["FunctionArn"],
                code_package.hash,
                language_runtime,
                self.config.resources.lambda_role(self.session),
                function_cfg,
            )
            self.update_function(lambda_function, code_package)
            lambda_function.updated_code = True
            # TODO: get configuration of REST API
        except self.client.exceptions.ResourceNotFoundException:
            self.logging.info("Creating function {} from {}".format(func_name, package))

            # AWS Lambda limit on zip deployment size
            # Limit to 50 MB
            # mypy doesn't recognize correctly the case when the same
            # variable has different types across the path
            code_config: Dict[str, Union[str, bytes]]
            if code_size < 50 * 1024 * 1024:
                package_body = open(package, "rb").read()
                code_config = {"ZipFile": package_body}
            # Upload code package to S3, then use it
            else:
                code_package_name = cast(str, os.path.basename(package))
                code_bucket, idx = storage_client.add_input_bucket(benchmark)
                storage_client.upload(code_bucket, package, code_package_name)
                self.logging.info("Uploading function {} code to {}".format(func_name, code_bucket))
                code_config = {"S3Bucket": code_bucket, "S3Key": code_package_name}
            ret = self.client.create_function(
                FunctionName=func_name,
                Runtime=self.cloud_runtime(language, language_runtime),
                Handler="handler.handler",
                Role=self.config.resources.lambda_role(self.session),
                MemorySize=memory,
                Timeout=timeout,
                Code=code_config,
            )

            lambda_function = LambdaFunction(
                func_name,
                code_package.benchmark,
                ret["FunctionArn"],
                code_package.hash,
                language_runtime,
                self.config.resources.lambda_role(self.session),
                function_cfg,
                code_bucket,
            )

            self.wait_function_active(lambda_function)

        # Add LibraryTrigger to a new function
        from sebs.aws.triggers import LibraryTrigger

        trigger = LibraryTrigger(func_name, self)
        trigger.logging_handlers = self.logging_handlers
        lambda_function.add_trigger(trigger)

        return lambda_function

    def cached_function(self, function: Function):

        from sebs.aws.triggers import LibraryTrigger

        for trigger in function.triggers(Trigger.TriggerType.LIBRARY):
            trigger.logging_handlers = self.logging_handlers
            cast(LibraryTrigger, trigger).deployment_client = self
        for trigger in function.triggers(Trigger.TriggerType.HTTP):
            trigger.logging_handlers = self.logging_handlers

    """
        Update function code and configuration on AWS.

        :param benchmark: benchmark name
        :param name: function name
        :param code_package: path to code package
        :param code_size: size of code package in bytes
        :param timeout: function timeout in seconds
        :param memory: memory limit for function
    """

    def update_function(self, function: Function, code_package: Benchmark):

        function = cast(LambdaFunction, function)
        name = function.name
        code_size = code_package.code_size
        package = code_package.code_location
        # Run AWS update
        # AWS Lambda limit on zip deployment
        if code_size < 50 * 1024 * 1024:
            with open(package, "rb") as code_body:
                self.client.update_function_code(FunctionName=name, ZipFile=code_body.read())
        # Upload code package to S3, then update
        else:
            code_package_name = os.path.basename(package)
            storage = cast(S3, self.get_storage())
            bucket = function.code_bucket(code_package.benchmark, storage)
            storage.upload(bucket, package, code_package_name)
            self.client.update_function_code(
                FunctionName=name, S3Bucket=bucket, S3Key=code_package_name
            )
        self.wait_function_updated(function)
        self.logging.info(f"Updated code of {name} function. ")
        # and update config
        self.client.update_function_configuration(
            FunctionName=name, Timeout=function.config.timeout, MemorySize=function.config.memory
        )
        self.wait_function_updated(function)
        self.logging.info(f"Updated configuration of {name} function. ")
        self.wait_function_updated(function)
        self.logging.info("Published new function code")

    def update_function_configuration(self, function: Function, benchmark: Benchmark):
        function = cast(LambdaFunction, function)
        self.client.update_function_configuration(
            FunctionName=function.name,
            Timeout=function.config.timeout,
            MemorySize=function.config.memory,
        )
        self.wait_function_updated(function)
        self.logging.info(f"Updated configuration of {function.name} function. ")

    @staticmethod
    def default_function_name(code_package: Benchmark) -> str:
        # Create function name
        func_name = "{}-{}-{}".format(
            code_package.benchmark, code_package.language_name, code_package.language_version
        )
        return AWS.format_function_name(func_name)

    @staticmethod
    def format_function_name(func_name: str) -> str:
        # AWS Lambda does not allow hyphens in function names
        func_name = func_name.replace("-", "_")
        func_name = func_name.replace(".", "_")
        return func_name

    """
        FIXME: does not clean the cache
    """

    def delete_function(self, func_name: Optional[str]):
        self.logging.debug("Deleting function {}".format(func_name))
        try:
            self.client.delete_function(FunctionName=func_name)
        except Exception:
            self.logging.debug("Function {} does not exist!".format(func_name))

    """
        Prepare AWS resources to store experiment results.
        Allocate one bucket.

        :param benchmark: benchmark name
        :return: name of bucket to store experiment results
    """

    def prepare_experiment(self, benchmark: str):
        logs_bucket = self.get_storage().add_output_bucket(benchmark, suffix="logs")
        return logs_bucket

    """
        Accepts AWS report after function invocation.
        Returns a dictionary filled with values with various metrics such as
        time, invocation time and memory consumed.

        :param log: decoded log from CloudWatch or from synchronuous invocation
        :return: dictionary with parsed values
    """

    @staticmethod
    def parse_aws_report(
        log: str, requests: Union[ExecutionResult, Dict[str, ExecutionResult]]
    ) -> str:
        aws_vals = {}
        for line in log.split("\t"):
            if not line.isspace():
                split = line.split(":")
                aws_vals[split[0]] = split[1].split()[0]
        if "START RequestId" in aws_vals:
            request_id = aws_vals["START RequestId"]
        else:
            request_id = aws_vals["REPORT RequestId"]
        if isinstance(requests, ExecutionResult):
            output = cast(ExecutionResult, requests)
        else:
            if request_id not in requests:
                return request_id
            output = requests[request_id]
        output.request_id = request_id
        output.provider_times.execution = int(float(aws_vals["Duration"]) * 1000)
        output.stats.memory_used = float(aws_vals["Max Memory Used"])
        if "Init Duration" in aws_vals:
            output.provider_times.initialization = int(float(aws_vals["Init Duration"]) * 1000)
        output.billing.billed_time = int(aws_vals["Billed Duration"])
        output.billing.memory = int(aws_vals["Memory Size"])
        output.billing.gb_seconds = output.billing.billed_time * output.billing.memory
        return request_id

    def shutdown(self) -> None:
        super().shutdown()

    def get_invocation_error(self, function_name: str, start_time: int, end_time: int):
        if not self.logs_client:
            self.logs_client = boto3.client(
                service_name="logs",
                aws_access_key_id=self.config.credentials.access_key,
                aws_secret_access_key=self.config.credentials.secret_key,
                region_name=self.config.region,
            )

        response = None
        while True:
            query = self.logs_client.start_query(
                logGroupName="/aws/lambda/{}".format(function_name),
                # queryString="filter @message like /REPORT/",
                queryString="fields @message",
                startTime=start_time,
                endTime=end_time,
            )
            query_id = query["queryId"]

            while response is None or response["status"] == "Running":
                self.logging.info("Waiting for AWS query to complete ...")
                time.sleep(5)
                response = self.logs_client.get_query_results(queryId=query_id)
            if len(response["results"]) == 0:
                self.logging.info("AWS logs are not yet available, repeat after 15s...")
                time.sleep(15)
                response = None
            else:
                break
        self.logging.error(f"Invocation error for AWS Lambda function {function_name}")
        for message in response["results"]:
            for value in message:
                if value["field"] == "@message":
                    self.logging.error(value["value"])

    def download_metrics(
        self,
        function_name: str,
        start_time: int,
        end_time: int,
        requests: Dict[str, ExecutionResult],
        metrics: dict,
    ):

        if not self.logs_client:
            self.logs_client = boto3.client(
                service_name="logs",
                aws_access_key_id=self.config.credentials.access_key,
                aws_secret_access_key=self.config.credentials.secret_key,
                region_name=self.config.region,
            )

        query = self.logs_client.start_query(
            logGroupName="/aws/lambda/{}".format(function_name),
            queryString="filter @message like /REPORT/",
            startTime=math.floor(start_time),
            endTime=math.ceil(end_time + 1),
            limit=10000,
        )
        query_id = query["queryId"]
        response = None

        while response is None or response["status"] == "Running":
            self.logging.info("Waiting for AWS query to complete ...")
            time.sleep(1)
            response = self.logs_client.get_query_results(queryId=query_id)
        # results contain a list of matches
        # each match has multiple parts, we look at `@message` since this one
        # contains the report of invocation
        results = response["results"]
        results_count = len(requests.keys())
        results_processed = 0
        requests_ids = set(requests.keys())
        for val in results:
            for result_part in val:
                if result_part["field"] == "@message":
                    request_id = AWS.parse_aws_report(result_part["value"], requests)
                    if request_id in requests:
                        results_processed += 1
                        requests_ids.remove(request_id)
        self.logging.info(
            f"Received {len(results)} entries, found results for {results_processed} "
            f"out of {results_count} invocations"
        )

    def create_trigger(self, func: Function, trigger_type: Trigger.TriggerType) -> Trigger:
        from sebs.aws.triggers import HTTPTrigger

        function = cast(LambdaFunction, func)

        if trigger_type == Trigger.TriggerType.HTTP:

            api_name = "{}-http-api".format(function.name)
            http_api = self.config.resources.http_api(api_name, function, self.session)
            # https://aws.amazon.com/blogs/compute/announcing-http-apis-for-amazon-api-gateway/
            # but this is wrong - source arn must be {api-arn}/*/*
            self.get_lambda_client().add_permission(
                FunctionName=function.name,
                StatementId=str(uuid.uuid1()),
                Action="lambda:InvokeFunction",
                Principal="apigateway.amazonaws.com",
                SourceArn=f"{http_api.arn}/*/*",
            )
            trigger = HTTPTrigger(http_api.endpoint, api_name)
            self.logging.info(
                f"Created HTTP trigger for {func.name} function. "
                "Sleep 5 seconds to avoid cloud errors."
            )
            time.sleep(5)
            trigger.logging_handlers = self.logging_handlers
        elif trigger_type == Trigger.TriggerType.LIBRARY:
            # should already exist
            return func.triggers(Trigger.TriggerType.LIBRARY)[0]
        else:
            raise RuntimeError("Not supported!")

        function.add_trigger(trigger)
        self.cache_client.update_function(function)
        return trigger

    def _enforce_cold_start(self, function: Function):
        func = cast(LambdaFunction, function)
        self.get_lambda_client().update_function_configuration(
            FunctionName=func.name,
            Timeout=func.config.timeout,
            MemorySize=func.config.memory,
            Environment={"Variables": {"ForceColdStart": str(self.cold_start_counter)}},
        )

    def enforce_cold_start(self, functions: List[Function], code_package: Benchmark):
        self.cold_start_counter += 1
        for func in functions:
            self._enforce_cold_start(func)
        self.logging.info("Sent function updates enforcing cold starts.")
        for func in functions:
            lambda_function = cast(LambdaFunction, func)
            self.wait_function_updated(lambda_function)
        self.logging.info("Finished function updates enforcing cold starts.")

    def wait_function_active(self, func: LambdaFunction):

        self.logging.info("Waiting for Lambda function to be created...")
        waiter = self.client.get_waiter("function_active_v2")
        waiter.wait(FunctionName=func.name)
        self.logging.info("Lambda function has been created.")

    def wait_function_updated(self, func: LambdaFunction):

        self.logging.info("Waiting for Lambda function to be updated...")
        waiter = self.client.get_waiter("function_updated_v2")
        waiter.wait(FunctionName=func.name)
        self.logging.info("Lambda function has been updated.")

    def cloud_runtime(self, language: Language, language_version: str):
        if language in [Language.NODEJS, Language.PYTHON]:
            return ("{}{}".format(language, language_version),)
        elif language == Language.CPP:
            return "provided.al2"
        else:
            raise NotImplementedError()
