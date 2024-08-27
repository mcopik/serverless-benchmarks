# https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
import collections.abc
import datetime
import json
import os
import shutil
import threading
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING  # noqa

from sebs.utils import LoggingBase, serialize

if TYPE_CHECKING:
    from sebs.benchmark import Benchmark
    from sebs.faas.function import Function


def update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def update_dict(cfg, val, keys):
    def map_keys(obj, val, keys):
        if len(keys):
            return {keys[0]: map_keys(obj, val, keys[1:])}
        else:
            return val

    update(cfg, map_keys(cfg, val, keys))


class Cache(LoggingBase):

    cached_config: Dict[str, str] = {}
    """
        Indicate that cloud offerings updated credentials or settings.
        Thus we have to write down changes.
    """
    config_updated = False

    def __init__(self, cache_dir: str):
        super().__init__()
        self.cache_dir = os.path.abspath(cache_dir)
        self.ignore_functions: bool = False
        self.ignore_storage: bool = False
        self._lock = threading.RLock()
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
        else:
            self.load_config()

    @staticmethod
    def typename() -> str:
        return "Benchmark"

    def load_config(self):
        with self._lock:
            for cloud in ["azure", "aws", "gcp", "openwhisk"]:
                cloud_config_file = os.path.join(self.cache_dir, "{}.json".format(cloud))
                if os.path.exists(cloud_config_file):
                    self.cached_config[cloud] = json.load(open(cloud_config_file, "r"))

    def get_config(self, cloud):
        return self.cached_config[cloud] if cloud in self.cached_config else None

    """
        Update config values. Sets flag to save updated content in the end.
        val: new value to store
        keys: array of consecutive keys for multi-level dictionary
    """

    def update_config(self, val, keys):
        with self._lock:
            update_dict(self.cached_config, val, keys)
        self.config_updated = True

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

    def shutdown(self):
        if self.config_updated:
            for cloud in ["azure", "aws", "gcp", "openwhisk"]:
                if cloud in self.cached_config:
                    cloud_config_file = os.path.join(self.cache_dir, "{}.json".format(cloud))
                    self.logging.info("Update cached config {}".format(cloud_config_file))
                    with open(cloud_config_file, "w") as out:
                        json.dump(self.cached_config[cloud], out, indent=2)

    """
        Access cached config of a benchmark.

        :param deployment: allowed deployment clouds or local
        :param benchmark:
        :param  language:

        :return: a JSON config or None when not exists
    """

    def get_benchmark_config(self, deployment: str, benchmark: str):
        benchmark_dir = os.path.join(self.cache_dir, benchmark)
        if os.path.exists(benchmark_dir):
            with open(os.path.join(benchmark_dir, "config.json"), "r") as fp:
                cfg = json.load(fp)
                return cfg[deployment] if deployment in cfg else None

    """
        Access cached version of benchmark code.

        :param deployment: allowed deployment clouds or local
        :param benchmark:
        :param  language:

        :return: a tuple of JSON config and absolute path to code or None
    """

    def get_code_package(
        self, deployment: str, benchmark: str, language: str, language_version: str
    ) -> Optional[Dict[str, Any]]:
        cfg = self.get_benchmark_config(deployment, benchmark)
        if cfg and language in cfg and language_version in cfg[language]["code_package"]:
            return cfg[language]["code_package"][language_version]
        else:
            return None

    def get_functions(
        self, deployment: str, benchmark: str, language: str
    ) -> Optional[Dict[str, Any]]:
        cfg = self.get_benchmark_config(deployment, benchmark)
        if cfg and language in cfg and not self.ignore_functions:
            return cfg[language]["functions"]
        else:
            return None

    """
        Access cached storage config of a benchmark.

        :param deployment: allowed deployment clouds or local
        :param benchmark:

        :return: a JSON config or None
    """

    def get_storage_config(self, deployment: str, benchmark: str):
        return self._get_resource_config(deployment, benchmark, "storage")

    def get_nosql_config(self, deployment: str, benchmark: str):
        return self._get_resource_config(deployment, benchmark, "nosql")

    def _get_resource_config(self, deployment: str, benchmark: str, resource: str):
        cfg = self.get_benchmark_config(deployment, benchmark)
        return cfg[resource] if cfg and resource in cfg and not self.ignore_storage else None

    def update_storage(self, deployment: str, benchmark: str, config: dict):
        if self.ignore_storage:
            return
        self._update_resources(deployment, benchmark, "storage", config)

    def update_nosql(self, deployment: str, benchmark: str, config: dict):
        if self.ignore_storage:
            return
        self._update_resources(deployment, benchmark, "nosql", config)

    def _update_resources(self, deployment: str, benchmark: str, resource: str, config: dict):
        if self.ignore_storage:
            return

        """
            We are now preparing benchmark data before caching function.
            Thus, we have to take over a situation where the cache directory does not exist.
        """

        benchmark_dir = os.path.join(self.cache_dir, benchmark)
        os.makedirs(benchmark_dir, exist_ok=True)

        with self._lock:

            if os.path.exists(os.path.join(benchmark_dir, "config.json")):
                with open(os.path.join(benchmark_dir, "config.json"), "r") as fp:
                    cached_config = json.load(fp)
            else:
                cached_config = {}

            if deployment in cached_config:
                cached_config[deployment][resource] = config
            else:
                cached_config[deployment] = {resource: config}

            with open(os.path.join(benchmark_dir, "config.json"), "w") as fp:
                json.dump(cached_config, fp, indent=2)

    def add_code_package(self, deployment_name: str, language_name: str, code_package: "Benchmark"):
        with self._lock:
            language = code_package.language_name
            language_version = code_package.language_version
            benchmark_dir = os.path.join(self.cache_dir, code_package.benchmark)
            os.makedirs(benchmark_dir, exist_ok=True)
            # Check if cache directory for this deployment exist
            cached_dir = os.path.join(benchmark_dir, deployment_name, language, language_version)
            if not os.path.exists(cached_dir):
                os.makedirs(cached_dir, exist_ok=True)

                # copy code
                if os.path.isdir(code_package.code_location):
                    cached_location = os.path.join(cached_dir, "code")
                    shutil.copytree(code_package.code_location, cached_location)
                # copy zip file
                else:
                    package_name = os.path.basename(code_package.code_location)
                    cached_location = os.path.join(cached_dir, package_name)
                    shutil.copy2(code_package.code_location, cached_dir)
                language_config = code_package.serialize()
                # don't store absolute path to avoid problems with moving cache dir
                relative_cached_loc = os.path.relpath(cached_location, self.cache_dir)
                language_config["location"] = relative_cached_loc
                date = str(datetime.datetime.now())
                language_config["date"] = {
                    "created": date,
                    "modified": date,
                }
                # config = {deployment_name: {language: language_config}}
                config = {
                    deployment_name: {
                        language: {
                            "code_package": {language_version: language_config},
                            "functions": {},
                        }
                    }
                }

                # make sure to not replace other entries
                if os.path.exists(os.path.join(benchmark_dir, "config.json")):
                    with open(os.path.join(benchmark_dir, "config.json"), "r") as fp:
                        cached_config = json.load(fp)
                        if deployment_name in cached_config:
                            # language known, platform known, extend dictionary
                            if language in cached_config[deployment_name]:
                                cached_config[deployment_name][language]["code_package"][
                                    language_version
                                ] = language_config
                            # language unknown, platform known - add new dictionary
                            else:
                                cached_config[deployment_name][language] = config[deployment_name][
                                    language
                                ]
                        else:
                            # language unknown, platform unknown - add new dictionary
                            cached_config[deployment_name] = config[deployment_name]
                        config = cached_config
                with open(os.path.join(benchmark_dir, "config.json"), "w") as fp:
                    json.dump(config, fp, indent=2)
            else:
                # TODO: update
                raise RuntimeError(
                    "Cached application {} for {} already exists!".format(
                        code_package.benchmark, deployment_name
                    )
                )

    def update_code_package(
        self, deployment_name: str, language_name: str, code_package: "Benchmark"
    ):
        with self._lock:
            language = code_package.language_name
            language_version = code_package.language_version
            benchmark_dir = os.path.join(self.cache_dir, code_package.benchmark)
            # Check if cache directory for this deployment exist
            cached_dir = os.path.join(benchmark_dir, deployment_name, language, language_version)
            if os.path.exists(cached_dir):

                # copy code
                if os.path.isdir(code_package.code_location):
                    cached_location = os.path.join(cached_dir, "code")
                    # could be replaced with dirs_exists_ok in copytree
                    # available in 3.8
                    shutil.rmtree(cached_location)
                    shutil.copytree(src=code_package.code_location, dst=cached_location)
                # copy zip file
                else:
                    package_name = os.path.basename(code_package.code_location)
                    cached_location = os.path.join(cached_dir, package_name)
                    if code_package.code_location != cached_location:
                        shutil.copy2(code_package.code_location, cached_dir)

                with open(os.path.join(benchmark_dir, "config.json"), "r") as fp:
                    config = json.load(fp)
                    date = str(datetime.datetime.now())
                    config[deployment_name][language]["code_package"][language_version]["date"][
                        "modified"
                    ] = date
                    config[deployment_name][language]["code_package"][language_version][
                        "hash"
                    ] = code_package.hash
                with open(os.path.join(benchmark_dir, "config.json"), "w") as fp:
                    json.dump(config, fp, indent=2)
            else:
                self.add_code_package(deployment_name, language_name, code_package)

    """
        Add new function to cache.

        :param deployment:
        :param benchmark:
        :param language:
        :param code_package: Path to directory/ZIP with code.
        :param language_config: Configuration of language and code.
        :param storage_config: Configuration of storage buckets.
    """

    def add_function(
        self,
        deployment_name: str,
        language_name: str,
        code_package: "Benchmark",
        function: "Function",
    ):
        if self.ignore_functions:
            return
        with self._lock:
            benchmark_dir = os.path.join(self.cache_dir, code_package.benchmark)
            language = code_package.language_name
            cache_config = os.path.join(benchmark_dir, "config.json")

            if os.path.exists(cache_config):
                functions_config: Dict[str, Any] = {function.name: {**function.serialize()}}

                with open(cache_config, "r") as fp:
                    cached_config = json.load(fp)
                    if "functions" not in cached_config[deployment_name][language]:
                        cached_config[deployment_name][language]["functions"] = functions_config
                    else:
                        cached_config[deployment_name][language]["functions"].update(
                            functions_config
                        )
                    config = cached_config
                with open(cache_config, "w") as fp:
                    fp.write(serialize(config))
            else:
                raise RuntimeError(
                    "Can't cache function {} for a non-existing code package!".format(function.name)
                )

    def update_function(self, function: "Function"):
        if self.ignore_functions:
            return
        with self._lock:
            benchmark_dir = os.path.join(self.cache_dir, function.benchmark)
            cache_config = os.path.join(benchmark_dir, "config.json")

            if os.path.exists(cache_config):

                with open(cache_config, "r") as fp:
                    cached_config = json.load(fp)
                    for deployment, cfg in cached_config.items():
                        for language, cfg2 in cfg.items():
                            if "functions" not in cfg2:
                                continue
                            for name, func in cfg2["functions"].items():
                                if name == function.name:
                                    cached_config[deployment][language]["functions"][
                                        name
                                    ] = function.serialize()
                with open(cache_config, "w") as fp:
                    fp.write(serialize(cached_config))
            else:
                raise RuntimeError(
                    "Can't cache function {} for a non-existing code package!".format(function.name)
                )
