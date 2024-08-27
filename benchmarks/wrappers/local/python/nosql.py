from decimal import Decimal
from os import environ
from typing import List, Optional, Union, Tuple

import boto3


class nosql:

    instance: Optional["nosql"] = None

    def __init__(self):

        if environ["NOSQL_STORAGE_TYPE"] != "scylladb":
            raise RuntimeError(f"Unsupported NoSQL storage type: {environ['NOSQL_STORAGE_TYPE']}!")

        self.client = boto3.resource(
            "dynamodb",
            region_name="None",
            aws_access_key_id="None",
            aws_secret_access_key="None",
            endpoint_url=f"http://{environ['NOSQL_STORAGE_ENDPOINT']}",
        )
        self._tables = {}

    # Based on: https://github.com/boto/boto3/issues/369#issuecomment-157205696
    def _remove_decimals(self, data: dict) -> Union[dict, list, int, float]:

        if isinstance(data, list):
            return [self._remove_decimals(x) for x in data]
        elif isinstance(data, dict):
            return {k: self._remove_decimals(v) for k, v in data.items()}
        elif isinstance(data, Decimal):
            if data.as_integer_ratio()[1] == 1:
                return int(data)
            else:
                return float(data)
        else:
            return data

    def _get_table(self, table_name: str):

        if table_name not in self._tables:

            env_name = f"NOSQL_STORAGE_TABLE_{table_name}"

            if env_name in environ:
                aws_name = environ[env_name]
                self._tables[table_name] = self.client.Table(aws_name)
            else:
                raise RuntimeError(
                    f"Couldn't find an environment variable {env_name} for table {table_name}"
                )

        return self._tables[table_name]

    def insert(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        data: dict,
    ):
        for key in (primary_key, secondary_key):
            data[key[0]] = key[1]

        self._get_table(table_name).put_item(Item=data)

    def get(
        self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]
    ) -> dict:

        data = {}
        for key in (primary_key, secondary_key):
            data[key[0]] = key[1]

        res = self._get_table(table_name).get_item(Key=data)
        return self._remove_decimals(res["Item"])

    def update(
        self,
        table_name: str,
        primary_key: Tuple[str, str],
        secondary_key: Tuple[str, str],
        updates: dict,
    ):

        key_data = {}
        for key in (primary_key, secondary_key):
            key_data[key[0]] = key[1]

        update_expression = "SET "
        update_values = {}
        update_names = {}

        # We use attribute names because DynamoDB reserves some keywords, like 'status'
        for key, value in updates.items():

            update_expression += f" #{key}_name = :{key}_value, "
            update_values[f":{key}_value"] = value
            update_names[f"#{key}_name"] = key

        update_expression = update_expression[:-2]

        self._get_table(table_name).update_item(
            Key=key_data,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=update_values,
            ExpressionAttributeNames=update_names,
        )

    def query(self, table_name: str, primary_key: Tuple[str, str], _: str) -> List[dict]:

        res = self._get_table(table_name).query(
            KeyConditionExpression=f"{primary_key[0]} = :keyvalue",
            ExpressionAttributeValues={":keyvalue": primary_key[1]},
        )["Items"]
        return self._remove_decimals(res)

    def delete(self, table_name: str, primary_key: Tuple[str, str], secondary_key: Tuple[str, str]):
        data = {}
        for key in (primary_key, secondary_key):
            data[key[0]] = key[1]

        self._get_table(table_name).delete_item(Key=data)

    @staticmethod
    def get_instance():
        if nosql.instance is None:
            nosql.instance = nosql()
        return nosql.instance
