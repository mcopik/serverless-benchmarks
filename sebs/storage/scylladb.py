import json
import os
import platform
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple, Type, TypeVar

from sebs.cache import Cache
from sebs.faas.config import Resources
from sebs.faas.nosql import NoSQLStorage
from sebs.types import NoSQLStorage as StorageType
from sebs.storage.config import ScyllaDBConfig
from sebs.utils import project_absolute_path

import boto3
from boto3.dynamodb.types import TypeSerializer
import docker


class ScyllaDB(NoSQLStorage):
    @staticmethod
    def typename() -> str:
        return f"{ScyllaDB.deployment_name()}.ScyllaDB"

    @staticmethod
    def deployment_name() -> str:
        return "scylladb"

    @property
    def config(self) -> ScyllaDBConfig:
        return self._cfg

    # the location does not matter
    SCYLLADB_REGION = "None"

    def __init__(
        self,
        docker_client: docker.client,
        cache_client: Cache,
        config: ScyllaDBConfig,
        resources: Optional[Resources] = None,
    ):

        super().__init__(self.SCYLLADB_REGION, cache_client, resources)  # type: ignore
        self._docker_client = docker_client
        self._storage_container: Optional[docker.container] = None
        self._cfg = config

        # Map benchmark -> orig_name -> table_name
        self._tables: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._serializer = TypeSerializer()

        if config.address != "":
            self.client = boto3.client(
                "dynamodb",
                region_name="None",
                aws_access_key_id="None",
                aws_secret_access_key="None",
                endpoint_url=f"http://{config.address}",
            )

    def start(self):

        if self._cfg.data_volume == "":
            scylladb_volume = os.path.join(project_absolute_path(), "scylladb-volume")
        else:
            scylladb_volume = self._cfg.data_volume
        scylladb_volume = os.path.abspath(scylladb_volume)

        os.makedirs(scylladb_volume, exist_ok=True)
        volumes = {
            scylladb_volume: {
                "bind": "/var/lib/scylla/",
                "mode": "rw",
            }
        }

        try:

            scylladb_args = ""
            scylladb_args += f"--smp {self._cfg.cpus} "
            scylladb_args += f"--memory {self._cfg.memory}M "
            scylladb_args += "--overprovisioned 1 "
            scylladb_args += "--alternator-port 8000 "
            scylladb_args += "--alternator-write-isolation=only_rmw_uses_lwt "

            self.logging.info("Starting ScyllaDB storage")
            self._storage_container = self._docker_client.containers.run(
                f"scylladb/scylla:{self._cfg.version}",
                command=scylladb_args,
                name="some-scylla",
                hostname="some-scylla",
                network_mode="bridge",
                volumes=volumes,
                ports={"8000": str(self._cfg.mapped_port)},
                remove=True,
                stdout=True,
                stderr=True,
                detach=True,
            )
            self._cfg.instance_id = self._storage_container.id

            # Wait until it boots up
            attempts = 0
            max_attempts = 30
            while attempts < max_attempts:

                exit_code, out = self._storage_container.exec_run("nodetool status")

                if exit_code == 0:
                    self.logging.info("Started ScyllaDB succesfully!")
                    break

                time.sleep(1.0)
                attempts += 1

            if attempts == max_attempts:
                self.logging.error("Failed to launch ScyllaBD!")
                self.logging.error(f"Last result of nodetool status: {out}")
                raise RuntimeError("Failed to launch ScyllaBD!")

            self.configure_connection()
        except docker.errors.APIError as e:
            self.logging.error("Starting ScyllaDB storage failed! Reason: {}".format(e))
            raise RuntimeError("Starting ScyllaDB storage unsuccesful")
        except Exception as e:
            self.logging.error("Starting ScyllaDB storage failed! Unknown error: {}".format(e))
            raise RuntimeError("Starting ScyllaDB storage unsuccesful")

    # FIXME: refactor this - duplicated code from minio
    def configure_connection(self):
        # who knows why? otherwise attributes are not loaded
        if self._cfg.address == "":

            if self._storage_container is None:
                raise RuntimeError(
                    "ScyllaDB container is not available! Make sure that you deployed "
                    "the ScyllaDB storage and provided configuration!"
                )

            self._storage_container.reload()

            # Check if the system is Linux and that it's not WSL
            if platform.system() == "Linux" and "microsoft" not in platform.release().lower():
                networks = self._storage_container.attrs["NetworkSettings"]["Networks"]
                self._cfg.address = "{IPAddress}:{Port}".format(
                    IPAddress=networks["bridge"]["IPAddress"], Port=self._cfg.alternator_port
                )
            else:
                # System is either WSL, Windows, or Mac
                self._cfg.address = f"localhost:{self._cfg.mapped_port}"

            if not self._cfg.address:
                self.logging.error(
                    f"Couldn't read the IP address of container from attributes "
                    f"{json.dumps(self._instance.attrs, indent=2)}"
                )
                raise RuntimeError(
                    f"Incorrect detection of IP address for container with id {self._instance_id}"
                )
            self.logging.info("Starting ScyllaDB instance at {}".format(self._cfg.address))

    def stop(self):
        if self._storage_container is not None:
            self.logging.info(f"Stopping ScyllaDB container at {self._cfg.address}.")
            self._storage_container.stop()
            self.logging.info(f"Stopped ScyllaDB container at {self._cfg.address}.")
        else:
            self.logging.error("Stopping ScyllaDB was not succesful, storage container not known!")

    def envs(self) -> dict:
        return {"NOSQL_STORAGE_TYPE": "scylladb", "NOSQL_STORAGE_ENDPOINT": self._cfg.address}

    def serialize(self) -> Tuple[StorageType, dict]:
        return StorageType.SCYLLADB, self._cfg.serialize()

    """
        This implementation supports overriding this class.
        The main ScyllaDB class is used to start/stop deployments.

        When overriding the implementation in Local/OpenWhisk/...,
        we call the _deserialize and provide an alternative implementation.
    """

    T = TypeVar("T", bound="ScyllaDB")

    @staticmethod
    def _deserialize(
        cached_config: ScyllaDBConfig, cache_client: Cache, resources: Resources, obj_type: Type[T]
    ) -> T:
        docker_client = docker.from_env()
        obj = obj_type(docker_client, cache_client, cached_config, resources)

        if cached_config.instance_id:
            instance_id = cached_config.instance_id
            try:
                obj._storage_container = docker_client.containers.get(instance_id)
            except docker.errors.NotFound:
                raise RuntimeError(f"Storage container {instance_id} does not exist!")
        else:
            obj._storage_container = None
        return obj

    @staticmethod
    def deserialize(
        cached_config: ScyllaDBConfig, cache_client: Cache, resources: Resources
    ) -> "ScyllaDB":
        return ScyllaDB._deserialize(cached_config, cache_client, resources, ScyllaDB)

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
                waiter.wait(TableName=name)

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
