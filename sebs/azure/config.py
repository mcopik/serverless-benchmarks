import json
import logging
import os
import re
import uuid
from typing import cast, Dict, List, Optional


from sebs.azure.cli import AzureCLI
from sebs.azure.cloud_resources import CosmosDBAccount
from sebs.cache import Cache
from sebs.faas.config import Config, Credentials, Resources
from sebs.utils import LoggingHandlers


class AzureCredentials(Credentials):

    _appId: str
    _tenant: str
    _password: str

    def __init__(
        self, appId: str, tenant: str, password: str, subscription_id: Optional[str] = None
    ):
        super().__init__()
        self._appId = appId
        self._tenant = tenant
        self._password = password
        self._subscription_id = subscription_id

    @property
    def appId(self) -> str:
        return self._appId

    @property
    def tenant(self) -> str:
        return self._tenant

    @property
    def password(self) -> str:
        return self._password

    @property
    def subscription_id(self) -> str:
        assert self._subscription_id is not None
        return self._subscription_id

    @subscription_id.setter
    def subscription_id(self, subscription_id: str):

        if self._subscription_id is not None and subscription_id != self._subscription_id:
            self.logging.error(
                f"The subscription id {subscription_id} from provided "
                f"credentials is different from the subscription id "
                f"{self._subscription_id} found in the cache! "
                "Please change your cache directory or create a new one!"
            )
            raise RuntimeError(
                f"Azure login credentials do not match the subscription "
                f"{self._subscription_id} in cache!"
            )

        self._subscription_id = subscription_id

    @property
    def has_subscription_id(self) -> bool:
        return self._subscription_id is not None

    @staticmethod
    def initialize(dct: dict, subscription_id: Optional[str]) -> "AzureCredentials":
        return AzureCredentials(dct["appId"], dct["tenant"], dct["password"], subscription_id)

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Credentials:

        cached_config = cache.get_config("azure")
        ret: AzureCredentials
        old_subscription_id: Optional[str] = None
        # Load cached values
        if cached_config and "credentials" in cached_config:
            old_subscription_id = cached_config["credentials"]["subscription_id"]

        # Check for new config
        if "credentials" in config and "appId" in config["credentials"]:
            ret = AzureCredentials.initialize(config["credentials"], old_subscription_id)
        elif "AZURE_SECRET_APPLICATION_ID" in os.environ:
            ret = AzureCredentials(
                os.environ["AZURE_SECRET_APPLICATION_ID"],
                os.environ["AZURE_SECRET_TENANT"],
                os.environ["AZURE_SECRET_PASSWORD"],
                old_subscription_id,
            )
        else:
            raise RuntimeError(
                "Azure login credentials are missing! Please set "
                "up environmental variables AZURE_SECRET_APPLICATION_ID and "
                "AZURE_SECRET_TENANT and AZURE_SECRET_PASSWORD"
            )
        ret.logging_handlers = handlers

        return ret

    def serialize(self) -> dict:
        out = {"subscription_id": self.subscription_id}
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
        cosmosdb_account: Optional[CosmosDBAccount] = None,
    ):
        super().__init__(name="azure")
        self._resource_group = resource_group
        self._storage_accounts = storage_accounts
        self._data_storage_account = data_storage_account
        self._cosmosdb_account = cosmosdb_account

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
            # Only underscore and alphanumeric characters are allowed
            self._resource_group = "sebs_resource_group_{}".format(self.resources_id)

            groups = self.list_resource_groups(cli_instance)
            if self._resource_group in groups:
                self.logging.info("Using existing resource group {}.".format(self._resource_group))
            else:
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

    def list_resource_groups(self, cli_instance: AzureCLI) -> List[str]:

        ret = cli_instance.execute(
            "az group list --query "
            "\"[?starts_with(name,'sebs_resource_group_') && location=='{0}']\"".format(
                self._region
            )
        )
        try:
            resource_groups = json.loads(ret.decode())
            return [x["name"] for x in resource_groups]
        except Exception:
            self.logging.error("Failed to parse the response!")
            self.logging.error(ret.decode())
            raise RuntimeError("Failed to parse response from Azure CLI!")

    def delete_resource_group(self, cli_instance: AzureCLI, name: str, wait: bool = True):

        cmd = "az group delete -y --name {0}".format(name)
        if not wait:
            cmd += " --no-wait"
        ret = cli_instance.execute(cmd)
        if len(ret) != 0:
            self.logging.error("Failed to delete the resource group!")
            self.logging.error(ret.decode())
            raise RuntimeError("Failed to delete the resource group!")

    """
        Find or create a serverless CosmosDB account.
        If not found, then create a new one based on the current resource ID.
        Restriction: account names must be globally unique.

        Requires Azure CLI instance in Docker.
    """

    def cosmosdb_account(self, cli_instance: AzureCLI) -> CosmosDBAccount:
        # Create resource group if not known
        if not self._cosmosdb_account:

            # Only hyphen and alphanumeric characters are allowed
            account_name = f"sebs-cosmosdb-account-{self.resources_id}"
            account_name = account_name.replace("_", "-")
            account_name = account_name.replace(".", "-")

            accounts = self.list_cosmosdb_accounts(cli_instance)
            if account_name in accounts:

                self.logging.info("Using existing CosmosDB account {}.".format(account_name))
                url = accounts[account_name]

            else:

                try:
                    self.logging.info(f"Starting allocation of CosmosDB account {account_name}")
                    self.logging.info("This can take few minutes :-)!")
                    ret = cli_instance.execute(
                        f" az cosmosdb create --name {account_name} "
                        f" --resource-group {self._resource_group} "
                        f' --locations regionName="{self._region}" '
                        " --capabilities EnableServerless "
                    )
                    ret_values = json.loads(ret.decode())
                    url = ret_values["documentEndpoint"]
                    self.logging.info(f"Allocated CosmosDB account {account_name}")
                except Exception:
                    self.logging.error("Failed to parse the response!")
                    self.logging.error(ret.decode())
                    raise RuntimeError("Failed to parse response from Azure CLI!")

            self._cosmosdb_account = CosmosDBAccount.from_allocation(
                account_name, self.resource_group(cli_instance), cli_instance, url
            )

        return self._cosmosdb_account

    def list_cosmosdb_accounts(self, cli_instance: AzureCLI) -> Dict[str, str]:

        ret = cli_instance.execute(
            f" az cosmosdb list --resource-group {self._resource_group} "
            " --query \"[?starts_with(name,'sebs-cosmosdb-account')]\" "
        )
        try:
            accounts = json.loads(ret.decode())
            return {x["name"]: x["documentEndpoint"] for x in accounts}
        except Exception:
            self.logging.error("Failed to parse the response!")
            self.logging.error(ret.decode())
            raise RuntimeError("Failed to parse response from Azure CLI!")

    """
        Retrieve or create storage account associated with benchmark data.
        Last argument allows to override the resource - useful when handling
        a single instance through multiple threads using different clients sharing the same cache.
    """

    def data_storage_account(self, cli_instance: AzureCLI) -> "AzureResources.Storage":
        if not self._data_storage_account:

            # remove non-numerical and non-alphabetic characters
            parsed = re.compile("[^a-zA-Z0-9]").sub("", self.resources_id)

            account_name = "storage{}".format(parsed)
            self._data_storage_account = self._create_storage_account(cli_instance, account_name)
        return self._data_storage_account

    def list_storage_accounts(self, cli_instance: AzureCLI) -> List[str]:

        ret = cli_instance.execute(
            ("az storage account list --resource-group {0}").format(
                self.resource_group(cli_instance)
            )
        )
        try:
            storage_accounts = json.loads(ret.decode())
            return [x["name"] for x in storage_accounts]
        except Exception:
            self.logging.error("Failed to parse the response!")
            self.logging.error(ret.decode())
            raise RuntimeError("Failed to parse response from Azure CLI!")

    """
        Create a new function storage account and add to the list.
    """

    def add_storage_account(self, cli_instance: AzureCLI) -> "AzureResources.Storage":

        # Create account. Only alphanumeric characters are allowed
        # This one is used to store functions code - hence the name.
        uuid_name = str(uuid.uuid1())[0:8]
        account_name = "function{}".format(uuid_name)

        account = self._create_storage_account(cli_instance, account_name)
        self._storage_accounts.append(account)
        return account

    """
        Internal implementation of creating a new storage account.
        The method does NOT update cache and
        does NOT add the account to any resource collection.
    """

    def _create_storage_account(
        self, cli_instance: AzureCLI, account_name: str
    ) -> "AzureResources.Storage":
        sku = "Standard_LRS"
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
        super().update_cache(cache_client)
        cache_client.update_config(val=self.serialize(), keys=["azure", "resources"])

    @staticmethod
    def initialize(res: Resources, dct: dict):

        ret = cast(AzureResources, res)
        super(AzureResources, AzureResources).initialize(ret, dct)

        ret._resource_group = dct["resource_group"]
        if "storage_accounts" in dct:
            ret._storage_accounts = [
                AzureResources.Storage.deserialize(x) for x in dct["storage_accounts"]
            ]
        else:
            ret._storage_accounts = []

        if "data_storage_account" in dct:
            ret._data_storage_account = AzureResources.Storage.deserialize(
                dct["data_storage_account"]
            )

        if "cosmosdb_account" in dct:
            ret._cosmosdb_account = CosmosDBAccount.deserialize(dct["cosmosdb_account"])

    def serialize(self) -> dict:
        out = super().serialize()
        if len(self._storage_accounts) > 0:
            out["storage_accounts"] = [x.serialize() for x in self._storage_accounts]
        if self._resource_group:
            out["resource_group"] = self._resource_group
        if self._cosmosdb_account:
            out["cosmosdb_account"] = self._cosmosdb_account.serialize()
        if self._data_storage_account:
            out["data_storage_account"] = self._data_storage_account.serialize()
        return out

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Resources:

        cached_config = cache.get_config("azure")
        ret = AzureResources()
        # Load cached values
        if cached_config and "resources" in cached_config and len(cached_config["resources"]) > 0:
            logging.info("Using cached resources for Azure")
            AzureResources.initialize(ret, cached_config["resources"])
        else:
            # Check for new config
            if "resources" in config:
                AzureResources.initialize(ret, config["resources"])
                ret.logging_handlers = handlers
                ret.logging.info("No cached resources for Azure found, using user configuration.")
            else:
                ret = AzureResources()
                ret.logging_handlers = handlers
                ret.logging.info("No resources for Azure found, initialize!")
        return ret


class AzureConfig(Config):
    def __init__(self, credentials: AzureCredentials, resources: AzureResources):
        super().__init__(name="azure")
        self._credentials = credentials
        self._resources = resources

    @property
    def credentials(self) -> AzureCredentials:
        return self._credentials

    @property
    def resources(self) -> AzureResources:
        return self._resources

    # FIXME: use future annotations (see sebs/faas/system)
    @staticmethod
    def initialize(cfg: Config, dct: dict):
        config = cast(AzureConfig, cfg)
        config._region = dct["region"]

    @staticmethod
    def deserialize(config: dict, cache: Cache, handlers: LoggingHandlers) -> Config:

        cached_config = cache.get_config("azure")
        # FIXME: use future annotations (see sebs/faas/system)
        credentials = cast(AzureCredentials, AzureCredentials.deserialize(config, cache, handlers))
        resources = cast(AzureResources, AzureResources.deserialize(config, cache, handlers))
        config_obj = AzureConfig(credentials, resources)
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
        self.credentials.update_cache(cache)
        self.resources.update_cache(cache)

    def serialize(self) -> dict:
        out = {
            "name": "azure",
            "region": self._region,
            "credentials": self._credentials.serialize(),
            "resources": self._resources.serialize(),
        }
        return out
