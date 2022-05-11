import os
import tempfile
import unittest
import zipfile
from typing import List

import sebs


class AWSCreateFunction(unittest.TestCase):
    config = {
        "python": {
            "deployment": {"name": "aws", "aws": {"region": "us-east-1"}},
            "experiments": {
                "runtime": {"language": "python", "version": "3.6"},
                "update_code": False,
                "update_storage": False,
                "download_results": False,
                "flags": {
                    "docker_copy_build_files": True
                }
            },
        },
        "nodejs": {
            "deployment": {"name": "aws", "aws": {"region": "us-east-1"}},
            "experiments": {
                "runtime": {"language": "nodejs", "version": "10.x"},
                "update_code": False,
                "update_storage": False,
                "download_results": False,
                "flags": {
                    "docker_copy_build_files": True
                }
            }
        }
    }
    package_files = {
        "python": ["handler.py", "function/storage.py", "requirements.txt", '.python_packages/'],
        "nodejs": ["handler.js", "function/storage.js", "package.json", "node_modules/"]
    }
    benchmark = "110.dynamic-html"
    function_name_suffixes = []

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.client = sebs.SeBS(self.tmp_dir.name)
        for i in range(0, 4):
            self.function_name_suffixes.append("_test_runner_{}".format(i))
        for language in ["python", "nodejs"]:
            config = self.config[language]
            deployment_client = self.client.get_deployment(config["deployment"])
            deployment_client.initialize()
            experiment_config = self.client.get_experiment(config["experiments"])
            benchmark = self.client.get_benchmark(
                self.benchmark, self.tmp_dir.name, deployment_client, experiment_config
            )

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.client = sebs.SeBS(cls.tmp_dir.name)
        for i in range(0, 4):
            cls.function_name_suffixes.append("_test_runner_{}".format(i))
        for language in ["python", "nodejs"]:
            config = cls.config[language]
            deployment_client = cls.client.get_deployment(config["deployment"])
            experiment_config = cls.client.get_experiment(config["experiments"])
            benchmark = cls.client.get_benchmark(
                cls.benchmark, cls.tmp_dir.name, deployment_client, experiment_config
            )
            func_name = deployment_client.default_benchmark_name(benchmark)
            for suffix in cls.function_name_suffixes:
                deployment_client.delete_function(func_name + suffix)

    def tearDown(self):
        for language in ["python", "nodejs"]:
            config = self.config[language]
            deployment_client = self.client.get_deployment(config["deployment"])
            deployment_client.initialize()
            experiment_config = self.client.get_experiment(config["experiments"])
            benchmark = self.client.get_benchmark(
                self.benchmark, self.tmp_dir.name, deployment_client, experiment_config
            )

    @classmethod
    def tearDownClass(cls):
        for language in ["python", "nodejs"]:
            config = cls.config[language]
            deployment_client = cls.client.get_deployment(config["deployment"])
            experiment_config = cls.client.get_experiment(config["experiments"])
            benchmark = cls.client.get_benchmark(
                cls.benchmark, cls.tmp_dir.name, deployment_client, experiment_config
            )
            func_name = deployment_client.default_benchmark_name(benchmark)
            for suffix in cls.function_name_suffixes:
                deployment_client.delete_function(func_name + suffix)

    def check_function(
        self, language: str, package: sebs.code_package.CodePackage, files: List[str]
    ):
        filename, file_extension = os.path.splitext(package.code_location)
        self.assertEqual(file_extension, ".zip")

        # check zip file contents
        with zipfile.ZipFile(package.code_location) as package:
            package_files = package.namelist()
            for package_file in files:
                # check directory - ZipFile lists only files, so we must
                # check that at least one of them is in this directory
                if package_file.endswith("/"):
                    self.assertTrue(any(f.startswith(package_file) for f in package_files))
                # check file
                else:
                    self.assertIn(package_file, package_files)

    def generate_benchmark(self, tmp_dir, language: str):
        config = self.config[language]
        deployment_client = self.client.get_deployment(config["deployment"])
        deployment_client.initialize()
        experiment_config = self.client.get_experiment(config["experiments"])
        benchmark = self.client.get_benchmark(
            self.benchmark, tmp_dir.name, deployment_client, experiment_config
        )
        self.assertIsInstance(deployment_client, sebs.aws.AWS)
        self.assertFalse(benchmark.is_cached)
        self.assertFalse(benchmark.is_cached_valid)
        return benchmark, deployment_client, experiment_config

    def test_create_function(self):
        tmp_dir = tempfile.TemporaryDirectory()
        for language in ["python", "nodejs"]:
            benchmark, deployment_client, experiment_config = self.generate_benchmark(tmp_dir, language)

            func_name = deployment_client.default_benchmark_name(benchmark) + self.function_name_suffixes[0]
            func = deployment_client.get_function(benchmark, func_name)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.assertEqual(func.name, func_name)
            self.check_function(language, benchmark, self.package_files[language])

    def test_retrieve_cache(self):
        tmp_dir = tempfile.TemporaryDirectory()
        for language in ["python", "nodejs"]:
            benchmark, deployment_client, experiment_config = self.generate_benchmark(tmp_dir, language)

            # generate default variant
            func_name = deployment_client.default_benchmark_name(benchmark) + self.function_name_suffixes[1]
            func = deployment_client.get_function(benchmark, func_name)
            timestamp = os.path.getmtime(benchmark.code_location)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.check_function(language, benchmark, self.package_files[language])
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            self.assertEqual(func.name, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)

            # use cached version
            benchmark = self.client.get_benchmark(
                self.benchmark, tmp_dir.name, deployment_client, experiment_config
            )
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            func = deployment_client.get_function(benchmark, func_name)
            current_timestamp = os.path.getmtime(benchmark.code_location)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.check_function(language, benchmark, self.package_files[language])
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            self.assertEqual(func.code_package_hash, benchmark.hash)
            # package code has not been rebuilt
            self.assertEqual(timestamp, current_timestamp)

    def test_rebuild_function(self):
        tmp_dir = tempfile.TemporaryDirectory()
        for language in ["python", "nodejs"]:
            benchmark, deployment_client, experiment_config = self.generate_benchmark(tmp_dir, language)

            # generate default variant
            func_name = deployment_client.default_benchmark_name(benchmark) + self.function_name_suffixes[2]
            func = deployment_client.get_function(benchmark, func_name)
            timestamp = os.path.getmtime(benchmark.code_location)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.check_function(language, benchmark, self.package_files[language])
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            self.assertEqual(func.name, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)

            # force rebuild of cached version
            experiment_config.update_code = True
            benchmark = self.client.get_benchmark(
                self.benchmark, tmp_dir.name, deployment_client, experiment_config
            )
            self.assertTrue(benchmark.is_cached)
            self.assertFalse(benchmark.is_cached_valid)
            func = deployment_client.get_function(benchmark, func_name)
            current_timestamp = os.path.getmtime(benchmark.code_location)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.check_function(language, benchmark, self.package_files[language])
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            self.assertEqual(func.name, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)
            # package should have been rebuilt
            self.assertLess(timestamp, current_timestamp)

    def test_update_function(self):
        tmp_dir = tempfile.TemporaryDirectory()
        for language in ["python", "nodejs"]:
            benchmark, deployment_client, experiment_config = self.generate_benchmark(tmp_dir, language)

            # generate default variant
            func_name = deployment_client.default_benchmark_name(benchmark) + self.function_name_suffixes[3]
            func = deployment_client.get_function(benchmark, func_name)
            timestamp = os.path.getmtime(benchmark.code_location)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.check_function(language, benchmark, self.package_files[language])
            self.assertTrue(benchmark.is_cached)
            self.assertTrue(benchmark.is_cached_valid)
            self.assertEqual(func.name, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)

            # change hash of benchmark - function should be reuploaded
            benchmark.hash = benchmark.hash + "s"
            deployment_client.cache_client.update_code_package(deployment_client.name(), language, benchmark)
            func = deployment_client.get_function(benchmark, func_name)
            self.assertIsInstance(func, sebs.aws.LambdaFunction)
            self.assertEqual(func.name, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)
            self.assertTrue(func.updated_code)

            # get the same function again - should be retrieved from updated cache
            func = deployment_client.get_function(benchmark, func_name)
            self.assertEqual(func.code_package_hash, benchmark.hash)
            self.assertFalse(func.updated_code)

    def test_incorrect_runtime(self):
        tmp_dir = tempfile.TemporaryDirectory()
        # wrong language version - expect failure
        for language in ["python", "nodejs"]:
            config = self.config[language]
            deployment_client = self.client.get_deployment(config["deployment"])
            deployment_client.initialize()
            self.assertIsInstance(deployment_client, sebs.aws.AWS)
            experiment_config = self.client.get_experiment(config["experiments"])
            experiment_config.runtime.version = "1.0"
            with self.assertRaises(Exception) as failure:
                benchmark = self.client.get_benchmark(
                    self.benchmark, tmp_dir.name, deployment_client, experiment_config
                )
                func = deployment_client.get_function(benchmark)
            self.assertTrue(
                "Unsupported {} version 1.0".format(language) in str(failure.exception)
            )
