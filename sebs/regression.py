import unittest
import testtools
import threading
from time import sleep
from typing import cast, Dict, Optional, Set, TYPE_CHECKING

from sebs.faas.benchmark import Trigger

if TYPE_CHECKING:
    from sebs import SeBS

benchmarks = [
    "110.dynamic-html",
    "120.uploader",
    "210.thumbnailer",
    "220.video-processing",
    "311.compression",
    "411.image-recognition",
    "501.graph-pagerank",
    "502.graph-mst",
    "503.graph-bfs",
    "504.dna-visualisation",
]

# user-defined config passed during initialization
cloud_config: Optional[dict] = None


class TestSequenceMeta(type):
    def __init__(cls, name, bases, attrs, deployment_name, triggers):
        type.__init__(cls, name, bases, attrs)
        cls.deployment_name = deployment_name
        cls.triggers = triggers

    def __new__(mcs, name, bases, dict, deployment_name, triggers):
        def gen_test(benchmark_name):
            def test(self):
                deployment_client = self.get_deployment(benchmark_name)
                print(
                    f"Begin regression test of {benchmark_name} on {deployment_client.name()}, "
                    f"region: {deployment_client.config.region}."
                )
                experiment_config = self.client.get_experiment_config(self.experiment_config)
                benchmark = self.client.get_benchmark(
                    benchmark_name, deployment_client, experiment_config
                )
                storage = deployment_client.get_storage(
                    replace_existing=experiment_config.update_storage
                )
                func = deployment_client.get_function(
                    benchmark, deployment_client.default_benchmark_name(benchmark)
                )
                input_config = benchmark.prepare_input(storage=storage, size="test")

                failure = False
                for trigger_type in triggers:
                    if len(func.triggers(trigger_type)) > 0:
                        trigger = func.triggers(trigger_type)[0]
                    else:
                        trigger = deployment_client.create_trigger(func, trigger_type)
                        """
                            sleep 5 seconds - on some cloud systems the triggers might
                            not be available immediately.
                            for example, AWS tends to throw "not exist" on newly created
                            API gateway
                        """
                        sleep(5)
                    # Synchronous invoke
                    try:
                        ret = trigger.sync_invoke(input_config)
                        if ret.stats.failure:
                            failure = True
                            print(f"{benchmark_name} fail on trigger: {trigger_type}")
                        else:
                            print(f"{benchmark_name} success on trigger: {trigger_type}")
                    except RuntimeError:
                        failure = True
                        print(f"{benchmark_name} fail on trigger: {trigger_type}")
                deployment_client.shutdown()
                if failure:
                    raise RuntimeError(f"Test of {benchmark_name} failed!")

            return test

        for benchmark in benchmarks:
            for trigger in triggers:
                test_name = "test_%s" % benchmark
                dict[test_name] = gen_test(benchmark)
        dict["lock"] = threading.Lock()
        dict["cfg"] = None
        return type.__new__(mcs, name, bases, dict)


class AWSTestSequence(
    unittest.TestCase,
    metaclass=TestSequenceMeta,
    deployment_name="aws",
    triggers=[Trigger.TriggerType.LIBRARY, Trigger.TriggerType.HTTP],
):
    def get_deployment(self, benchmark_name):
        deployment_name = "aws"
        assert cloud_config
        deployment_client = self.client.get_deployment(
            cloud_config,
            logging_filename=f"regression_{deployment_name}_{benchmark_name}.log",
        )
        deployment_client.initialize()
        return deployment_client


class AzureTestSequence(
    unittest.TestCase,
    metaclass=TestSequenceMeta,
    deployment_name="azure",
    triggers=[Trigger.TriggerType.HTTP],
):
    def get_deployment(self, benchmark_name):
        deployment_name = "azure"
        assert cloud_config
        with AzureTestSequence.lock:
            if not AzureTestSequence.cfg:
                AzureTestSequence.cfg = self.client.get_deployment_config(
                    cloud_config,
                    logging_filename=f"regression_{deployment_name}_{benchmark_name}.log",
                )
            deployment_client = self.client.get_deployment(
                cloud_config,
                logging_filename=f"regression_{deployment_name}_{benchmark_name}.log",
                deployment_config=AzureTestSequence.cfg,
            )
            deployment_client.initialize()
            deployment_client.allocate_shared_resource()
            return deployment_client


class GCPTestSequence(
    unittest.TestCase,
    metaclass=TestSequenceMeta,
    deployment_name="gcp",
    triggers=[Trigger.TriggerType.HTTP],
):
    def get_deployment(self, benchmark_name):
        deployment_name = "gcp"
        assert cloud_config
        deployment_client = self.client.get_deployment(
            cloud_config,
            logging_filename=f"regression_{deployment_name}_{benchmark_name}.log",
        )
        deployment_client.initialize()
        return deployment_client


# https://stackoverflow.com/questions/22484805/a-simple-working-example-for-testtools-concurrentstreamtestsuite
class TracingStreamResult(testtools.StreamResult):
    all_correct: bool
    output: Dict[str, bytes] = {}

    def __init__(self):
        self.all_correct = True
        self.success = set()
        self.failures = set()

    # no way to directly access test instance from here
    def status(self, *args, **kwargs):
        self.all_correct = self.all_correct and (kwargs["test_status"] in ["inprogress", "success"])
        test_name = kwargs["test_id"].split("_")[-1]
        if not kwargs["test_status"]:
            test_id = kwargs["test_id"]
            if test_id not in self.output:
                self.output[test_id] = b""
            self.output[test_id] += kwargs["file_bytes"]
        elif kwargs["test_status"] == "fail":
            print("\n-------------\n")
            print("{0[test_id]}: {0[test_status]}".format(kwargs))
            print("{0[test_id]}: {1}".format(kwargs, self.output[kwargs["test_id"]].decode()))
            print("\n-------------\n")
            self.failures.add(test_name)
        elif kwargs["test_status"] == "success":
            self.success.add(test_name)


def regression_suite(
    sebs_client: "SeBS",
    experiment_config: dict,
    providers: Set[str],
    deployment_config: dict,
    benchmark_name: Optional[str] = None,
):
    suite = unittest.TestSuite()
    global cloud_config
    cloud_config = deployment_config
    if "aws" in providers:
        assert "aws" in cloud_config
        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(AWSTestSequence))
    if "azure" in providers:
        assert "azure" in cloud_config
        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(AzureTestSequence))
    if "gcp" in providers:
        assert "gcp" in cloud_config
        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(GCPTestSequence))
    tests = []
    # mypy is confused here
    for case in suite:
        for test in case:  # type: ignore
            # skip
            test_name = cast(unittest.TestCase, test)._testMethodName
            if not benchmark_name or (benchmark_name and benchmark_name in test_name):
                test.client = sebs_client  # type: ignore
                test.experiment_config = experiment_config  # type: ignore
                tests.append(test)
                print(f"Select test {test_name}")
            else:
                print(f"Skip test {test_name}")
    concurrent_suite = testtools.ConcurrentStreamTestSuite(lambda: ((test, None) for test in tests))
    result = TracingStreamResult()
    result.startTestRun()
    concurrent_suite.run(result)
    result.stopTestRun()
    print(f"Succesfully executed {len(result.success)} out of {len(tests)} functions")
    for suc in result.success:
        print(f"- {suc}")
    if len(result.failures):
        print(f"Failures when executing {len(result.failures)} out of {len(tests)} functions")
        for failure in result.failures:
            print(f"- {failure}")
    return not result.all_correct
