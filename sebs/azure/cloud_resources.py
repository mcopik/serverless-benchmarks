import json
from typing import Optional

from sebs.azure.cli import AzureCLI


class CosmosDBAccount:
    @property
    def account_name(self) -> str:
        return self._account_name

    @property
    def url(self) -> str:
        return self._url

    @property
    def credential(self) -> str:
        return self._credential

    def __init__(self, account_name: str, url: str, credential: str):
        super().__init__()
        self._account_name = account_name
        self._url = url
        self._credential = credential

    @staticmethod
    def from_cache(account_name: str, url: str, credential: str) -> "CosmosDBAccount":
        return CosmosDBAccount(account_name, url, credential)

    @staticmethod
    def from_allocation(
        account_name: str, resource_group: str, cli_instance: AzureCLI, url: Optional[str]
    ) -> "CosmosDBAccount":

        if url is None:
            url = CosmosDBAccount.query_url(
                account_name,
                resource_group,
                cli_instance,
            )

        credential = CosmosDBAccount.query_credentials(
            account_name,
            resource_group,
            cli_instance,
        )

        return CosmosDBAccount(account_name, url, credential)

    @staticmethod
    def query_url(account_name: str, resource_group: str, cli_instance: AzureCLI) -> str:

        # Find the endpoint URL
        ret = cli_instance.execute(
            f" az cosmosdb show --name {account_name} " f" --resource-group {resource_group} "
        )
        ret = json.loads(ret.decode("utf-8"))
        return ret["documentEndpoint"]

    @staticmethod
    def query_credentials(account_name: str, resource_group: str, cli_instance: AzureCLI) -> str:

        # Read the master key to access CosmosDB account
        ret = cli_instance.execute(
            f" az cosmosdb keys list --name {account_name} " f" --resource-group {resource_group} "
        )
        ret = json.loads(ret.decode("utf-8"))
        credential = ret["primaryMasterKey"]

        return credential

    def serialize(self) -> dict:
        return {
            "account_name": self._account_name,
            "url": self._url,
            "credential": self._credential,
        }

    @staticmethod
    def deserialize(obj: dict) -> "CosmosDBAccount":
        return CosmosDBAccount.from_cache(obj["account_name"], obj["url"], obj["credential"])
