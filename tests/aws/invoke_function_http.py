import os
import tempfile
import unittest
import zipfile
from typing import Dict, List

import sebs


class AWSInvokeFunctionHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.client = sebs.SeBS(self.tmp_dir.name)

    def invoke_sync(self, func: sebs.aws.LambdaFunction, func_input: dict):
        ret = func.triggers[1].sync_invoke(func_input)
        self.assertFalse(ret.stats.failure)
        # check that these values are not empty
        self.assertTrue(ret.request_id)
        self.assertGreater(ret.times.client, ret.times.benchmark)

    def test_invoke_sync_python(self):
        config = {
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
        }
        benchmark_name = "110.dynamic-html"
        deployment_client = self.client.get_deployment(config["deployment"])
        deployment_client.initialize()
        experiment_config = self.client.get_experiment(config["experiments"])
        benchmark = self.client.get_benchmark(
            benchmark_name, self.tmp_dir.name, deployment_client, experiment_config
        )
        bench_input = benchmark.prepare_input(
            storage=deployment_client.get_storage(), size="test"
        )
        func = deployment_client.get_function(benchmark, '{}-http'.format(sebs.aws.AWS.default_benchmark_name(benchmark)))
        from sebs.faas.benchmark import Trigger
        deployment_client.create_trigger(func, Trigger.TriggerType.HTTP)
        self.invoke_sync(func, bench_input)

    def test_invoke_sync_nodejs(self):
        config = {
            "deployment": {"name": "aws", "aws": {"region": "us-east-1"}},
            "experiments": {
                "runtime": {"language": "nodejs", "version": "10.x"},
                "update_code": False,
                "update_storage": False,
                "download_results": False,
                "flags": {
                    "docker_copy_build_files": True
                }
            },
        }
        benchmark_name = "110.dynamic-html"
        deployment_client = self.client.get_deployment(config["deployment"])
        deployment_client.initialize()
        experiment_config = self.client.get_experiment(config["experiments"])
        benchmark = self.client.get_benchmark(
            benchmark_name, self.tmp_dir.name, deployment_client, experiment_config
        )
        bench_input = benchmark.prepare_input(
            storage=deployment_client.get_storage(), size="test"
        )
        func = deployment_client.get_function(benchmark, '{}-http'.format(sebs.aws.AWS.default_benchmark_name(benchmark)))
        from sebs.faas.benchmark import Trigger
        deployment_client.create_trigger(func, Trigger.TriggerType.HTTP)
        self.invoke_sync(func, bench_input)

