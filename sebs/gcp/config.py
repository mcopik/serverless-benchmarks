import os
from typing import cast, List, Tuple

from sebs.cache import Cache
from sebs.faas.config import Config, Credentials, Resources
from sebs.utils import LoggingHandlers

# FIXME: Replace type hints for static generators after migration to 3.7
# https://stackoverflow.com/questions/33533148/how-do-i-specify-that-the-return-type-of-a-method-is-the-same-as-the-class-itsel

"""
    Credentials for FaaS system used to authorize operations on functions
    and other resources.

    The order of credentials initialization:
    1. Load credentials from cache.
    2. If any new vaues are provided in the config, they override cache values.
    3. If nothing is provided, initialize using environmental variables.
    4. If no information is provided, then failure is reported.
"""


class GCPCredentials(Credentials):
    _gcp_credentials: str

    def __init__(self, gcp_credentials: str):
        super().__init__()
        self._gcp_credentials = gcp_credentials

    @property
    def gcp_credentials(self) -> str:
        return self._gcp_credentials

    @staticmethod
    def initialize(gcp_credentials: str) -> Credentials:
        return GCPCredentials(gcp_credentials)

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:
        cached_config = cache.get_config("gcp")
        ret: GCPCredentials
        # Load cached values but only if they are non-empty
        if (
            cached_config
            and "credentials" in cached_config
            and cached_config["credentials"]["keys_json"]
        ):
            ret = cast(
                GCPCredentials,
                GCPCredentials.initialize(cached_config["credentials"]["keys_json"]),
            )
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ret.gcp_credentials
            ret.logging_handlers = handlers
            ret.logging.info("Using cached credentials for GCP")
        else:
            # Check for new config
            if "credentials" in config and config["credentials"]:
                ret = cast(GCPCredentials, GCPCredentials.initialize(config["credentials"]))
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ret.gcp_credentials
            # Look for default GCP credentials
            elif "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
                ret = GCPCredentials(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
                cache.update_config(
                    val=ret.gcp_credentials, keys=["gcp", "credentials", "keys_json"]
                )
            # Look for our environment variables
            elif "GCP_SECRET_APPLICATION_CREDENTIALS" in os.environ:
                ret = GCPCredentials(os.environ["GCP_SECRET_APPLICATION_CREDENTIALS"])
                cache.update_config(
                    val=ret.gcp_credentials, keys=["gcp", "credentials", "keys_json"]
                )
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ret.gcp_credentials
            else:
                raise RuntimeError(
                    "GCP login credentials are missing! Please set the path to .json "
                    "with cloud credentials in config or in the GCP_SECRET_APPLICATION_CREDENTIALS "
                    "environmental variable"
                )
            ret.logging_handlers = handlers
            ret.logging.info("No cached credentials for GCP found, initialize!")
        return ret

    """
        Serialize to JSON for storage in cache.
    """

    def serialize(self) -> dict:
        out = {"keys_json": self.gcp_credentials}
        return out

    def update_cache(self, cache: Cache):
        cache.update_config(val=self.gcp_credentials, keys=["gcp", "credentials", "keys_json"])


"""
    Class grouping resources allocated at the FaaS system to execute functions
    and deploy various services. Examples might include IAM roles and API gateways
    for HTTP triggers.

    Storage resources are handled seperately.
"""


class GCPResources(Resources):
    def __init__(self):
        super().__init__()

    @staticmethod
    def initialize(dct: dict) -> Resources:
        return GCPResources()

    """
        Serialize to JSON for storage in cache.
    """

    def serialize(self) -> dict:
        return {}

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> "Resources":
        cached_config = cache.get_config("gcp")
        ret: GCPResources
        if cached_config and "resources" in cached_config:
            ret = cast(GCPResources, GCPResources.initialize(cached_config["resources"]))
            ret.logging_handlers = handlers
            ret.logging.info("Using cached resources for GCP")
        else:
            ret = cast(GCPResources, GCPResources.initialize(config))
            ret.logging_handlers = handlers
            ret.logging.info("No cached resources for GCP found, using user configuration.")
        return ret

    def update_cache(self, cache: Cache):
        pass


"""
    FaaS system config defining cloud region (if necessary), credentials and
    resources allocated.
"""


class GCPConfig(Config):

    _project_name: str

    def __init__(self, credentials: GCPCredentials, resources: GCPResources, redis_host: str):
        super().__init__()
        self._credentials = credentials
        self._resources = resources
        self._redis_host = redis_host

    @property
    def region(self) -> str:
        return self._region

    @property
    def project_name(self) -> str:
        return self._project_name

    @property
    def credentials(self) -> GCPCredentials:
        return self._credentials

    @property
    def resources(self) -> GCPResources:
        return self._resources

    @property
    def redis_host(self) -> str:
        return self._redis_host

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> "Config":
        cached_config = cache.get_config("gcp")
        credentials = cast(GCPCredentials, GCPCredentials.deserialize(config, cache, handlers))
        resources = cast(GCPResources, GCPResources.deserialize(config, cache, handlers))
        config_obj = GCPConfig(credentials, resources, cached_config["redis_host"])
        config_obj.logging_handlers = handlers
        if cached_config:
            config_obj.logging.info("Loading cached config for GCP")
            GCPConfig.initialize(config_obj, cached_config)
        else:
            config_obj.logging.info("Using user-provided config for GCP")

            # User didn't provide the project name
            if "project_name" not in config or not config["project_name"]:
                if "GCP_PROJECT_NAME" in os.environ:
                    GCPConfig.initialize(
                        config_obj,
                        {**config, "project_name": os.environ["GCP_PROJECT_NAME"]},
                    )
                else:
                    raise RuntimeError(
                        "Google Cloud Platform: project name is missing! "
                        "Please provide it in configuration or through the "
                        "GCP_PROJECT_NAME environment variable!"
                    )
            else:
                GCPConfig.initialize(config_obj, config)

        # mypy makes a mistake here
        updated_keys: List[Tuple[str, Tuple[str]]] = [
            ["region", ["gcp", "region"]],  # type: ignore
            ["project_name", ["gcp", "project_name"]],  # type: ignore
        ]
        # for each attribute here, check if its version is different than the one provided by
        # user; if yes, then update the value
        for config_key, keys in updated_keys:

            old_value = getattr(config_obj, config_key)
            # ignore empty values
            if getattr(config_obj, config_key) != config[config_key] and config[config_key]:
                config_obj.logging.info(
                    f"Updating cached key {config_key} with {old_value} "
                    f"to user-provided value {config[config_key]}."
                )
                setattr(config_obj, f"_{config_key}", config[config_key])
                cache.update_config(val=getattr(config_obj, config_key), keys=keys)

        return config_obj

    @staticmethod
    def initialize(cfg: Config, dct: dict):
        config = cast(GCPConfig, cfg)
        config._project_name = dct["project_name"]
        config._region = dct["region"]
        config._redis_host = dct["redis_host"]

    def serialize(self) -> dict:
        out = {
            "name": "gcp",
            "project_name": self._project_name,
            "region": self._region,
            "credentials": self._credentials.serialize(),
            "resources": self._resources.serialize(),
            "redis_host": self._redis_host,
        }
        return out

    def update_cache(self, cache: Cache):
        cache.update_config(val=self.project_name, keys=["gcp", "project_name"])
        cache.update_config(val=self.region, keys=["gcp", "region"])
        self.credentials.update_cache(cache)
        self.resources.update_cache(cache)
