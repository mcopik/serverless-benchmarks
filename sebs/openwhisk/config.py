from sebs.cache import Cache
from sebs.faas.config import Credentials, Resources, Config
from sebs.utils import LoggingHandlers


class OpenWhiskCredentials(Credentials):

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:
        return OpenWhiskCredentials()

    def serialize(self) -> dict:
        return {}


class OpenWhiskResources(Resources):

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Resources:
        return OpenWhiskResources()

    def serialize(self) -> dict:
        return {}


class OpenWhiskConfig(Config):
    name: str
    shutdownStorage: bool
    cache: Cache

    def __init__(self, config: dict, cache: Cache):
        super().__init__()
        self._credentials = OpenWhiskCredentials()
        self._resources = OpenWhiskResources()
        self.name = config['name']
        self.shutdownStorage = config['shutdownStorage']
        self.removeCluster = config['removeCluster']
        self.cache = cache

    @property
    def credentials(self) -> Credentials:
        return self._credentials

    @property
    def resources(self) -> Resources:
        return self._resources

    @staticmethod
    def initialize(cfg: Config, dct: dict):
        pass

    def serialize(self) -> dict:
        return {
            "name": "openwhisk",
            "shutdownStorage": self.shutdownStorage,
            "removeCluster": self.removeCluster,
            "credentials": self._credentials.serialize(),
            "resources": self._resources.serialize(),
        }

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Config:
        res = OpenWhiskConfig(config, cache)
        res.logging_handlers = handlers
        return res

    def update_cache(self, cache: Cache):
        pass
