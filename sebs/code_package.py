import glob
import hashlib
import json
import os
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Tuple

import docker

from sebs.config import SeBSConfig
from sebs.cache import Cache
from sebs.utils import find_package_code, project_absolute_path, LoggingBase
from sebs.faas.storage import PersistentStorage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sebs.experiments.config import Config as ExperimentConfig
    from sebs.experiments.config import Language


class CodePackageConfig:
    def __init__(self, timeout: int, memory: int, languages: List["Language"]):
        self._timeout = timeout
        self._memory = memory
        self._languages = languages

    @property
    def timeout(self) -> int:
        return self._timeout

    @property
    def memory(self) -> int:
        return self._memory

    @property
    def languages(self) -> List["Language"]:
        return self._languages

    # FIXME: 3.7+ python with future annotations
    @staticmethod
    def deserialize(json_object: dict) -> "CodePackageConfig":
        from sebs.experiments.config import Language

        return CodePackageConfig(
            json_object["timeout"],
            json_object["memory"],
            [Language.deserialize(x) for x in json_object["languages"]],
        )


"""
    Creates code package representing a benchmark with all code and assets
    prepared and dependency install performed within Docker image corresponding
    to the cloud deployment.

    The behavior of the class depends on cache state:
    1)  First, if there's no cache entry, a code package is built.
    2)  Otherwise, the hash of the entire benchmark is computed and compared
        with the cached value. If changed, then rebuilt then benchmark.
    3)  Otherwise, just return the path to cache code.
"""


class CodePackage(LoggingBase):
    @staticmethod
    def typename() -> str:
        return "CodePackage"

    @property
    def name(self):
        return self._name

    @property
    def path(self):
        return self._path

    @property
    def config(self) -> CodePackageConfig:
        return self._config

    @property
    def payload(self) -> dict:
        return self._payload

    @property
    def benchmarks(self) -> Dict[str, Any]:
        return self._benchmarks

    @property
    def code_location(self):
        if self.payload:
            return os.path.join(self._cache_client.cache_dir, self.payload["location"])
        else:
            return self._code_location

    @property
    def is_cached(self):
        return self._is_cached

    @is_cached.setter
    def is_cached(self, val: bool):
        self._is_cached = val

    @property
    def is_cached_valid(self):
        return self._is_cached_valid

    @is_cached_valid.setter
    def is_cached_valid(self, val: bool):
        self._is_cached_valid = val

    @property
    def code_size(self):
        return self._code_size

    @property
    def language(self) -> "Language":
        return self._language

    @property
    def language_name(self) -> str:
        return self._language.value

    @property
    def language_version(self):
        return self._language_version

    @property  # noqa: A003
    def hash(self):
        path = os.path.join(self.path, self.language_name)
        self._hash_value = CodePackage.hash_directory(
            path, self._deployment_name, self.language_name
        )
        return self._hash_value

    @hash.setter  # noqa: A003
    def hash(self, val: str):
        """
        Used only for testing purposes.
        """
        self._hash_value = val

    def __init__(
        self,
        name: str,
        deployment_name: str,
        config: "ExperimentConfig",
        system_config: SeBSConfig,
        output_dir: str,
        cache_client: Cache,
        docker_client: docker.client,
    ):
        super().__init__()
        self._name = name
        self._deployment_name = deployment_name
        self._experiment_config = config
        self._language = config.runtime.language
        self._language_version = config.runtime.version
        self._path = find_package_code(self.name, "benchmarks")
        if not self._path:
            raise RuntimeError("Benchmark {name} not found!".format(name=self._name))
        with open(os.path.join(self.path, "config.json")) as json_file:
            self._config: CodePackageConfig = CodePackageConfig.deserialize(json.load(json_file))

        if self.language not in self.config.languages:
            raise RuntimeError(
                "Benchmark {} not available for language {}".format(self.name, self.language)
            )
        self._cache_client = cache_client
        self._docker_client = docker_client
        self._system_config = system_config
        self._hash_value = None
        self._output_dir = os.path.join(output_dir, f"{name}_code")

        # verify existence of function in cache
        self.query_cache()
        if config.update_code:
            self._is_cached_valid = False

    """
        Compute MD5 hash of an entire directory.
    """

    @staticmethod
    def hash_directory(directory: str, deployment: str, language: str):

        hash_sum = hashlib.md5()
        FILES = {
            "python": ["*.py", "requirements.txt*"],
            "nodejs": ["*.js", "package.json"],
        }
        WRAPPERS = {"python": "*.py", "nodejs": "*.js"}
        NON_LANG_FILES = ["*.sh", "*.json"]
        selected_files = FILES[language] + NON_LANG_FILES
        for file_type in selected_files:
            for f in glob.glob(os.path.join(directory, file_type)):
                path = os.path.join(directory, f)
                with open(path, "rb") as opened_file:
                    hash_sum.update(opened_file.read())

        # workflow definition
        definition_path = os.path.join(directory, os.path.pardir, "definition.json")
        if os.path.exists(definition_path):
            with open(definition_path, "rb") as opened_file:
                hash_sum.update(opened_file.read())

        # wrappers
        wrappers = project_absolute_path(
            "benchmarks", "wrappers", deployment, language, WRAPPERS[language]
        )
        for f in glob.glob(wrappers):
            path = os.path.join(directory, f)
            with open(path, "rb") as opened_file:
                hash_sum.update(opened_file.read())
        return hash_sum.hexdigest()

    def serialize(self) -> dict:
        return {"size": self.code_size, "hash": self.hash}

    def query_cache(self):
        self._payload = self._cache_client.get_code_package(
            deployment=self._deployment_name,
            benchmark=self._name,
            language=self.language_name,
        )
        self._benchmarks = self._cache_client.get_benchmarks(
            deployment=self._deployment_name,
            benchmark=self._name,
            language=self.language_name,
        )

        if self._payload is not None:
            # compare hashes
            current_hash = self.hash
            old_hash = self._payload["hash"]
            self._code_size = self._payload["size"]
            self._is_cached = True
            self._is_cached_valid = current_hash == old_hash
        else:
            self._is_cached = False
            self._is_cached_valid = False

    def get_code_files(self, include_config=True):
        FILES = {
            "python": ["*.py"],
            "nodejs": ["*.js"],
        }
        if include_config:
            FILES["python"] += ["requirements.txt*", "*.json"]
            FILES["nodejs"] += ["package.json", "*.json"]

        path = os.path.join(self.path, self.language_name)
        for file_type in FILES[self.language_name]:
            for f in glob.glob(os.path.join(path, file_type)):
                yield os.path.join(path, f)

    def copy_code(self, output_dir: str):
        for path in self.get_code_files():
            shutil.copy2(path, output_dir)

    def add_benchmark_data(self, output_dir):
        cmd = "/bin/bash {path}/init.sh {output_dir} false"
        paths = [
            self.path,
            os.path.join(self.path, self.language_name),
        ]
        for path in paths:
            if os.path.exists(os.path.join(path, "init.sh")):
                out = subprocess.run(
                    cmd.format(path=path, output_dir=output_dir),
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                self.logging.debug(out.stdout.decode("utf-8"))

    def add_deployment_files(self, output_dir: str, is_workflow: bool):
        handlers_dir = project_absolute_path(
            "benchmarks", "wrappers", self._deployment_name, self.language_name
        )
        handlers = [
            os.path.join(handlers_dir, file)
            for file in self._system_config.deployment_files(
                self._deployment_name, self.language_name
            )
        ]
        for file in handlers:
            shutil.copy2(file, os.path.join(output_dir))

        if self.language_name == "python":
            handler_path = os.path.join(output_dir, "handler.py")
            handler_function_path = os.path.join(output_dir, "handler_function.py")
            handler_workflow_path = os.path.join(output_dir, "handler_workflow.py")
            if is_workflow:
                os.rename(handler_workflow_path, handler_path)
                os.remove(handler_function_path)
            else:
                os.rename(handler_function_path, handler_path)
                os.remove(handler_workflow_path)

    def add_deployment_package_python(self, output_dir):
        # append to the end of requirements file
        packages = self._system_config.deployment_packages(
            self._deployment_name, self.language_name
        )
        if len(packages):
            with open(os.path.join(output_dir, "requirements.txt"), "a") as out:
                out.write("\n")
                for package in packages:
                    out.write(package + "\n")

    def add_deployment_package_nodejs(self, output_dir):
        # modify package.json
        packages = self._system_config.deployment_packages(
            self._deployment_name, self.language_name
        )
        if len(packages):
            package_config = os.path.join(output_dir, "package.json")
            with open(package_config, "r") as package_file:
                package_json = json.load(package_file)
            for key, val in packages.items():
                package_json["dependencies"][key] = val
            with open(package_config, "w") as package_file:
                json.dump(package_json, package_file, indent=2)

    def add_deployment_package(self, output_dir):
        from sebs.experiments.config import Language

        if self.language == Language.PYTHON:
            self.add_deployment_package_python(output_dir)
        elif self.language == Language.NODEJS:
            self.add_deployment_package_nodejs(output_dir)
        else:
            raise NotImplementedError

    @staticmethod
    def directory_size(directory: str):
        from pathlib import Path

        root = Path(directory)
        sizes = [f.stat().st_size for f in root.glob("**/*") if f.is_file()]
        return sum(sizes)

    def install_dependencies(self, output_dir):
        # do we have docker image for this run and language?
        if "build" not in self._system_config.docker_image_types(
            self._deployment_name, self.language_name
        ):
            self.logging.info(
                (
                    "Docker build image for {deployment} run in {language} "
                    "is not available, skipping"
                ).format(deployment=self._deployment_name, language=self.language_name)
            )
        else:
            repo_name = self._system_config.docker_repository()
            image_name = "build.{deployment}.{language}.{runtime}".format(
                deployment=self._deployment_name,
                language=self.language_name,
                runtime=self.language_version,
            )
            try:
                self._docker_client.images.get(repo_name + ":" + image_name)
            except docker.errors.ImageNotFound:
                try:
                    self.logging.info(
                        "Docker pull of image {repo}:{image}".format(
                            repo=repo_name, image=image_name
                        )
                    )
                    self._docker_client.images.pull(repo_name, image_name)
                except docker.errors.APIError:
                    raise RuntimeError("Docker pull of image {} failed!".format(image_name))

            # Create set of mounted volumes unless Docker volumes are disabled
            if not self._experiment_config.check_flag("docker_copy_build_files"):
                volumes = {os.path.abspath(output_dir): {"bind": "/mnt/function", "mode": "rw"}}
                package_script = os.path.abspath(
                    os.path.join(self._path, self.language_name, "package.sh")
                )
                # does this benchmark has package.sh script?
                if os.path.exists(package_script):
                    volumes[package_script] = {
                        "bind": "/mnt/function/package.sh",
                        "mode": "ro",
                    }

            # run Docker container to install packages
            PACKAGE_FILES = {"python": "requirements.txt", "nodejs": "package.json"}
            file = os.path.join(output_dir, PACKAGE_FILES[self.language_name])
            if os.path.exists(file):
                try:
                    self.logging.info(
                        "Docker build of benchmark dependencies in container "
                        "of image {repo}:{image}".format(repo=repo_name, image=image_name)
                    )
                    uid = os.getuid()
                    # Standard, simplest build
                    if not self._experiment_config.check_flag("docker_copy_build_files"):
                        self.logging.info(
                            "Docker mount of benchmark code from path {path}".format(
                                path=os.path.abspath(output_dir)
                            )
                        )
                        stdout = self._docker_client.containers.run(
                            "{}:{}".format(repo_name, image_name),
                            volumes=volumes,
                            environment={"APP": self.name},
                            # user="1000:1000",
                            user=uid,
                            remove=True,
                            stdout=True,
                            stderr=True,
                        )
                    # Hack to enable builds on platforms where Docker mounted volumes
                    # are not supported. Example: CircleCI docker environment
                    else:
                        container = self._docker_client.containers.run(
                            "{}:{}".format(repo_name, image_name),
                            environment={"APP": self.name},
                            # user="1000:1000",
                            user=uid,
                            # remove=True,
                            detach=True,
                            tty=True,
                            command="/bin/bash",
                        )
                        # copy application files
                        import tarfile

                        self.logging.info(
                            "Send benchmark code from path {path} to "
                            "Docker instance".format(path=os.path.abspath(output_dir))
                        )
                        tar_archive = os.path.join(output_dir, os.path.pardir, "function.tar")
                        with tarfile.open(tar_archive, "w") as tar:
                            for f in os.listdir(output_dir):
                                tar.add(os.path.join(output_dir, f), arcname=f)
                        with open(tar_archive, "rb") as data:
                            container.put_archive("/mnt/function", data.read())
                        # do the build step
                        exit_code, stdout = container.exec_run(
                            cmd="/bin/bash installer.sh", stdout=True, stderr=True
                        )
                        # copy updated code with package
                        data, stat = container.get_archive("/mnt/function")
                        with open(tar_archive, "wb") as f:
                            for chunk in data:
                                f.write(chunk)
                        with tarfile.open(tar_archive, "r") as tar:
                            tar.extractall(output_dir)
                            # docker packs the entire directory with basename function
                            for f in os.listdir(os.path.join(output_dir, "function")):
                                shutil.move(
                                    os.path.join(output_dir, "function", f),
                                    os.path.join(output_dir, f),
                                )
                            shutil.rmtree(os.path.join(output_dir, "function"))
                        container.stop()

                    # Pass to output information on optimizing builds.
                    # Useful for AWS where packages have to obey size limits.
                    for line in stdout.decode("utf-8").split("\n"):
                        if "size" in line:
                            self.logging.info("Docker build: {}".format(line))
                except docker.errors.ContainerError as e:
                    self.logging.error("Package build failed!")
                    self.logging.error(e)
                    self.logging.error(f"Docker mount volumes: {volumes}")
                    raise e

    def recalculate_code_size(self):
        self._code_size = CodePackage.directory_size(self._output_dir)
        return self._code_size

    def build(
        self,
        deployment_build_step: Callable[["CodePackage", str, bool], Tuple[str, int]],
        is_workflow: bool,
    ) -> Tuple[bool, str]:

        # Skip build if files are up to date and user didn't enforce rebuild
        if self.is_cached and self.is_cached_valid:
            self.logging.info(
                "Using cached benchmark {} at {}".format(self.name, self.code_location)
            )
            return False, self.code_location

        msg = (
            "no cached code package."
            if not self.is_cached
            else "cached code package is not up to date/build enforced."
        )
        self.logging.info("Building benchmark {}. Reason: {}".format(self.name, msg))
        # clear existing cache information
        self._payload = None

        # create directory to be deployed
        if os.path.exists(self._output_dir):
            shutil.rmtree(self._output_dir)
        os.makedirs(self._output_dir)

        self.copy_code(self._output_dir)
        self.add_benchmark_data(self._output_dir)
        self.add_deployment_files(self._output_dir, is_workflow)
        self.add_deployment_package(self._output_dir)
        self.install_dependencies(self._output_dir)
        self._code_location, self._code_size = deployment_build_step(
            self, os.path.abspath(self._output_dir), is_workflow
        )
        self.logging.info(
            (
                "Created code package (source hash: {hash}), for run on {deployment}"
                + " with {language}:{runtime}"
            ).format(
                hash=self.hash,
                deployment=self._deployment_name,
                language=self.language_name,
                runtime=self.language_version,
            )
        )

        # package already exists
        if self.is_cached:
            self._cache_client.update_code_package(self._deployment_name, self.language_name, self)
        else:
            self._cache_client.add_code_package(self._deployment_name, self.language_name, self)
        self.query_cache()

        return True, self._code_location

    """
        Locates benchmark input generator, inspect how many storage buckets
        are needed and launches corresponding storage instance, if necessary.

        :param client: Deployment client
        :param benchmark:
        :param path:
        :param size: Benchmark workload size
    """

    def prepare_input(self, storage: PersistentStorage, size: str):
        benchmark_data_path = find_package_code(self.name, "benchmarks-data")
        mod = load_benchmark_input(self._path)
        buckets = mod.buckets_count()
        storage.allocate_buckets(self.name, buckets)
        # Get JSON and upload data as required by benchmark
        input_config = mod.generate_input(
            benchmark_data_path,
            size,
            storage.input,
            storage.output,
            storage.uploader_func,
        )
        return input_config

    """
        This is used in experiments that modify the size of input package.
        This step allows to modify code package without going through the entire pipeline.
    """

    def code_package_modify(self, filename: str, data: bytes):

        if self.is_archive():
            self._update_zip(self.code_location, filename, data)
            new_size = self.recompute_size() / 1024.0 / 1024.0
            self.logging.info(f"Modified zip package {self.code_location}, new size {new_size} MB")
        else:
            raise NotImplementedError()

    """
        AWS: .zip file
        Azure: directory
    """

    def is_archive(self) -> bool:
        if os.path.isfile(self.code_location):
            extension = os.path.splitext(self.code_location)[1]
            return extension in [".zip"]
        return False

    def recompute_size(self) -> float:
        bytes_size = os.path.getsize(self.code_location)
        self._code_size = bytes_size
        return bytes_size

    #  https://stackoverflow.com/questions/25738523/how-to-update-one-file-inside-zip-file-using-python
    @staticmethod
    def _update_zip(zipname: str, filename: str, data: bytes):
        import zipfile
        import tempfile

        # generate a temp file
        tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(zipname))
        os.close(tmpfd)

        # create a temp copy of the archive without filename
        with zipfile.ZipFile(zipname, "r") as zin:
            with zipfile.ZipFile(tmpname, "w") as zout:
                zout.comment = zin.comment  # preserve the comment
                for item in zin.infolist():
                    if item.filename != filename:
                        zout.writestr(item, zin.read(item.filename))

        # replace with the temp archive
        os.remove(zipname)
        os.rename(tmpname, zipname)

        # now add filename with its new data
        with zipfile.ZipFile(zipname, mode="a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, data)


"""
    The interface of `input` module of each benchmark.
    Useful for static type hinting with mypy.
"""


class CodePackageModuleInterface:
    @staticmethod
    def buckets_count() -> Tuple[int, int]:
        pass

    @staticmethod
    def generate_input(
        data_dir: str,
        size: str,
        input_buckets: List[str],
        output_buckets: List[str],
        upload_func: Callable[[int, str, str], None],
    ) -> Dict[str, str]:
        pass


def load_benchmark_input(path: str) -> CodePackageModuleInterface:
    # Look for input generator file in the directory containing benchmark
    import importlib.machinery

    loader = importlib.machinery.SourceFileLoader("input", os.path.join(path, "input.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod  # type: ignore
