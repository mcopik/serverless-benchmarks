import json
import logging
import os
import uuid
from typing import cast, Any, Dict, List, Optional  # noqa


from sebs.azure.cli import AzureCLI
from sebs.cache import Cache
from sebs.faas.config import Config, Credentials, Resources
from sebs.utils import LoggingHandlers


class AzureCredentials(Credentials):

    _appId: str
    _tenant: str
    _password: str

    def __init__(self, appId: str, tenant: str, password: str):
        super().__init__()
        self._appId = appId
        self._tenant = tenant
        self._password = password

    @property
    def appId(self) -> str:
        return self._appId

    @property
    def tenant(self) -> str:
        return self._tenant

    @property
    def password(self) -> str:
        return self._password

    @staticmethod
    def initialize(dct: dict) -> Credentials:
        return AzureCredentials(dct["appId"], dct["tenant"], dct["password"])

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:

        # FIXME: update return types of both functions to avoid cast
        # needs 3.7+  to support annotations
        cached_config = cache.get_config("azure")
        ret: AzureCredentials
        # Load cached values
        if cached_config and "credentials" in cached_config:
            ret = cast(
                AzureCredentials,
                AzureCredentials.initialize(cached_config["credentials"]),
            )
            ret.logging_handlers = handlers
            ret.logging.info("Using cached credentials for Azure")
        else:
            # Check for new config
            if "credentials" in config:
                ret = cast(
                    AzureCredentials,
                    AzureCredentials.initialize(config["credentials"]),
                )
            elif "AZURE_SECRET_APPLICATION_ID" in os.environ:
                ret = AzureCredentials(
                    os.environ["AZURE_SECRET_APPLICATION_ID"],
                    os.environ["AZURE_SECRET_TENANT"],
                    os.environ["AZURE_SECRET_PASSWORD"],
                )
            else:
                raise RuntimeError(
                    "Azure login credentials are missing! Please set "
                    "up environmental variables AZURE_SECRET_APPLICATION_ID and "
                    "AZURE_SECRET_TENANT and AZURE_SECRET_PASSWORD"
                )
            ret.logging_handlers = handlers
            ret.logging.info("No cached credentials for Azure found, initialize!")
        return ret

    def serialize(self) -> dict:
        out = {"appId": self.appId, "tenant": self.tenant, "password": self.password}
        return out

    def update_cache(self, cache_client: Cache):
        cache_client.update_config(val=self.serialize(), keys=["azure", "credentials"])


class AzureResources(Resources):
    class Storage:
        def __init__(self, account_name: str, connection_string: str):
            super().__init__()
            self.account_name = account_name
            self.connection_string = connection_string

        # FIXME: 3.7+ migration with future annotations
        @staticmethod
        def from_cache(account_name: str, connection_string: str) -> "AzureResources.Storage":
            assert connection_string, "Empty connection string for account {}".format(account_name)
            return AzureResources.Storage(account_name, connection_string)

        @staticmethod
        def from_allocation(account_name: str, cli_instance: AzureCLI) -> "AzureResources.Storage":
            connection_string = AzureResources.Storage.query_connection_string(
                account_name, cli_instance
            )
            ret = AzureResources.Storage(account_name, connection_string)
            return ret

        """
            Query the storage string in Azure using selected storage account.
        """

        @staticmethod
        def query_connection_string(account_name: str, cli_instance: AzureCLI) -> str:
            ret = cli_instance.execute(
                "az storage account show-connection-string --name {}".format(account_name)
            )
            ret = json.loads(ret.decode("utf-8"))
            connection_string = ret["connectionString"]
            return connection_string

        def serialize(self) -> dict:
            return vars(self)

        @staticmethod
        def deserialize(obj: dict) -> "AzureResources.Storage":
            return AzureResources.Storage.from_cache(obj["account_name"], obj["connection_string"])

    # FIXME: 3.7 Python, future annotations
    def __init__(
        self,
        resource_group: Optional[str] = None,
        storage_accounts: List["AzureResources.Storage"] = [],
        data_storage_account: Optional["AzureResources.Storage"] = None,
    ):
        super().__init__()
        self._resource_group = resource_group
        self._storage_accounts = storage_accounts
        self._data_storage_account = data_storage_account

    def set_region(self, region: str):
        self._region = region

    @property
    def storage_accounts(self) -> List["AzureResources.Storage"]:
        return self._storage_accounts

    """
        Locate resource group name in config.
        If not found, then create a new resource group with uuid-based name.

        Requires Azure CLI instance in Docker.
    """

    def resource_group(self, cli_instance: AzureCLI) -> str:
        # Create resource group if not known
        if not self._resource_group:
            uuid_name = str(uuid.uuid1())[0:8]
            # Only underscore and alphanumeric characters are allowed
            self._resource_group = "sebs_resource_group_{}".format(uuid_name)
            self.logging.info(
                "Starting allocation of resource group {}.".format(self._resource_group)
            )
            cli_instance.execute(
                "az group create --name {0} --location {1}".format(
                    self._resource_group, self._region
                )
            )
            self.logging.info("Resource group {} created.".format(self._resource_group))
        return self._resource_group

    """
        Retrieve or create storage account associated with benchmark data.
        Last argument allows to override the resource - useful when handling
        a single instance through multiple threads using different clients sharing the same cache.
    """

    def data_storage_account(self, cli_instance: AzureCLI) -> "AzureResources.Storage":
        if not self._data_storage_account:
            self._data_storage_account = self._create_storage_account(cli_instance)
        return self._data_storage_account

    """
        Create a new function storage account and add to the list.
    """

    def add_storage_account(self, cli_instance: AzureCLI) -> "AzureResources.Storage":
        account = self._create_storage_account(cli_instance)
        self._storage_accounts.append(account)
        return account

    """
        Internal implementation of creating a new storage account.
        The method does NOT update cache and
        does NOT add the account to any resource collection.
    """

    def _create_storage_account(self, cli_instance: AzureCLI) -> "AzureResources.Storage":
        sku = "Standard_LRS"
        # Create account. Only alphanumeric characters are allowed
        uuid_name = str(uuid.uuid1())[0:8]
        account_name = "sebsstorage{}".format(uuid_name)
        self.logging.info("Starting allocation of storage account {}.".format(account_name))
        cli_instance.execute(
            (
                "az storage account create --name {0} --location {1} "
                "--resource-group {2} --sku {3}"
            ).format(
                account_name,
                self._region,
                self.resource_group(cli_instance),
                sku,
            )
        )
        self.logging.info("Storage account {} created.".format(account_name))
        return AzureResources.Storage.from_allocation(account_name, cli_instance)

    """
        Update the contents of the user cache.
        The changes are directly written to the file system.

        Update values: storage accounts, data storage accounts, resource groups.
    """

    def update_cache(self, cache_client: Cache):
        cache_client.update_config(val=self.serialize(), keys=["azure", "resources"])

    # FIXME: python3.7+ future annotatons
    @staticmethod
    def initialize(dct: dict) -> Resources:
        return AzureResources(
            resource_group=dct["resource_group"],
            storage_accounts=[
                AzureResources.Storage.deserialize(x) for x in dct["storage_accounts"]
            ],
            data_storage_account=AzureResources.Storage.deserialize(dct["data_storage_account"]),
        )

    def serialize(self) -> dict:
        out: Dict[str, Any] = {}
        if len(self._storage_accounts) > 0:
            out["storage_accounts"] = [x.serialize() for x in self._storage_accounts]
        if self._resource_group:
            out["resource_group"] = self._resource_group
        if self._data_storage_account:
            out["data_storage_account"] = self._data_storage_account.serialize()
        return out

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Resources:

        cached_config = cache.get_config("azure")
        ret: AzureResources
        # Load cached values
        if cached_config and "resources" in cached_config and len(cached_config["resources"]) > 0:
            logging.info("Using cached resources for Azure")
            ret = cast(AzureResources, AzureResources.initialize(cached_config["resources"]))
        else:
            # Check for new config
            if "resources" in config:
                ret = cast(AzureResources, AzureResources.initialize(config["resources"]))
                ret.logging_handlers = handlers
                ret.logging.info("No cached resources for Azure found, using user configuration.")
            else:
                ret = AzureResources()
                ret.logging_handlers = handlers
                ret.logging.info("No resources for Azure found, initialize!")
        return ret


class AzureConfig(Config):
    def __init__(self, credentials: AzureCredentials, resources: AzureResources, redis_host: str):
        super().__init__()
        self._resources_id = ""
        self._credentials = credentials
        self._resources = resources
        self._redis_host = redis_host

    @property
    def credentials(self) -> AzureCredentials:
        return self._credentials

    @property
    def resources(self) -> AzureResources:
        return self._resources

    @property
    def resources_id(self) -> str:
        return self._resources_id

    @property
    def redis_host(self) -> str:
        return self._redis_host

    # FIXME: use future annotations (see sebs/faas/system)
    @staticmethod
    def initialize(cfg: Config, dct: dict):
        config = cast(AzureConfig, cfg)
        config._region = dct["region"]
        config._redis_host = dct["redis_host"]
        if "resources_id" in dct:
            config._resources_id = dct["resources_id"]
        else:
            config._resources_id = str(uuid.uuid1())[0:8]
            config.logging.info(
                f"Azure: generating unique resource name for"
                f"the experiments: {config._resources_id}"
            )

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Config:

        cached_config = cache.get_config("azure")
        # FIXME: use future annotations (see sebs/faas/system)
        credentials = cast(AzureCredentials, AzureCredentials.deserialize(config, cache, handlers))
        resources = cast(AzureResources, AzureResources.deserialize(config, cache, handlers))
        config_obj = AzureConfig(credentials, resources, cached_config["redis_host"])
        config_obj.logging_handlers = handlers
        # Load cached values
        if cached_config:
            config_obj.logging.info("Using cached config for Azure")
            AzureConfig.initialize(config_obj, cached_config)
        else:
            config_obj.logging.info("Using user-provided config for Azure")
            AzureConfig.initialize(config_obj, config)

        resources.set_region(config_obj.region)
        return config_obj

    """
        Update the contents of the user cache.
        The changes are directly written to the file system.

        Update values: region.
    """

    def update_cache(self, cache: Cache):
        cache.update_config(val=self.region, keys=["azure", "region"])
        cache.update_config(val=self.resources_id, keys=["azure", "resources_id"])
        self.credentials.update_cache(cache)
        self.resources.update_cache(cache)

    def serialize(self) -> dict:
        out = {
            "name": "azure",
            "region": self._region,
            "resources_id": self.resources_id,
            "credentials": self._credentials.serialize(),
            "resources": self._resources.serialize(),
            "redis_host": self._redis_host,
        }
        return out
