from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from sebs.cache import Cache
from sebs.faas.config import Resources
from sebs.faas.nosql import NoSQLStorage
from sebs.gcp.cli import GCloudCLI

from google.cloud import datastore


@dataclass
class BenchmarkResources:

    database: str
    kinds: List[str]
    # We allocate this dynamically - ignore when caching
    database_client: Optional[datastore.Client] = None

    def serialize(self) -> dict:
        return {"database": self.database, "kinds": self.kinds}

    @staticmethod
    def deserialize(config: dict) -> "BenchmarkResources":
        return BenchmarkResources(database=config["database"], kinds=config["kinds"])


class Datastore(NoSQLStorage):
    @staticmethod
    def typename() -> str:
        return "GCP.Datastore"

    @staticmethod
    def deployment_name():
        return "gcp"

    def __init__(
        self, cli_instance: GCloudCLI, cache_client: Cache, resources: Resources, region: str
    ):
        super().__init__(region, cache_client, resources)
        self._cli_instance = cli_instance
        self._region = region

        # Mapping: benchmark -> Datastore database
        self._benchmark_resources: Dict[str, BenchmarkResources] = {}

    """
        GCP requires no table mappings: the name of "kind" is the same as benchmark name.
    """

    def get_tables(self, benchmark: str) -> Dict[str, str]:
        return {}

    def _get_table_name(self, benchmark: str, table: str) -> Optional[str]:

        if benchmark not in self._benchmark_resources:
            return None

        if table not in self._benchmark_resources[benchmark].kinds:
            return None

        return table

    def retrieve_cache(self, benchmark: str) -> bool:

        if benchmark in self._benchmark_resources:
            return True

        cached_storage = self.cache_client.get_nosql_config(self.deployment_name(), benchmark)
        if cached_storage is not None:
            self._benchmark_resources[benchmark] = BenchmarkResources.deserialize(cached_storage)
            return True

        return False

    def update_cache(self, benchmark: str):

        self._cache_client.update_nosql(
            self.deployment_name(), benchmark, self._benchmark_resources[benchmark].serialize()
        )

    def benchmark_database(self, benchmark: str) -> str:
        return self._benchmark_resources[benchmark].database

    def writer_func(
        self,
        benchmark: str,
        table: str,
        data: dict,
        primary_key: Tuple[str, str],
        secondary_key: Optional[Tuple[str, str]] = None,
    ):

        res = self._benchmark_resources[benchmark]
        table_name = self._get_table_name(benchmark, table)

        # FIXME: support both options
        assert secondary_key is not None

        if res.database_client is None:
            res.database_client = datastore.Client(database=res.database)

        parent_key = res.database_client.key(secondary_key[0], secondary_key[1])
        key = res.database_client.key(
            # kind determines the table
            table_name,
            # main ID key
            secondary_key[1],
            # organization key
            parent=parent_key,
        )

        val = datastore.Entity(key=key)
        val.update(data)
        res.database_client.put(val)

    def create_table(
        self, benchmark: str, name: str, primary_key: str, _: Optional[str] = None
    ) -> str:

        benchmark_resources = self._benchmark_resources.get(benchmark, None)

        if benchmark_resources is not None and name in benchmark_resources.kinds:
            self.logging.info(f"Using cached Datastore kind {name}")
            return name

        """
            No data for this benchmark -> we need to allocate a new Datastore database.
        """

        if benchmark_resources is None:

            database_name = f"sebs-benchmarks-{self._cloud_resources.resources_id}-{benchmark}"

            try:

                self._cli_instance.execute(
                    "gcloud firestore databases describe "
                    f" --database='{database_name}' "
                    " --format='json'"
                )

            except RuntimeError as e:

                if "NOT_FOUND" in str(e):

                    """
                    Allocate a new Firestore database, in datastore mode
                    """

                    self.logging.info(f"Allocating a new Firestore database {database_name}")
                    self._cli_instance.execute(
                        "gcloud firestore databases create "
                        f" --database='{database_name}' "
                        f" --location={self.region} "
                        f" --type='datastore-mode' "
                    )
                    self.logging.info(f"Allocated a new Firestore database {database_name}")

                else:

                    self.logging.error("Couldn't query Datastore instances!")
                    self.logging.error(e)
                    raise RuntimeError("Couldn't query Datastore instances!")

            db_client = datastore.Client(database=database_name)
            benchmark_resources = BenchmarkResources(
                database=database_name, kinds=[], database_client=db_client
            )
            self._benchmark_resources[benchmark] = benchmark_resources

        benchmark_resources.kinds.append(name)

        return name

    def clear_table(self, name: str) -> str:
        raise NotImplementedError()

    def remove_table(self, name: str) -> str:
        raise NotImplementedError()
