import sebs.local.storage
from typing import List, Tuple, Any
import secrets
import docker.errors
from sebs.cache import Cache


class Minio(sebs.local.storage.Minio):

    @staticmethod
    def deployment_name() -> str:
        return "openwhisk"

    input_buckets: List[str] = []
    output_buckets: List[str] = []
    input_index = 0
    output_index = 0
    access_key: str = ""
    secret_key: str = ""
    port = 9000
    location = "openwhiskBenchmark"
    connection: Any

    def __init__(self,docker_client: docker.client, cache_client: Cache, replace_existing: bool):
        super(Minio, self).__init__(docker_client, cache_client, replace_existing)
        self.start()
        self.connection = self.get_connection()

    def start(self):
        self.startMinio()

    def startMinio(self):
        minioVersion = "minio/minio:latest"
        try:
            self._storage_container = self._docker_client.containers.get("minio")
            self.logging.info("Minio container already exists")
            envs = self._storage_container.attrs["Config"]["Env"]
            if isinstance(envs, (tuple, list)):
                envs = dict([i.split('=', 1) for i in envs])
            self._access_key = envs['MINIO_ACCESS_KEY']
            self._secret_key = envs['MINIO_SECRET_KEY']
        except docker.errors.NotFound:
            self.logging.info("Minio container does not exists, starting")
            self._access_key = secrets.token_urlsafe(32)
            self._secret_key = secrets.token_hex(32)
            self._storage_container = self._docker_client.containers.run(
                minioVersion,
                command="server /data",
                environment={
                    "MINIO_ACCESS_KEY": self._access_key,
                    "MINIO_SECRET_KEY": self._secret_key,
                },
                remove=True,
                stdout=True,
                stderr=True,
                detach=True,
                name="minio"
            )

        self.logging.info("ACCESS_KEY={}".format(self._access_key))
        self.logging.info("SECRET_KEY={}".format(self._secret_key))
        self._storage_container.reload()
        networks = self._storage_container.attrs["NetworkSettings"]["Networks"]
        self._url = "{IPAddress}:{Port}".format(
            IPAddress=networks["bridge"]["IPAddress"], Port=self.port
        )
        self.logging.info("Minio runs at {}".format(self._url))