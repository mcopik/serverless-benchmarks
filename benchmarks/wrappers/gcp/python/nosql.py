from typing import List, Optional, Tuple

from google.cloud import datastore


class nosql:

    instance: Optional["nosql"] = None

    """
    Each benchmark supports up to two keys - one for grouping items,
    and for unique identification of each item.

    In Google Cloud Datastore, we determine different tables by using
    its value for `kind` name.

    The primary key is assigned to the `kind` value.

    To implement sorting semantics, we use the ancestor relation:
    the sorting key is used as the parent.
    It is the assumption that all related items will have the same parent.
    """

    def __init__(self, database: str):
        self._client = datastore.Client(database=database)

    def insert(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        data: dict,
    ):

        parent_key = self._client.key(primary_key[0], primary_key[1])
        key = self._client.key(
            # kind determines the table
            table_name,
            # main ID key
            secondary_key[1],
            # organization key
            parent=parent_key,
        )

        val = datastore.Entity(key=key)
        val.update(data)
        self._client.put(val)

    def update(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        data: dict,
    ):
        # There is no direct update - we have to fetch the entire entity and manually change fields.
        parent_key = self._client.key(primary_key[0], primary_key[1])
        key = self._client.key(
            # kind determines the table
            table_name,
            # main ID key
            secondary_key[1],
            # organization key
            parent=parent_key,
        )
        res = self._client.get(key)
        if res is None:
            res = datastore.Entity(key=key)
        res.update(data)
        self._client.put(res)

    def get(
        self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]
    ) -> Optional[dict]:

        parent_key = self._client.key(primary_key[0], primary_key[1])
        key = self._client.key(
            # kind determines the table
            table_name,
            # main ID key
            secondary_key[1],
            # organization key
            parent=parent_key,
        )

        res = self._client.get(key)
        if res is None:
            return None

        # Emulate the kind key
        res[secondary_key[0]] = secondary_key[1]

        return res

    """
        This query must involve partition key - it does not scan across partitions.
    """

    def query(
        self, table_name: str, primary_key: Tuple[str, str], secondary_key_name: str
    ) -> List[dict]:

        ancestor = self._client.key(primary_key[0], primary_key[1])
        query = self._client.query(kind=table_name, ancestor=ancestor)
        res = list(query.fetch())

        # Emulate the kind key
        for item in res:
            item[secondary_key_name] = item.key.name

        return res

    def delete(self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]):
        parent_key = self._client.key(primary_key[0], primary_key[1])
        key = self._client.key(
            # kind determines the table
            table_name,
            # main ID key
            secondary_key[1],
            # organization key
            parent=parent_key,
        )

        return self._client.delete(key)

    @staticmethod
    def get_instance(database: Optional[str] = None):
        if nosql.instance is None:
            assert database is not None
            nosql.instance = nosql(database)
        return nosql.instance
