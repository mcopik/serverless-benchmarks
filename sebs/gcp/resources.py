from typing import cast, Optional

from sebs.config import SeBSConfig
from sebs.gcp.config import GCPConfig
from sebs.gcp.storage import GCPStorage
from sebs.gcp.datastore import Datastore
from sebs.gcp.cli import GCloudCLI
from sebs.cache import Cache
from sebs.faas.resources import SystemResources
from sebs.utils import LoggingHandlers

import docker


class GCPSystemResources(SystemResources):
    @staticmethod
    def typename() -> str:
        return "GCP.SystemResources"

    @property
    def config(self) -> GCPConfig:
        return cast(GCPConfig, self._config)

    def __init__(
        self,
        system_config: SeBSConfig,
        config: GCPConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logger_handlers: LoggingHandlers,
    ):
        super().__init__(config, cache_client, docker_client)

        self._logging_handlers = logger_handlers
        self._storage: Optional[GCPStorage] = None
        self._nosql_storage: Optional[Datastore] = None
        self._cli_instance: Optional[GCloudCLI] = None
        self._system_config = system_config

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    def get_storage(self, replace_existing: Optional[bool] = None) -> GCPStorage:
        if not self._storage:
            self._storage = GCPStorage(
                self.config.region,
                self._cache_client,
                self.config.resources,
                replace_existing if replace_existing is not None else False,
            )
            self._storage.logging_handlers = self._logging_handlers
        elif replace_existing is not None:
            self._storage.replace_existing = replace_existing
        return self._storage

    def get_nosql_storage(self) -> Datastore:
        if not self._nosql_storage:
            self._nosql_storage = Datastore(
                self.cli_instance, self._cache_client, self.config.resources, self.config.region
            )
        return self._nosql_storage

    @property
    def cli_instance(self) -> GCloudCLI:
        if self._cli_instance is None:
            self._cli_instance = GCloudCLI(
                self.config.credentials, self._system_config, self._docker_client
            )
            self._cli_instance_stop = True

            self._cli_instance.login(self.config.credentials.project_name)
        return self._cli_instance

    def initialize_cli(self, cli: GCloudCLI):
        self._cli_instance = cli
        self._cli_instance_stop = False

    def shutdown(self) -> None:
        if self._cli_instance and self._cli_instance_stop:
            self._cli_instance.shutdown()
