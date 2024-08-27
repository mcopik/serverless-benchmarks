
import os
import uuid
from typing import Optional

from azure.storage.blob import BlobServiceClient

class storage:
    instance = None
    client = None

    def __init__(self, connection_string: str):
        self.client = BlobServiceClient.from_connection_string(connection_string)

    @staticmethod
    def unique_name(name):
        name, extension = os.path.splitext(name)
        return '{name}.{random}{extension}'.format(
                    name=name,
                    extension=extension,
                    random=str(uuid.uuid4()).split('-')[0]
                )

    def upload(self, container, file, filepath):
        with open(filepath, 'rb') as data:
            return self.upload_stream(container, file, data)

    def download(self, container, file, filepath):
        with open(filepath, 'wb') as download_file:
            download_file.write( self.download_stream(container, file) )
    
    def download_directory(self, container, prefix, path):
        client = self.client.get_container_client(container=container)
        objects = client.list_blobs(name_starts_with=prefix)
        for obj in objects:
            file_name = obj.name
            path_to_file = os.path.dirname(file_name)
            os.makedirs(os.path.join(path, path_to_file), exist_ok=True)
            self.download(container, file_name, os.path.join(path, file_name))
    
    def upload_stream(self, container, file, data):
        key_name = storage.unique_name(file)
        client = self.client.get_blob_client(
                container=container,
                blob=key_name
        )
        client.upload_blob(data)
        return key_name

    def download_stream(self, container, file):
        client = self.client.get_blob_client(container=container, blob=file)
        return client.download_blob().readall()
    
    @staticmethod
    def get_instance(connection_string: Optional[str] = None):
        if storage.instance is None:
            assert connection_string is not None
            storage.instance = storage(connection_string)
        return storage.instance
