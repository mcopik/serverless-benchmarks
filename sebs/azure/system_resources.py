import json
from typing import cast, Optional

from sebs.config import SeBSConfig
from sebs.azure.config import AzureConfig
from sebs.azure.blob_storage import BlobStorage
from sebs.azure.cosmosdb import CosmosDB
from sebs.azure.cli import AzureCLI
from sebs.cache import Cache
from sebs.faas.resources import SystemResources
from sebs.utils import LoggingHandlers

import docker


class AzureSystemResources(SystemResources):
    @staticmethod
    def typename() -> str:
        return "Azure.SystemResources"

    @property
    def config(self) -> AzureConfig:
        return cast(AzureConfig, self._config)

    def __init__(
        self,
        system_config: SeBSConfig,
        config: AzureConfig,
        cache_client: Cache,
        docker_client: docker.client,
        logger_handlers: LoggingHandlers,
    ):
        super().__init__(config, cache_client, docker_client)

        self._logging_handlers = logger_handlers
        self._storage: Optional[BlobStorage] = None
        self._nosql_storage: Optional[CosmosDB] = None
        self._cli_instance: Optional[AzureCLI] = None
        self._system_config = system_config

    """
        Create wrapper object for Azure blob storage.
        First ensure that storage account is created and connection string
        is known. Then, create wrapper and create request number of buckets.

        Requires Azure CLI instance in Docker to obtain storage account details.

        :param benchmark:
        :param buckets: number of input and output buckets
        :param replace_existing: when true, replace existing files in input buckets
        :return: Azure storage instance
    """

    def get_storage(self, replace_existing: Optional[bool] = None) -> BlobStorage:
        if self._storage is None:
            self._storage = BlobStorage(
                self.config.region,
                self._cache_client,
                self.config.resources,
                self.config.resources.data_storage_account(self.cli_instance).connection_string,
                replace_existing=replace_existing if replace_existing is not None else False,
            )
            self._storage.logging_handlers = self.logging_handlers
        elif replace_existing is not None:
            self._storage.replace_existing = replace_existing
        return self._storage

    def get_nosql_storage(self) -> CosmosDB:
        if self._nosql_storage is None:
            self._nosql_storage = CosmosDB(
                self.cli_instance, self._cache_client, self.config.resources, self.config.region
            )
        return self._nosql_storage

    @property
    def cli_instance(self) -> AzureCLI:

        if self._cli_instance is None:
            self._cli_instance = AzureCLI(self._system_config, self._docker_client)
            self._cli_instance_stop = True

            output = self._cli_instance.login(
                appId=self.config.credentials.appId,
                tenant=self.config.credentials.tenant,
                password=self.config.credentials.password,
            )

            subscriptions = json.loads(output)
            if len(subscriptions) == 0:
                raise RuntimeError("Didn't find any valid subscription on Azure!")
            if len(subscriptions) > 1:
                raise RuntimeError(
                    "Found more than one valid subscription on Azure - not supported!"
                )

            self.config.credentials.subscription_id = subscriptions[0]["id"]

        return self._cli_instance

    def initialize_cli(self, cli: AzureCLI):
        self._cli_instance = cli
        self._cli_instance_stop = False

    def shutdown(self) -> None:
        if self._cli_instance and self._cli_instance_stop:
            self._cli_instance.shutdown()
