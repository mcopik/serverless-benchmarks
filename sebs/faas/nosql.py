from abc import ABC
from abc import abstractmethod
from typing import Dict, Optional, Tuple

from sebs.faas.config import Resources
from sebs.cache import Cache
from sebs.utils import LoggingBase


class NoSQLStorage(ABC, LoggingBase):
    @staticmethod
    @abstractmethod
    def deployment_name() -> str:
        pass

    @property
    def cache_client(self) -> Cache:
        return self._cache_client

    @property
    def region(self):
        return self._region

    def __init__(self, region: str, cache_client: Cache, resources: Resources):
        super().__init__()
        self._cache_client = cache_client
        self._cached = False
        self._region = region
        self._cloud_resources = resources

        # Map benchmark -> orig_name -> table_name
        # self._tables: Dict[str, Dict[str, str]] = defaultdict(dict)

    @abstractmethod
    def get_tables(self, benchmark: str) -> Dict[str, str]:
        pass

    @abstractmethod
    def _get_table_name(self, benchmark: str, table: str) -> Optional[str]:
        pass

    @abstractmethod
    def retrieve_cache(self, benchmark: str) -> bool:
        pass

    @abstractmethod
    def update_cache(self, benchmark: str):
        pass

    def envs(self) -> dict:
        return {}

    """
        Each table name follow this pattern:
        sebs-benchmarks-{resource_id}-{benchmark-name}-{table-name}

        Each implementation should do the following
        (1) Retrieve cached data
        (2) Create missing table that do not exist
        (3) Update cached data if anything new was created
    """

    def create_benchmark_tables(
        self, benchmark: str, name: str, primary_key: str, secondary_key: Optional[str] = None
    ):

        if self.retrieve_cache(benchmark):

            table_name = self._get_table_name(benchmark, name)
            if table_name is not None:
                self.logging.info(
                    f"Using cached NoSQL table {table_name} for benchmark {benchmark}"
                )
                return

        self.logging.info(f"Preparing to create a NoSQL table {name} for benchmark {benchmark}")

        self.create_table(benchmark, name, primary_key, secondary_key)

        self.update_cache(benchmark)

    """

        AWS: DynamoDB Table
        Azure: CosmosDB Container
        Google Cloud: Firestore in Datastore Mode, Database
    """

    @abstractmethod
    def create_table(
        self, benchmark: str, name: str, primary_key: str, secondary_key: Optional[str] = None
    ) -> str:
        pass

    @abstractmethod
    def writer_func(
        self,
        benchmark: str,
        table: str,
        data: dict,
        primary_key: Tuple[str, str],
        secondary_key: Optional[Tuple[str, str]] = None,
    ):
        pass

    """

        AWS DynamoDB: Removing & recreating table is the cheapest & fastest option

        Azure CosmosDB: recreate container

        Google Cloud: also likely recreate

    """

    @abstractmethod
    def clear_table(self, name: str) -> str:
        pass

    @abstractmethod
    def remove_table(self, name: str) -> str:
        pass
