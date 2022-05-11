import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from typing import List, Optional, TextIO, Union

from redis import Redis

PROJECT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
PACK_CODE_APP = "pack_code_{}.sh"


def project_absolute_path(*paths: str):
    return os.path.join(PROJECT_DIR, *paths)


class JSONSerializer(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "serialize"):
            return o.serialize()
        elif isinstance(o, dict):
            return str(o)
        else:
            try:
                return vars(o)
            except TypeError:
                return str(o)


def serialize(obj) -> str:
    if hasattr(obj, "serialize"):
        return json.dumps(obj.serialize(), sort_keys=True, indent=2)
    else:
        return json.dumps(obj, cls=JSONSerializer, sort_keys=True, indent=2)


# Executing with shell provides options such as wildcard expansion
def execute(cmd, shell=False, cwd=None):
    if not shell:
        cmd = cmd.split()
    ret = subprocess.run(
        cmd, shell=shell, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if ret.returncode:
        raise RuntimeError(
            "Running {} failed!\n Output: {}".format(cmd, ret.stdout.decode("utf-8"))
        )
    return ret.stdout.decode("utf-8")


def update_nested_dict(cfg: dict, keys: List[str], value: Optional[str]):
    if value:
        # make sure parent keys exist
        for key in keys[:-1]:
            cfg = cfg.setdefault(key, {})
        cfg[keys[-1]] = value


def find(name, path):
    for root, dirs, files in os.walk(path):
        if name in dirs:
            return os.path.join(root, name)
    return None


def create_output(directory, preserve_dir, verbose):
    output_dir = os.path.abspath(directory)
    if os.path.exists(output_dir) and not preserve_dir:
        shutil.rmtree(output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    configure_logging()

    return output_dir


def configure_logging():

    # disable information from libraries logging to decrease output noise
    loggers = ["urrlib3", "docker", "botocore"]
    for name in logging.root.manager.loggerDict:
        for logger in loggers:
            if name.startswith(logger):
                logging.getLogger(name).setLevel(logging.ERROR)


def replace_string_in_file(path: str, from_str: str, to_str: str):
    with open(path, "rt") as f:
        data = f.read()

    data = data.replace(from_str, to_str)

    with open(path, "wt") as f:
        f.write(data)


def connect_to_redis_cache(host: str):
    redis = Redis(host=host, port=6379, decode_responses=True, socket_connect_timeout=10)
    redis.ping()

    return redis


def download_measurements(redis: Redis, workflow_name: str, after: float, **static_args):
    payloads = []

    for key in redis.scan_iter(match=f"{workflow_name}/*"):
        assert key[: len(workflow_name)] == workflow_name

        payload = redis.get(key)
        redis.delete(key)

        if payload:
            try:
                payload = json.loads(payload)

                # make sure only measurements from our benchmark are saved
                if payload["start"] > after:
                    payload = {**payload, **static_args}
                    payloads.append(payload)
            except json.decoder.JSONDecodeError:
                print(f"Failed to decode payload: {payload}")

    return payloads


# def configure_logging(verbose: bool = False, output_dir: Optional[str] = None):
#    logging_format = "%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s"
#    logging_date_format = "%H:%M:%S"
#
#    # default file log
#    options = {
#        "format": logging_format,
#        "datefmt": logging_date_format,
#        "level": logging.DEBUG if verbose else logging.INFO,
#    }
#    if output_dir:
#        options = {
#            **options,
#            "filename": os.path.join(output_dir, "out.log"),
#            "filemode": "w",
#        }
#    logging.basicConfig(**options)
#    # Add stdout output
#    if output_dir:
#        stdout = logging.StreamHandler(sys.stdout)
#        formatter = logging.Formatter(logging_format, logging_date_format)
#        stdout.setFormatter(formatter)
#        stdout.setLevel(logging.DEBUG if verbose else logging.INFO)
#        logging.getLogger().addHandler(stdout)
#    # disable information from libraries logging to decrease output noise
#    for name in logging.root.manager.loggerDict:
#        if (
#            name.startswith("urllib3")
#            or name.startswith("docker")
#            or name.startswith("botocore")
#        ):
#            logging.getLogger(name).setLevel(logging.ERROR)


"""
    Locate directory corresponding to a benchmark in benchmarks
    or benchmarks-data directory.

    :param benchmark: Benchmark name.
    :param path: Path for lookup, relative to repository.
    :return: relative path to directory corresponding to benchmark
"""


def find_package_code(benchmark: str, path: str):
    benchmarks_dir = os.path.join(PROJECT_DIR, path)
    benchmark_path = find(benchmark, benchmarks_dir)
    return benchmark_path


def global_logging():
    logging_format = "%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s"
    logging_date_format = "%H:%M:%S"
    logging.basicConfig(format=logging_format, datefmt=logging_date_format, level=logging.INFO)


class LoggingHandlers:
    def __init__(self, verbose: bool = False, filename: Optional[str] = None):
        logging_format = "%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s"
        logging_date_format = "%H:%M:%S"
        formatter = logging.Formatter(logging_format, logging_date_format)
        self.handlers: List[Union[logging.FileHandler, logging.StreamHandler[TextIO]]] = []

        # Add stdout output
        if verbose:
            stdout = logging.StreamHandler(sys.stdout)
            stdout.setFormatter(formatter)
            stdout.setLevel(logging.DEBUG if verbose else logging.INFO)
            self.handlers.append(stdout)

        # Add file output if needed
        if filename:
            file_out = logging.FileHandler(filename=filename, mode="w")
            file_out.setFormatter(formatter)
            file_out.setLevel(logging.DEBUG if verbose else logging.INFO)
            self.handlers.append(file_out)


class LoggingBase:
    def __init__(self):
        uuid_name = str(uuid.uuid4())[0:4]
        if hasattr(self, "typename"):
            self.logging = logging.getLogger(f"{self.typename()}-{uuid_name}")
        else:
            self.logging = logging.getLogger(f"{self.__class__.__name__}-{uuid_name}")
        self.logging.setLevel(logging.INFO)

    @property
    def logging_handlers(self) -> LoggingHandlers:
        return self._logging_handlers

    @logging_handlers.setter
    def logging_handlers(self, handlers: LoggingHandlers):
        self._logging_handlers = handlers
        self.logging.propagate = False
        for handler in handlers.handlers:
            self.logging.addHandler(handler)


def has_platform(name: str) -> bool:
    return os.environ.get(f"SEBS_WITH_{name.upper()}", "False").lower() == "true"
