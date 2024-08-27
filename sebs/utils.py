import json
import logging
import os
import shutil
import subprocess
import uuid
import click
import datetime

from typing import List, Optional

PROJECT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, "dockerfiles")
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


def append_nested_dict(cfg: dict, keys: List[str], value: Optional[dict]):
    if value:
        # make sure parent keys exist
        for key in keys[:-1]:
            cfg = cfg.setdefault(key, {})
        cfg[keys[-1]] = {**cfg[keys[-1]], **value}


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


def find_benchmark(benchmark: str, path: str):
    benchmarks_dir = os.path.join(PROJECT_DIR, path)
    benchmark_path = find(benchmark, benchmarks_dir)
    return benchmark_path


def global_logging():
    logging_format = "%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s"
    logging_date_format = "%H:%M:%S"
    logging.basicConfig(format=logging_format, datefmt=logging_date_format, level=logging.INFO)


class ColoredWrapper:
    SUCCESS = "\033[92m"
    STATUS = "\033[94m"
    WARNING = "\033[93m"
    ERROR = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"

    def __init__(self, prefix, logger, verbose=True, propagte=False):
        self.verbose = verbose
        self.propagte = propagte
        self.prefix = prefix
        self._logging = logger

    def debug(self, message):
        if self.verbose:
            self._print(message, ColoredWrapper.STATUS)
            if self.propagte:
                self._logging.debug(message)

    def info(self, message):
        self._print(message, ColoredWrapper.SUCCESS)
        if self.propagte:
            self._logging.info(message)

    def warning(self, message):
        self._print(message, ColoredWrapper.WARNING)
        if self.propagte:
            self._logging.warning(message)

    def error(self, message):
        self._print(message, ColoredWrapper.ERROR)
        if self.propagte:
            self._logging.error(message)

    def critical(self, message):
        self._print(message, ColoredWrapper.ERROR)
        if self.propagte:
            self._logging.critical(message)

    def _print(self, message, color):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")
        click.echo(
            f"{color}{ColoredWrapper.BOLD}[{timestamp}]{ColoredWrapper.END} "
            f"{ColoredWrapper.BOLD}{self.prefix}{ColoredWrapper.END} {message}"
        )


class LoggingHandlers:
    def __init__(self, verbose: bool = False, filename: Optional[str] = None):
        logging_format = "%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s"
        logging_date_format = "%H:%M:%S"
        formatter = logging.Formatter(logging_format, logging_date_format)
        self.handler: Optional[logging.FileHandler] = None

        # Remember verbosity for colored wrapper
        self.verbosity = verbose

        # Add file output if needed
        if filename:
            file_out = logging.FileHandler(filename=filename, mode="w")
            file_out.setFormatter(formatter)
            file_out.setLevel(logging.DEBUG if verbose else logging.INFO)
            self.handler = file_out


class LoggingBase:
    def __init__(self):
        uuid_name = str(uuid.uuid4())[0:4]
        if hasattr(self, "typename"):
            self.log_name = f"{self.typename()}-{uuid_name}"
        else:
            self.log_name = f"{self.__class__.__name__}-{uuid_name}"

        self._logging = logging.getLogger(self.log_name)
        self._logging.setLevel(logging.INFO)
        self.wrapper = ColoredWrapper(self.log_name, self._logging)

    @property
    def logging(self) -> ColoredWrapper:
        # This would always print log with color. And only if
        # filename in LoggingHandlers is set, it would log to file.
        return self.wrapper

    @property
    def logging_handlers(self) -> LoggingHandlers:
        return self._logging_handlers

    @logging_handlers.setter
    def logging_handlers(self, handlers: LoggingHandlers):
        self._logging_handlers = handlers

        self._logging.propagate = False
        self.wrapper = ColoredWrapper(
            self.log_name,
            self._logging,
            verbose=handlers.verbosity,
            propagte=handlers.handler is not None,
        )

        if self._logging_handlers.handler is not None:
            self._logging.addHandler(self._logging_handlers.handler)


def has_platform(name: str) -> bool:
    return os.environ.get(f"SEBS_WITH_{name.upper()}", "False").lower() == "true"


def catch_interrupt():

    import signal
    import sys
    import traceback

    def handler(x, y):
        traceback.print_stack()
        sys.exit(signal.SIGINT)

    signal.signal(signal.SIGINT, handler)
