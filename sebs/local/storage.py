import docker
from typing import Optional

from sebs.faas.config import Resources
from sebs.storage import minio
from sebs.storage import scylladb
from sebs.storage.config import MinioConfig, ScyllaDBConfig
from sebs.cache import Cache


class Minio(minio.Minio):
    @staticmethod
    def deployment_name() -> str:
        return "local"

    @staticmethod
    def typename() -> str:
        return "Local.Minio"

    def __init__(
        self,
        docker_client: docker.client,
        cache_client: Cache,
        res: Resources,
        replace_existing: bool,
    ):
        super().__init__(docker_client, cache_client, res, replace_existing)

    @staticmethod
    def deserialize(
        cached_config: MinioConfig, cache_client: Cache, resources: Resources
    ) -> "Minio":
        return super(Minio, Minio)._deserialize(cached_config, cache_client, resources, Minio)


class ScyllaDB(scylladb.ScyllaDB):
    @staticmethod
    def deployment_name() -> str:
        return "local"

    @staticmethod
    def typename() -> str:
        return "Local.ScyllaDB"

    def __init__(
        self,
        docker_client: docker.client,
        cache_client: Cache,
        config: ScyllaDBConfig,
        res: Optional[Resources],
    ):
        super().__init__(docker_client, cache_client, config, res)

    @staticmethod
    def deserialize(
        cached_config: ScyllaDBConfig, cache_client: Cache, resources: Resources
    ) -> "ScyllaDB":
        return super(ScyllaDB, ScyllaDB)._deserialize(
            cached_config, cache_client, resources, ScyllaDB
        )
