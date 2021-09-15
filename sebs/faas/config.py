from abc import ABC
from abc import abstractmethod

from sebs.cache import Cache
from sebs.utils import LoggingBase, LoggingHandlers

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


class Credentials(ABC, LoggingBase):
    def __init__(self):
        super().__init__()

    """
        Create credentials instance from user config and cached values.
    """

    @staticmethod
    @abstractmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> "Credentials":
        pass

    """
        Serialize to JSON for storage in cache.
    """

    @abstractmethod
    def serialize(self) -> dict:
        pass


"""
    Class grouping resources allocated at the FaaS system to execute functions
    and deploy various services. Examples might include IAM roles and API gateways
    for HTTP triggers.

    Storage resources are handled seperately.
"""


class Resources(ABC, LoggingBase):
    def __init__(self):
        super().__init__()

    """
        Create credentials instance from user config and cached values.
    """

    @staticmethod
    @abstractmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> "Resources":
        pass

    """
        Serialize to JSON for storage in cache.
    """

    @abstractmethod
    def serialize(self) -> dict:
        pass


"""
    FaaS system config defining cloud region (if necessary), credentials and
    resources allocated.
"""


class Config(ABC, LoggingBase):

    _region: str

    def __init__(self):
        super().__init__()

    @property
    def region(self) -> str:
        return self._region

    @property
    @abstractmethod
    def credentials(self) -> Credentials:
        pass

    @property
    @abstractmethod
    def resources(self) -> Resources:
        pass

    @staticmethod
    @abstractmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> "Config":
        from sebs.aws.config import AWSConfig
        from sebs.azure.config import AzureConfig
        from sebs.gcp.config import GCPConfig
        from sebs.local.config import LocalConfig
        from sebs.openwhisk.config import OpenWhiskConfig

        name = config["name"]
        func = {
            "aws": AWSConfig.deserialize,
            "azure": AzureConfig.deserialize,
            "gcp": GCPConfig.deserialize,
            "local": LocalConfig.deserialize,
            "openwhisk": OpenWhiskConfig.deserialize,
        }.get(name)
        assert func, "Unknown config type!"
        return func(config[name] if name in config else config, cache, handlers)

    @abstractmethod
    def serialize(self) -> dict:
        pass

    @abstractmethod
    def update_cache(self, cache: Cache):
        pass
