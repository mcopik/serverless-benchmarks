from typing import Dict, List, Optional, Tuple

from azure.cosmos import CosmosClient, ContainerProxy


class nosql:
    instance = None
    client = None

    def __init__(self, url: str, credential: str, database: str):
        self._client = CosmosClient(url=url, credential=credential)
        self._db_client = self._client.get_database_client(database)
        self._containers: Dict[str, ContainerProxy] = {}

    def _get_table(self, table_name: str):

        if table_name not in self._containers:
            self._containers[table_name] = self._db_client.get_container_client(table_name)

        return self._containers[table_name]

    def insert(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        data: dict,
    ):

        data[primary_key[0]] = primary_key[1]
        # secondary key must have that name in CosmosDB
        data["id"] = secondary_key[1]

        self._get_table(table_name).upsert_item(data)

    def get(
        self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]
    ) -> dict:
        res = self._get_table(table_name).read_item(
            item=secondary_key[1], partition_key=primary_key[1]
        )
        res[secondary_key[0]] = secondary_key[1]

        return res

    def update(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        updates: dict,
    ):

        ops = []
        for key, value in updates.items():
            ops.append({"op": "add", "path": f"/{key}", "value": value})

        self._get_table(table_name).patch_item(
            item=secondary_key[1], partition_key=primary_key[1], patch_operations=ops
        )

    """
        This query must involve partition key - it does not scan across partitions.
    """

    def query(
        self, table_name: str, primary_key: Tuple[str, str], secondary_key_name: str
    ) -> List[dict]:

        res = list(
            self._get_table(table_name).query_items(
                f"SELECT * FROM c WHERE c.{primary_key[0]} = '{primary_key[1]}'",
                enable_cross_partition_query=False,
            )
        )

        # Emulate the kind key
        for item in res:
            item[secondary_key_name] = item["id"]

        return res

    def delete(self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]):

        self._get_table(table_name).delete_item(item=secondary_key[1], partition_key=primary_key[1])

    @staticmethod
    def get_instance(
        database: Optional[str] = None, url: Optional[str] = None, credential: Optional[str] = None
    ):
        if nosql.instance is None:
            assert database is not None and url is not None and credential is not None
            nosql.instance = nosql(url, credential, database)
        return nosql.instance
