from abc import abstractmethod, ABC
from typing import Optional

import docker

from sebs.cache import Cache
from sebs.faas.config import Config
from sebs.faas.storage import PersistentStorage
from sebs.faas.nosql import NoSQLStorage
from sebs.utils import LoggingBase


class SystemResources(ABC, LoggingBase):
    def __init__(self, config: Config, cache_client: Cache, docker_client: docker.client):

        super().__init__()

        self._config = config
        self._cache_client = cache_client
        self._docker_client = docker_client

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    @abstractmethod
    def get_storage(self, replace_existing: Optional[bool] = None) -> PersistentStorage:
        pass

    """
        Access persistent storage instance.
        It might be a remote and truly persistent service (AWS S3, Azure Blob..),
        or a dynamically allocated local instance.

        :param replace_existing: replace benchmark input data if exists already
    """

    @abstractmethod
    def get_nosql_storage(self) -> NoSQLStorage:
        pass
