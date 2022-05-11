import logging
import uuid
from typing import List

from google.cloud import storage as gcp_storage  # type: ignore

from sebs.cache import Cache
from ..faas.storage import PersistentStorage


class GCPStorage(PersistentStorage):
    @staticmethod
    def typename() -> str:
        return "GCP.GCPStorage"

    @staticmethod
    def deployment_name():
        return "gcp"

    @property
    def replace_existing(self) -> bool:
        return self._replace_existing

    @replace_existing.setter
    def replace_existing(self, val: bool):
        self._replace_existing = val

    def __init__(self, region: str, cache_client: Cache, replace_existing: bool):
        super().__init__(region, cache_client, replace_existing)
        self.replace_existing = replace_existing
        self.client = gcp_storage.Client()
        self.cached = False

    def correct_name(self, name: str) -> str:
        return name

    def _create_bucket(self, name, buckets: List[str] = []):
        found_bucket = False
        for bucket_name in buckets:
            if name in bucket_name:
                found_bucket = True
                break

        if not found_bucket:
            random_name = str(uuid.uuid4())[0:16]
            bucket_name = "{}-{}".format(name, random_name).replace(".", "_")
            self.client.create_bucket(bucket_name)
            logging.info("Created bucket {}".format(bucket_name))
            return bucket_name
        else:
            logging.info("Bucket {} for {} already exists, skipping.".format(bucket_name, name))
            return bucket_name

    def download(self, bucket_name: str, key: str, filepath: str) -> None:
        logging.info("Download {}:{} to {}".format(bucket_name, key, filepath))
        bucket_instance = self.client.bucket(bucket_name)
        blob = bucket_instance.blob(key)
        blob.download_to_filename(filepath)

    def upload(self, bucket_name: str, filepath: str, key: str):
        logging.info("Upload {} to {}".format(filepath, bucket_name))
        bucket_instance = self.client.bucket(bucket_name)
        blob = bucket_instance.blob(key, chunk_size=4 * 1024 * 1024)
        gcp_storage.blob._MAX_MULTIPART_SIZE = 5 * 1024 * 1024  # workaround for connection timeout
        blob.upload_from_filename(filepath)

    def list_bucket(self, bucket_name: str) -> List[str]:
        bucket_instance = self.client.get_bucket(bucket_name)
        all_blobs = list(self.client.list_blobs(bucket_instance))
        blobs = [blob.name for blob in all_blobs]
        return blobs

    def list_buckets(self, bucket_name: str) -> List[str]:
        all_buckets = list(self.client.list_buckets())
        buckets = [bucket.name for bucket in all_buckets]
        return buckets

    def clean_bucket(self, bucket: str):
        raise NotImplementedError()

    """
        :param bucket_name:
        :return: list of files in a given bucket
    """

    # def list_bucket(self, bucket_name: str) -> List[str]:
    #    name = "{}-{}".format(bucket_name, suffix)
    #    bucket_name = self.create_bucket(name)
    #    return bucket_name

    def uploader_func(self, bucket_idx: int, key: str, filepath: str) -> None:
        if self.cached and not self.replace_existing:
            return
        bucket_name = self.input_buckets[bucket_idx]
        print(self.input_buckets_files[bucket_idx])
        if not self.replace_existing:
            for blob in self.input_buckets_files[bucket_idx]:
                if key == blob:
                    logging.info("Skipping upload of {} to {}".format(filepath, bucket_name))
                    return
        bucket_name = self.input_buckets[bucket_idx]
        self.upload(bucket_name, filepath, key)
