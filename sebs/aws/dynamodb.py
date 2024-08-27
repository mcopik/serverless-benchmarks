from collections import defaultdict
from typing import Dict, Optional, Tuple

from sebs.cache import Cache
from sebs.faas.config import Resources
from sebs.faas.nosql import NoSQLStorage

import boto3
from boto3.dynamodb.types import TypeSerializer


class DynamoDB(NoSQLStorage):
    @staticmethod
    def typename() -> str:
        return "AWS.DynamoDB"

    @staticmethod
    def deployment_name():
        return "aws"

    def __init__(
        self,
        session: boto3.session.Session,
        cache_client: Cache,
        resources: Resources,
        region: str,
        access_key: str,
        secret_key: str,
    ):
        super().__init__(region, cache_client, resources)
        self.client = session.client(
            "dynamodb",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        # Map benchmark -> orig_name -> table_name
        self._tables: Dict[str, Dict[str, str]] = defaultdict(dict)

        self._serializer = TypeSerializer()

    def retrieve_cache(self, benchmark: str) -> bool:

        if benchmark in self._tables:
            return True

        cached_storage = self.cache_client.get_nosql_config(self.deployment_name(), benchmark)
        if cached_storage is not None:
            self._tables[benchmark] = cached_storage["tables"]
            return True

        return False

    def update_cache(self, benchmark: str):

        self._cache_client.update_nosql(
            self.deployment_name(),
            benchmark,
            {
                "tables": self._tables[benchmark],
            },
        )

    def get_tables(self, benchmark: str) -> Dict[str, str]:
        return self._tables[benchmark]

    def _get_table_name(self, benchmark: str, table: str) -> Optional[str]:

        if benchmark not in self._tables:
            return None

        if table not in self._tables[benchmark]:
            return None

        return self._tables[benchmark][table]

    def writer_func(
        self,
        benchmark: str,
        table: str,
        data: dict,
        primary_key: Tuple[str, str],
        secondary_key: Optional[Tuple[str, str]] = None,
    ):

        table_name = self._get_table_name(benchmark, table)
        assert table_name is not None

        for key in (primary_key, secondary_key):
            if key is not None:
                data[key[0]] = key[1]

        serialized_data = {k: self._serializer.serialize(v) for k, v in data.items()}
        self.client.put_item(TableName=table_name, Item=serialized_data)

    """
        AWS: create a DynamoDB Table

        In contrast to the hierarchy of database objects in Azure (account -> database -> container)
        and GCP (database per benchmark), we need to create unique table names here.
    """

    def create_table(
        self, benchmark: str, name: str, primary_key: str, secondary_key: Optional[str] = None
    ) -> str:

        table_name = f"sebs-benchmarks-{self._cloud_resources.resources_id}-{benchmark}-{name}"

        try:

            definitions = [{"AttributeName": primary_key, "AttributeType": "S"}]
            key_schema = [{"AttributeName": primary_key, "KeyType": "HASH"}]

            if secondary_key is not None:
                definitions.append({"AttributeName": secondary_key, "AttributeType": "S"})
                key_schema.append({"AttributeName": secondary_key, "KeyType": "RANGE"})

            ret = self.client.create_table(
                TableName=table_name,
                BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=definitions,  # type: ignore
                KeySchema=key_schema,  # type: ignore
            )

            if ret["TableDescription"]["TableStatus"] == "CREATING":

                self.logging.info(f"Waiting for creation of DynamoDB table {name}")
                waiter = self.client.get_waiter("table_exists")
                waiter.wait(TableName=table_name, WaiterConfig={"Delay": 1})

            self.logging.info(f"Created DynamoDB table {name} for benchmark {benchmark}")
            self._tables[benchmark][name] = table_name

            return ret["TableDescription"]["TableName"]

        except self.client.exceptions.ResourceInUseException as e:

            if "already exists" in e.response["Error"]["Message"]:
                self.logging.info(
                    f"Using existing DynamoDB table {table_name} for benchmark {benchmark}"
                )
                self._tables[benchmark][name] = table_name
                return name

            raise RuntimeError(f"Creating DynamoDB failed, unknown reason! Error: {e}")

    def clear_table(self, name: str) -> str:
        raise NotImplementedError()

    def remove_table(self, name: str) -> str:
        raise NotImplementedError()
