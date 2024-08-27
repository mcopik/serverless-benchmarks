import copy
import json
import os
import secrets
import uuid
import platform
from typing import List, Optional, Type, TypeVar

import docker
import minio

from sebs.cache import Cache
from sebs.types import Storage as StorageTypes
from sebs.faas.config import Resources
from sebs.faas.storage import PersistentStorage
from sebs.storage.config import MinioConfig
from sebs.utils import project_absolute_path


class Minio(PersistentStorage):
    @staticmethod
    def typename() -> str:
        return f"{Minio.deployment_name()}.Minio"

    @staticmethod
    def deployment_name() -> str:
        return "minio"

    # the location does not matter
    MINIO_REGION = "us-east-1"

    def __init__(
        self,
        docker_client: docker.client,
        cache_client: Cache,
        resources: Resources,
        replace_existing: bool,
    ):
        super().__init__(self.MINIO_REGION, cache_client, resources, replace_existing)
        self._docker_client = docker_client
        self._storage_container: Optional[docker.container] = None
        self._cfg = MinioConfig()

    @property
    def config(self) -> MinioConfig:
        return self._cfg

    @config.setter
    def config(self, config: MinioConfig):
        self._cfg = config

    @staticmethod
    def _define_http_client():
        """
        Minio does not allow another way of configuring timeout for connection.
        The rest of configuration is copied from source code of Minio.
        """
        import urllib3
        from datetime import timedelta

        timeout = timedelta(seconds=1).seconds

        return urllib3.PoolManager(
            timeout=urllib3.util.Timeout(connect=timeout, read=timeout),
            maxsize=10,
            retries=urllib3.Retry(
                total=5, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]
            ),
        )

    def start(self):

        if self._cfg.data_volume == "":
            minio_volume = os.path.join(project_absolute_path(), "minio-volume")
        else:
            minio_volume = self._cfg.data_volume
        minio_volume = os.path.abspath(minio_volume)

        os.makedirs(minio_volume, exist_ok=True)
        volumes = {
            minio_volume: {
                "bind": "/data",
                "mode": "rw",
            }
        }

        self._cfg.access_key = secrets.token_urlsafe(32)
        self._cfg.secret_key = secrets.token_hex(32)
        self._cfg.address = ""
        self.logging.info("Minio storage ACCESS_KEY={}".format(self._cfg.access_key))
        self.logging.info("Minio storage SECRET_KEY={}".format(self._cfg.secret_key))
        try:
            self.logging.info(f"Starting storage Minio on port {self._cfg.mapped_port}")
            self._storage_container = self._docker_client.containers.run(
                f"minio/minio:{self._cfg.version}",
                command="server /data",
                network_mode="bridge",
                ports={"9000": str(self._cfg.mapped_port)},
                environment={
                    "MINIO_ACCESS_KEY": self._cfg.access_key,
                    "MINIO_SECRET_KEY": self._cfg.secret_key,
                },
                volumes=volumes,
                remove=True,
                stdout=True,
                stderr=True,
                detach=True,
            )
            self._cfg.instance_id = self._storage_container.id
            self.configure_connection()
        except docker.errors.APIError as e:
            self.logging.error("Starting Minio storage failed! Reason: {}".format(e))
            raise RuntimeError("Starting Minio storage unsuccesful")
        except Exception as e:
            self.logging.error("Starting Minio storage failed! Unknown error: {}".format(e))
            raise RuntimeError("Starting Minio storage unsuccesful")

    def configure_connection(self):
        # who knows why? otherwise attributes are not loaded
        if self._cfg.address == "":

            if self._storage_container is None:
                raise RuntimeError(
                    "Minio container is not available! Make sure that you deployed "
                    "the Minio storage and provided configuration!"
                )

            self._storage_container.reload()

            # Check if the system is Linux and that it's not WSL
            if platform.system() == "Linux" and "microsoft" not in platform.release().lower():
                networks = self._storage_container.attrs["NetworkSettings"]["Networks"]
                self._cfg.address = "{IPAddress}:{Port}".format(
                    IPAddress=networks["bridge"]["IPAddress"], Port=9000
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
            self.logging.info("Starting minio instance at {}".format(self._cfg.address))
        self.connection = self.get_connection()

    def stop(self):
        if self._storage_container is not None:
            self.logging.info(f"Stopping minio container at {self._cfg.address}.")
            self._storage_container.stop()
            self.logging.info(f"Stopped minio container at {self._cfg.address}.")
        else:
            self.logging.error("Stopping minio was not succesful, storage container not known!")

    def get_connection(self):
        return minio.Minio(
            self._cfg.address,
            access_key=self._cfg.access_key,
            secret_key=self._cfg.secret_key,
            secure=False,
            http_client=Minio._define_http_client(),
        )

    def _create_bucket(self, name: str, buckets: List[str] = [], randomize_name: bool = False):
        for bucket_name in buckets:
            if name in bucket_name:
                self.logging.info(
                    "Bucket {} for {} already exists, skipping.".format(bucket_name, name)
                )
                return bucket_name
        # minio has limit of bucket name to 16 characters
        if randomize_name:
            bucket_name = "{}-{}".format(name, str(uuid.uuid4())[0:16])
        else:
            bucket_name = name
        try:
            self.connection.make_bucket(bucket_name, location=self.MINIO_REGION)
            self.logging.info("Created bucket {}".format(bucket_name))
            return bucket_name
        except (
            minio.error.BucketAlreadyOwnedByYou,
            minio.error.BucketAlreadyExists,
            minio.error.ResponseError,
        ) as err:
            self.logging.error("Bucket creation failed!")
            # rethrow
            raise err

    def uploader_func(self, path_idx, file, filepath):
        try:
            key = os.path.join(self.input_prefixes[path_idx], file)
            bucket_name = self.get_bucket(Resources.StorageBucketType.BENCHMARKS)
            self.connection.fput_object(bucket_name, key, filepath)
        except minio.error.ResponseError as err:
            self.logging.error("Upload failed!")
            raise (err)

    def clean(self):
        for bucket in self.output_buckets:
            objects = self.connection.list_objects_v2(bucket)
            objects = [obj.object_name for obj in objects]
            for err in self.connection.remove_objects(bucket, objects):
                self.logging.error("Deletion Error: {}".format(err))

    def download_results(self, result_dir):
        result_dir = os.path.join(result_dir, "storage_output")
        for bucket in self.output_buckets:
            objects = self.connection.list_objects_v2(bucket)
            objects = [obj.object_name for obj in objects]
            for obj in objects:
                self.connection.fget_object(bucket, obj, os.path.join(result_dir, obj))

    def clean_bucket(self, bucket: str):
        delete_object_list = map(
            lambda x: minio.DeleteObject(x.object_name),
            self.connection.list_objects(bucket_name=bucket),
        )
        errors = self.connection.remove_objects(bucket, delete_object_list)
        for error in errors:
            self.logging.error(f"Error when deleting object from bucket {bucket}: {error}!")

    def remove_bucket(self, bucket: str):
        self.connection.remove_bucket(Bucket=bucket)

    def correct_name(self, name: str) -> str:
        return name

    def download(self, bucket_name: str, key: str, filepath: str):
        raise NotImplementedError()

    def exists_bucket(self, bucket_name: str) -> bool:
        return self.connection.bucket_exists(bucket_name)

    def list_bucket(self, bucket_name: str, prefix: str = "") -> List[str]:
        try:
            objects_list = self.connection.list_objects(bucket_name)
            objects: List[str]
            return [obj.object_name for obj in objects_list if prefix in obj.object_name]
        except minio.error.NoSuchBucket:
            raise RuntimeError(f"Attempting to access a non-existing bucket {bucket_name}!")

    def list_buckets(self, bucket_name: Optional[str] = None) -> List[str]:
        buckets = self.connection.list_buckets()
        if bucket_name is not None:
            return [bucket.name for bucket in buckets if bucket_name in bucket.name]
        else:
            return [bucket.name for bucket in buckets]

    def upload(self, bucket_name: str, filepath: str, key: str):
        raise NotImplementedError()

    def serialize(self) -> dict:
        return {
            **self._cfg.serialize(),
            "type": StorageTypes.MINIO,
        }

    """
        This implementation supports overriding this class.
        The main Minio class is used to start/stop deployments.

        When overriding the implementation in Local/OpenWhisk/...,
        we call the _deserialize and provide an alternative implementation.
    """

    T = TypeVar("T", bound="Minio")

    @staticmethod
    def _deserialize(
        cached_config: MinioConfig, cache_client: Cache, res: Resources, obj_type: Type[T]
    ) -> T:
        docker_client = docker.from_env()
        obj = obj_type(docker_client, cache_client, res, False)
        obj._cfg = cached_config
        if cached_config.instance_id:
            instance_id = cached_config.instance_id
            try:
                obj._storage_container = docker_client.containers.get(instance_id)
            except docker.errors.NotFound:
                raise RuntimeError(f"Storage container {instance_id} does not exist!")
        else:
            obj._storage_container = None
        obj._input_prefixes = copy.copy(cached_config.input_buckets)
        obj._output_prefixes = copy.copy(cached_config.output_buckets)
        obj.configure_connection()
        return obj

    @staticmethod
    def deserialize(cached_config: MinioConfig, cache_client: Cache, res: Resources) -> "Minio":
        return Minio._deserialize(cached_config, cache_client, res, Minio)
