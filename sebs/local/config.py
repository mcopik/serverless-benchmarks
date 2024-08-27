from typing import cast, Optional, Tuple

from sebs.cache import Cache
from sebs.faas.config import Config, Credentials, Resources
from sebs.storage.config import NoSQLStorageConfig, PersistentStorageConfig, ScyllaDBConfig
from sebs.storage.minio import MinioConfig
from sebs.utils import LoggingHandlers


class LocalCredentials(Credentials):
    def serialize(self) -> dict:
        return {}

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:
        return LocalCredentials()


"""
    No need to cache and store - we prepare the benchmark and finish.
    The rest is used later by the user.
"""


class LocalResources(Resources):
    def __init__(
        self,
        storage_cfg: Optional[PersistentStorageConfig] = None,
        nosql_storage_cfg: Optional[NoSQLStorageConfig] = None,
    ):
        super().__init__(name="local")
        self._object_storage = storage_cfg
        self._nosql_storage = nosql_storage_cfg

    @property
    def storage_config(self) -> Optional[PersistentStorageConfig]:
        return self._object_storage

    @property
    def nosql_storage_config(self) -> Optional[NoSQLStorageConfig]:
        return self._nosql_storage

    def serialize(self) -> dict:
        out: dict = {}

        if self._object_storage is not None:
            out = {**out, "storage": self._object_storage.serialize()}

        if self._nosql_storage is not None:
            out = {**out, "nosql": self._nosql_storage.serialize()}

        return out

    @staticmethod
    def initialize(res: Resources, cfg: dict):
        pass

    def _deserialize_storage(
        self, config: dict, cached_config: Optional[dict], storage_type: str
    ) -> Tuple[str, dict]:

        storage_impl = ""
        storage_config = {}

        # Check for new config
        if "storage" in config and storage_type in config["storage"]:

            storage_impl = config["storage"][storage_type]["type"]
            storage_config = config["storage"][storage_type][storage_impl]
            self.logging.info(
                "Using user-provided configuration of storage "
                f"type: {storage_type} for local containers."
            )

        # Load cached values
        elif (
            cached_config is not None
            and "resources" in cached_config
            and "storage" in cached_config["resources"]
            and "object" in cached_config["resources"]["storage"]
        ):
            storage_impl = cached_config["storage"]["object"]["type"]
            storage_config = cached_config["storage"]["object"][storage_impl]
            self.logging.info(
                f"Using cached configuration of storage type: {storage_type} for local container."
            )

        return storage_impl, storage_config

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Resources:
        ret = LocalResources()

        cached_config = cache.get_config("local")

        obj_storage_impl, obj_storage_cfg = ret._deserialize_storage(
            config, cached_config, "object"
        )

        if obj_storage_impl == "minio":
            ret._object_storage = MinioConfig.deserialize(obj_storage_cfg)
            ret.logging.info("Deserializing access data to Minio storage")
        elif obj_storage_impl != "":
            ret.logging.warning(f"Unknown object storage type: {obj_storage_impl}")
        else:
            ret.logging.info("No object storage available")

        nosql_storage_impl, nosql_storage_cfg = ret._deserialize_storage(
            config, cached_config, "nosql"
        )

        if nosql_storage_impl == "scylladb":
            ret._nosql_storage = ScyllaDBConfig.deserialize(nosql_storage_cfg)
            ret.logging.info("Deserializing access data to ScylladB NoSQL storage")
        elif nosql_storage_impl != "":
            ret.logging.warning(f"Unknown NoSQL storage type: {nosql_storage_impl}")
        else:
            ret.logging.info("No NoSQL storage available")

        return ret


class LocalConfig(Config):
    def __init__(self):
        super().__init__(name="local")
        self._credentials = LocalCredentials()
        self._resources = LocalResources()

    @staticmethod
    def typename() -> str:
        return "Local.Config"

    @staticmethod
    def initialize(cfg: Config, dct: dict):
        pass

    @property
    def credentials(self) -> LocalCredentials:
        return self._credentials

    @property
    def resources(self) -> LocalResources:
        return self._resources

    @resources.setter
    def resources(self, val: LocalResources):
        self._resources = val

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Config:

        config_obj = LocalConfig()
        config_obj.resources = cast(
            LocalResources, LocalResources.deserialize(config, cache, handlers)
        )
        config_obj.logging_handlers = handlers
        return config_obj

    def serialize(self) -> dict:
        return {}

    def update_cache(self, cache: Cache):
        pass
