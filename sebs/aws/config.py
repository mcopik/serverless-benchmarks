import json
import os
import time
from typing import cast, Dict, Optional

import boto3


from sebs.cache import Cache
from sebs.faas.config import Config, Credentials, Resources
from sebs.aws.function import LambdaFunction
from sebs.utils import LoggingHandlers


class AWSCredentials(Credentials):

    _access_key: str
    _secret_key: str

    def __init__(self, access_key: str, secret_key: str):
        super().__init__()
        self._access_key = access_key
        self._secret_key = secret_key

    @staticmethod
    def typename() -> str:
        return "AWS.Credentials"

    @property
    def access_key(self) -> str:
        return self._access_key

    @property
    def secret_key(self) -> str:
        return self._secret_key

    @staticmethod
    def initialize(dct: dict) -> Credentials:
        return AWSCredentials(dct["access_key"], dct["secret_key"])

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:

        # FIXME: update return types of both functions to avoid cast
        # needs 3.7+  to support annotations
        cached_config = cache.get_config("aws")
        ret: AWSCredentials
        # Load cached values
        if cached_config and "credentials" in cached_config:
            ret = cast(AWSCredentials, AWSCredentials.initialize(cached_config["credentials"]))
            ret.logging_handlers = handlers
            ret.logging.info("Using cached credentials for AWS")
        else:
            # Check for new config
            if "credentials" in config:
                ret = cast(AWSCredentials, AWSCredentials.initialize(config["credentials"]))
            elif "AWS_ACCESS_KEY_ID" in os.environ:
                ret = AWSCredentials(
                    os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"]
                )
            else:
                raise RuntimeError(
                    "AWS login credentials are missing! Please set "
                    "up environmental variables AWS_ACCESS_KEY_ID and "
                    "AWS_SECRET_ACCESS_KEY"
                )
            ret.logging.info("No cached credentials for AWS found, initialize!")
            ret.logging_handlers = handlers
        return ret

    def update_cache(self, cache: Cache):
        cache.update_config(val=self.access_key, keys=["aws", "credentials", "access_key"])
        cache.update_config(val=self.secret_key, keys=["aws", "credentials", "secret_key"])

    def serialize(self) -> dict:
        out = {"access_key": self.access_key, "secret_key": self.secret_key}
        return out


class AWSResources(Resources):
    class HTTPApi:
        def __init__(self, arn: str, endpoint: str):
            self._arn = arn
            self._endpoint = endpoint

        @property
        def arn(self) -> str:
            return self._arn

        @property
        def endpoint(self) -> str:
            return self._endpoint

        @staticmethod
        def deserialize(dct: dict) -> "AWSResources.HTTPApi":
            return AWSResources.HTTPApi(dct["arn"], dct["endpoint"])

        def serialize(self) -> dict:
            out = {"arn": self.arn, "endpoint": self.endpoint}
            return out

    def __init__(self, lambda_role: str):
        super().__init__()
        self._lambda_role = lambda_role
        self._http_apis: Dict[str, AWSResources.HTTPApi] = {}
        self._region: Optional[str] = None

    @staticmethod
    def typename() -> str:
        return "AWS.Resources"

    def set_region(self, region: str):
        self._region = region

    def lambda_role(self, boto3_session: boto3.session.Session) -> str:
        if not self._lambda_role:
            iam_client = boto3_session.client(service_name="iam")
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "",
                        "Effect": "Allow",
                        "Principal": {"Service": ["lambda.amazonaws.com", "states.amazonaws.com"]},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
            role_name = "sebs-role"
            attached_policies = [
                "arn:aws:iam::aws:policy/AmazonS3FullAccess",
                "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaRole",
                "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess",
            ]
            try:
                out = iam_client.get_role(RoleName=role_name)
                self._lambda_role = out["Role"]["Arn"]
                self.logging.info(f"AWS: Selected {self._lambda_role} IAM role")
            except iam_client.exceptions.NoSuchEntityException:
                out = iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                )
                self._lambda_role = out["Role"]["Arn"]
                self.logging.info(
                    f"AWS: Created {self._lambda_role} IAM role. "
                    "Sleep 10 seconds to avoid problems when using role immediately."
                )
                time.sleep(10)
            # Attach basic AWS Lambda and S3 policies.
            for policy in attached_policies:
                iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
        return self._lambda_role

    def http_api(
        self, api_name: str, func: LambdaFunction, boto3_session: boto3.session.Session
    ) -> "AWSResources.HTTPApi":

        http_api = self._http_apis.get(api_name)
        if not http_api:
            # get apigateway client
            api_client = boto3_session.client(
                service_name="apigatewayv2", region_name=cast(str, self._region)
            )

            # check existing apis
            api_data = None
            for api in api_client.get_apis()["Items"]:
                if api["Name"] == api_name:
                    self.logging.info(f"Using existing HTTP API {api_name}")
                    api_data = api
                    break
            if not api_data:
                self.logging.info(f"Creating HTTP API {api_name}")
                api_data = api_client.create_api(  # type: ignore
                    Name=api_name, ProtocolType="HTTP", Target=func.arn
                )
            api_id = api_data["ApiId"]  # type: ignore
            endpoint = api_data["ApiEndpoint"]  # type: ignore

            # function's arn format is: arn:aws:{region}:{account-id}:{func}
            # easier than querying AWS resources to get account id
            account_id = func.arn.split(":")[4]
            # API arn is:
            arn = f"arn:aws:execute-api:{self._region}:{account_id}:{api_id}"
            http_api = AWSResources.HTTPApi(arn, endpoint)
            self._http_apis[api_name] = http_api
        else:
            self.logging.info(f"Using cached HTTP API {api_name}")
        return http_api

    # FIXME: python3.7+ future annotatons
    @staticmethod
    def initialize(dct: dict) -> Resources:
        ret = AWSResources(dct["lambda-role"] if "lambda-role" in dct else "")
        if "http-apis" in dct:
            for key, value in dct["http-apis"].items():
                ret._http_apis[key] = AWSResources.HTTPApi.deserialize(value)
        return ret

    def serialize(self) -> dict:
        out = {
            "lambda-role": self._lambda_role,
            "http-apis": {key: value.serialize() for (key, value) in self._http_apis.items()},
        }
        return out

    def update_cache(self, cache: Cache):
        cache.update_config(val=self._lambda_role, keys=["aws", "resources", "lambda-role"])
        for name, api in self._http_apis.items():
            cache.update_config(val=api.serialize(), keys=["aws", "resources", "http-apis", name])

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Resources:

        cached_config = cache.get_config("aws")
        ret: AWSResources
        # Load cached values
        if cached_config and "resources" in cached_config:
            ret = cast(AWSResources, AWSResources.initialize(cached_config["resources"]))
            ret.logging_handlers = handlers
            ret.logging.info("Using cached resources for AWS")
        else:
            # Check for new config
            if "resources" in config:
                ret = cast(AWSResources, AWSResources.initialize(config["resources"]))
                ret.logging_handlers = handlers
                ret.logging.info("No cached resources for AWS found, using user configuration.")
            else:
                ret = AWSResources(lambda_role="")
                ret.logging_handlers = handlers
                ret.logging.info("No resources for AWS found, initialize!")

        return ret


class AWSConfig(Config):
    def __init__(self, credentials: AWSCredentials, resources: AWSResources, redis_host: str):
        super().__init__()
        self._credentials = credentials
        self._resources = resources
        self._redis_host = redis_host

    @staticmethod
    def typename() -> str:
        return "AWS.Config"

    @property
    def credentials(self) -> AWSCredentials:
        return self._credentials

    @property
    def resources(self) -> AWSResources:
        return self._resources

    @property
    def redis_host(self) -> str:
        return self._redis_host

    # FIXME: use future annotations (see sebs/faas/system)
    @staticmethod
    def initialize(cfg: Config, dct: dict):
        config = cast(AWSConfig, cfg)
        config._region = dct["region"]
        config._redis_host = dct["redis_host"]

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Config:

        cached_config = cache.get_config("aws")
        # FIXME: use future annotations (see sebs/faas/system)
        credentials = cast(AWSCredentials, AWSCredentials.deserialize(config, cache, handlers))
        resources = cast(AWSResources, AWSResources.deserialize(config, cache, handlers))
        config_obj = AWSConfig(credentials, resources, cached_config["redis_host"])
        config_obj.logging_handlers = handlers
        # Load cached values
        if cached_config:
            config_obj.logging.info("Using cached config for AWS")
            AWSConfig.initialize(config_obj, cached_config)
        else:
            config_obj.logging.info("Using user-provided config for AWS")
            AWSConfig.initialize(config_obj, config)

        resources.set_region(config_obj.region)
        return config_obj

    """
        Update the contents of the user cache.
        The changes are directly written to the file system.

        Update values: region.
    """

    def update_cache(self, cache: Cache):
        cache.update_config(val=self.region, keys=["aws", "region"])
        self.credentials.update_cache(cache)
        self.resources.update_cache(cache)

    def serialize(self) -> dict:
        out = {
            "name": "aws",
            "region": self._region,
            "credentials": self._credentials.serialize(),
            "resources": self._resources.serialize(),
            "redis_host": self._redis_host,
        }
        return out
