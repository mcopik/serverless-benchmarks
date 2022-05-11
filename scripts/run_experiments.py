#!/usr/bin/env python3

import argparse
import collections
import copy
import docker
import glob
import json
import logging
import minio
import os
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import urllib, urllib.request
import uuid

from functools import partial
from typing import Tuple

from sebs import Cache, CodePackage
from sebs.experiments.environment import ExperimentEnvironment
from sebs import utils as experiment_utils

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def iterable(val):
    return val if isinstance(val, collections.Iterable) else [val, ]

def run_container(client, language, version, volumes, code_package, home_dir, cpuset):
    return client.containers.run(
            'sebs.run.local.{}.{}'.format(language, version),
            command='/bin/bash',
            volumes = {
                **volumes,
                code_package : {'bind': os.path.join(home_dir, 'code'), 'mode': 'ro'}
            },
            cpuset_cpus=cpuset,
            # required to access perf counters
            # alternative: use custom seccomp profile
            privileged=True,
            user='1000:1000',
            network_mode="bridge",
            remove=True,
            stdout=True, stderr=True,
            detach=True, tty=True
        )

class docker_experiment:
    name = None
    experiment_type = None
    config = None
    instances = 0
    start = lambda *args: None
    cleanup = lambda * args: None
    finish = lambda *args: None
    docker_volumes = {}
    detach = False
    result_path = None
    json_file = None
    language = None

    # if more than one instance of app, then we need to detach from running containers
    def __init__(self, instances, name, experiment_type,
            input_config, option=None, additional_cfg=None):
        self.instances = instances
        self.detach = instances > 1
        self.experiment_type = experiment_type
        self.name = name
        self.language = input_config['benchmark']['language']

        self.json_file = '{}.json'.format(self.name)
        with open(self.json_file, 'w') as f:
            experiment = {
                'name': self.name,
                'type': self.experiment_type,
            }
            if option is not None:
                experiment['experiment_options'] = option
            cfg_copy = copy.deepcopy(input_config)
            cfg_copy['benchmark'].update(experiment)
            if additional_cfg is not None:
                cfg_copy['benchmark'].update(additional_cfg)
            json.dump(cfg_copy, f, indent=2)
            self.config = cfg_copy

    def get_docker_volumes(self, output_dir, home_dir):
        return {
                os.path.join(output_dir, self.json_file):
                {'bind': os.path.join(home_dir, self.json_file), 'mode': 'ro'}
            }

    # result is copied from Docker or created locally by analyzers
    # provide path to analyzer result OR find all csv files copied from Docker
    def get_result_path(self, instance):
        if self.result_path is None:
            path = os.path.join(instance, 'results')
            return [file for file in glob.glob(os.path.join(path, '*.csv'))]
        else:
            return [self.result_path]

class analyzer_experiment(docker_experiment):
    port = None
    proc = None

    def __init__(self, instances, name, experiment_type, input_config, port, option=None):
        additional_cfg = {
            'analyzer': {
                'participants' : instances,
                'analyzer_port': port
            }
        }
        docker_experiment.__init__(self, instances, name, experiment_type,
                input_config, option, additional_cfg)
        self.port = port

    # Start analyzer process on provided port.
    # Results are written to file at `result_path`
    # Output of analyzer goes to `file_output`
    def start(self):
        file_name = '{}.json'.format(self.name)
        os.makedirs(self.name, exist_ok=True)
        os.makedirs(os.path.join(self.name, 'results'), exist_ok=True)
        file_output = open(os.path.join(self.name, 'proc-analyzer.out'), 'w')
        self.result_path = os.path.join(self.name, 'results', '{}.csv'.format(self.name))
        self.proc = subprocess.Popen(
                [os.path.join(SCRIPT_DIR, 'proc_analyzer.py'), str(self.port),
                    self.result_path, self.experiment_type, str(self.instances)],
                stdout=file_output,
                stderr=subprocess.STDOUT
            )
        if self.proc.returncode is not None:
            logging.error('Memory analyzer finished unexpectedly')

    # Write down results of analyzer and kill the process.
    def cleanup(self):
        try:
            # curl returns zero event if request errored on server side
            response = urllib.request.urlopen('http://0.0.0.0:{}/dump'.format(self.port), {})
            code = response.getcode()
            if code != 200:
                logging.error('Proc analyzer failed when writing values!')
                logging.error(response.read())
                raise RuntimeError()
        except urllib.error.HTTPError as err:
            logging.error('Proc analyzer failed when writing values!')
            raise(err)
        self.proc.kill()

    # For launches with multiple instances, we need a way to tell if N-th
    # instance has been processed and we can launch a new one.
    # Thus we wait until server analyzer returns message indicating that all
    # current processing is finished.
    def finish(self, count):
        # verify if we can launch more instances (analyzer processed all active instances)
        if self.instances > 1:
            values = 0
            while values != count:
                response = urllib.request.urlopen('http://0.0.0.0:{}/processed_apps'.format(self.port), {})
                data = response.read()
                values = json.loads(data)['apps']

def run_experiment_time(input_config):
    experiments = []
    for option in ['warm', 'cold']:
        experiments.append(docker_experiment(
                instances=1,
                name='time_{}'.format(option),
                experiment_type='time',
                input_config=input_config,
                option=option
            ))
    return experiments

def run_experiment_papi_ipc(input_config):
    experiments = []
    experiments.append(docker_experiment(
        instances=1,
        name='inscount_papi',
        experiment_type='papi',
        input_config=input_config,
        additional_cfg={
            'papi': {
                'events': ['PAPI_TOT_INS', 'PAPI_LST_INS', 'PAPI_BR_INS'],#, 'PAPI_BR_MSP'],
                'overflow_instruction_granularity' : 1e6,
                'overflow_buffer_size': 1e6
            }
        }
    ))
    experiments.append(docker_experiment(
        instances=1,
        name='sp_flops_papi',
        experiment_type='papi',
        input_config=input_config,
        additional_cfg={
            'papi': {
                'events': ['PAPI_TOT_INS', 'PAPI_SP_OPS', 'PAPI_VEC_SP'],
                'overflow_instruction_granularity' : 1e6,
                'overflow_buffer_size': 1e6
            }
        }
    ))
    experiments.append(docker_experiment(
        instances=1,
        name='dp_flops_papi',
        experiment_type='papi',
        input_config=input_config,
        additional_cfg={
            'papi': {
                'events': ['PAPI_TOT_INS', 'PAPI_DP_OPS', 'PAPI_VEC_DP'],
                'overflow_instruction_granularity' : 1e6,
                'overflow_buffer_size': 1e6
            }
        }
    ))
    experiments.append(docker_experiment(
        instances=1,
        name='cache_papi',
        experiment_type='papi',
        input_config=input_config,
        additional_cfg={
            'papi': {
                'events': ['PAPI_TOT_INS', 'PAPI_L1_DCM', 'PAPI_L1_ICM', 'PAPI_L2_TCM', 'PAPI_L3_TCM'],
                'overflow_instruction_granularity' : 1e6,
                'overflow_buffer_size': 1e6
            }
        }
    ))
    experiments.append(docker_experiment(
        instances=1,
        name='cycles_papi',
        experiment_type='papi',
        input_config=input_config,
        additional_cfg={
            'papi': {
                'events': ['PAPI_TOT_CYC', 'PAPI_TOT_INS', 'PAPI_STL_ICY', 'PAPI_STL_CCY', 'PAPI_RES_STL'],
                'overflow_instruction_granularity' : 1e6,
                'overflow_buffer_size': 1e6
            }
        }
    ))
    return experiments

def run_experiment_mem(input_config):
    experiments = []
    experiments.append(analyzer_experiment(
        instances=1,
        name='mem-single',
        experiment_type='memory',
        input_config=input_config,
        port=8081
    ))
    experiments.append(analyzer_experiment(
        instances=5,
        name='mem-multiple',
        experiment_type='memory',
        input_config=input_config,
        port=8081
    ))
    return experiments

def run_experiment_disk_io(input_config):
    experiments = []
    experiments.append(analyzer_experiment(
        instances=1,
        name='disk-io',
        experiment_type='disk-io',
        input_config=input_config,
        port=8081
    ))
    return experiments

experiments = {
        'time' : run_experiment_time,
        'papi' : run_experiment_papi_ipc,
        'memory' : run_experiment_mem,
        'disk-io' : run_experiment_disk_io
        }
experiments['all'] = list(experiments.values())
docker_client = docker.from_env()
verbose = False

parser = argparse.ArgumentParser(description='Run local app experiments.')
parser.add_argument('benchmark', type=str, help='Benchmark name')
parser.add_argument('output_dir', type=str, help='Output dir')
parser.add_argument('language', choices=['python', 'nodejs', 'cpp'],
                    help='Benchmark language')
parser.add_argument('experiment', choices=['time', 'papi', 'memory', 'disk-io', 'all'],
                    help='Benchmark language')
parser.add_argument('size', choices=['test', 'small', 'large'],
                    help='Benchmark input test size')
parser.add_argument('--repetitions', action='store', default=None, type=int,
                    help='Number of experimental repetitions')
parser.add_argument('--config', action='store',
        default=os.path.join(SCRIPT_DIR, os.pardir, 'config', 'experiments.json'),
        type=str, help='Experiments config file')
parser.add_argument('--cache', action='store', default='cache', type=str,
                    help='Cache directory')
parser.add_argument('--update', action='store_true', default=False,
                    help='Update function code in cache and deployment.')
parser.add_argument('--shutdown-containers', action='store_true',
                    help='Shutdown containers after experiments.')
parser.add_argument('--no-shutdown-containers', dest='shutdown_containers', action='store_false',
                    help='Shutdown containers after experiments.')
parser.set_defaults(shutdown_containers=True)
parser.add_argument('--verbose', action='store', default=False, type=bool,
                    help='Verbose output')

class minio_storage:
    storage_container = None
    input_buckets = []
    output_buckets = []
    access_key = None
    secret_key = None
    port = 9000
    location = 'us-east-1'
    connection = None
    docker_client = None

    def __init__(self, docker_client, benchmark, buckets):
        self.docker_client = docker_client
        if buckets[0] + buckets[1] > 0:
            self.start()
            self.connection = self.get_connection()
            for i in range(0, buckets[0]):
                self.input_buckets.append(
                        self.create_bucket('{}-{}-input'.format(benchmark, i)))
            for i in range(0, buckets[1]):
                self.output_buckets.append(
                        self.create_bucket('{}-{}-output'.format(benchmark, i)))
    def input(self):
        return self.input_buckets

    def output(self):
        return self.output_buckets

    def start(self):
        self.access_key = secrets.token_urlsafe(32)
        self.secret_key = secrets.token_hex(32)
        logging.info('ACCESS_KEY={}'.format(self.access_key))
        logging.info('SECRET_KEY={}'.format(self.secret_key))
        self.storage_container = self.docker_client.containers.run(
            'minio/minio',
            command='server /data',
            ports={str(self.port): self.port},
            environment={
                'MINIO_ACCESS_KEY' : self.access_key,
                'MINIO_SECRET_KEY' : self.secret_key
            },
            remove=True,
            stdout=True, stderr=True,
            detach=True
        )
        # who knows why? otherwise attributes are not loaded
        self.storage_container.reload()
        networks = self.storage_container.attrs['NetworkSettings']['Networks']
        self.url = '{IPAddress}:{Port}'.format(
                IPAddress=networks['bridge']['IPAddress'],
                Port=self.port
        )
        logging.info('Starting minio instance at {}'.format(self.url))

    def stop(self):
        if self.storage_container is not None:
            logging.info('Stopping minio instance at {url}'.format(url=self.url))
            self.storage_container.stop()

    def get_connection(self):
        return minio.Minio(self.url,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=False)

    def config_to_json(self):
        if self.storage_container is not None:
            return {
                    'address': self.url,
                    'secret_key': self.secret_key,
                    'access_key': self.access_key,
                    'input': self.input_buckets,
                    'output': self.output_buckets
                }
        else:
            return {}

    def create_bucket(self, name):
        # minio has limit of bucket name to 16 characters
        bucket_name = '{}-{}'.format(name, str(uuid.uuid4())[0:16])
        try:
            self.connection.make_bucket(bucket_name, location=self.location)
            logging.info('Created bucket {}'.format(bucket_name))
            return bucket_name
        except (minio.error.BucketAlreadyOwnedByYou, minio.error.BucketAlreadyExists, minio.error.ResponseError) as err:
            logging.error('Bucket creation failed!')
            # rethrow
            raise err

    def uploader_func(self, bucket_idx, file, filepath):
        try:
            self.connection.fput_object(self.input_buckets[bucket_idx], file, filepath)
        except minio.error.ResponseError as err:
            logging.error('Upload failed!')
            raise(err)

    def clean(self):
        for bucket in self.output_buckets:
            objects = self.connection.list_objects_v2(bucket)
            objects = [obj.object_name for obj in objects]
            for err in self.connection.remove_objects(bucket, objects):
                logging.error("Deletion Error: {}".format(del_err))

    def download_results(self, result_dir):
        result_dir = os.path.join(result_dir, 'storage_output')
        for bucket in self.output_buckets:
            objects = self.connection.list_objects_v2(bucket)
            objects = [obj.object_name for obj in objects]
            for obj in objects:
                self.connection.fget_object(bucket, obj, os.path.join(result_dir, obj))

class local:

    storage_instance = None
    docker_client = None
    language = None
    cache_client = None
    config = None

    def __init__(self, cache_client, config, docker_client, language):
        self.cache_client = cache_client
        self.config = config
        self.docker_client = docker_client
        self.language = language

    '''
        It would be sufficient to just pack the code and ship it as zip to AWS.
        However, to have a compatible function implementation across providers,
        we create a small module.
        Issue: relative imports in Python when using storage wrapper.
        Azure expects a relative import inside a module.

        Structure:
        function
        - function.py
        - storage.py
        - resources
        handler.py

        dir: directory where code is located
        benchmark: benchmark name
    '''
    def package_code(self, dir :str, benchmark :str):

        CONFIG_FILES = {
            'python': ['handler.py', 'requirements.txt', '.python_packages'],
            'nodejs': ['handler.js', 'package.json', 'node_modules']
        }
        package_config = CONFIG_FILES[self.language]
        function_dir = os.path.join(dir, 'function')
        os.makedirs(function_dir)
        # move all files to 'function' except handler.py
        for file in os.listdir(dir):
            if file not in package_config:
                file = os.path.join(dir, file)
                shutil.move(file, function_dir)
        return dir

    '''
        Create wrapper object for minio storage and fill buckets.
        Starts minio as a Docker instance, using always fresh buckets.

        :param benchmark:
        :param buckets: number of input and output buckets
        :param replace_existing: not used.
        :return: Azure storage instance
    '''
    def get_storage(self, benchmark :str, buckets :Tuple[int, int],
            replace_existing: bool=False):
        self.storage_instance = minio_storage(docker_client, benchmark, buckets)
        return self.storage_instance

    def storage(self):
        return self.storage_instance

    '''
        Shut down minio storage instance.
    '''
    def shutdown(self):
        if self.storage_instance:
            self.storage_instance.stop()

    '''
        Create benchmark package or use an exisiting one.
        a)  if a cached function is present and no update flag is passed,
            then just return function name
        b)  if a cached function is present and update flag is passed,
            then provide path to it
        c)  if no cached function is present, then create code package and
            provide path to it

        :param benchmark:
        :param benchmark_path: Path to benchmark code
        :param config: JSON config for benchmark
        :return: path to code, code size
    '''
    def create_function(self, code_package: CodePackage, experiment_config :dict):

        benchmark = code_package.name

        if code_package.is_cached and code_package.is_cached_valid:
            func_name = code_package.cached_config['name']
            code_location = code_package.code_location
            logging.info('Using cached function {fname} in {loc}'.format(
                fname=func_name,
                loc=code_location
            ))
            return func_name
        # b) cached_instance, create package and update code
        elif code_package.is_cached:

            func_name = benchmark
            code_location = code_package.code_location

            # Build code package
            package = self.package_code(code_location, code_package.name)
            code_size = code_package.recalculate_code_size()
            cached_cfg = code_package.cached_config

            # Copy new code to cache
            cached_cfg['code_size'] = code_size
            cached_cfg['hash'] = code_package.hash
            self.cache_client.update_function('local', benchmark, self.language,
                    package, cached_cfg
            )
            logging.info('Updating cached function {fname} in {loc}'.format(
                fname=func_name,
                loc=code_location
            ))

            return func_name
        # c) no cached instance, create package and upload code
        else:
            func_name = benchmark
            code_location = code_package.code_location

            # Build code package
            package = self.package_code(code_location, code_package.name)
            code_size = code_package.recalculate_code_size()
            logging.info('Creating function {fname} in {loc}'.format(
                fname=func_name,
                loc=code_location
            ))
            self.cache_client.add_benchmark(
                deployment='local',
                benchmark=benchmark,
                language=self.language,
                code_package=package,
                language_config={
                    'name': func_name,
                    'code_size': code_size,
                    'runtime': self.config['experiments']['runtime'],
                    'hash': code_package.hash
                },
                storage_config={}
            )
            return func_name

deployment_client = None

try:
    benchmark_summary = { 'experiments': {} }

    # 0. Input args
    args = parser.parse_args()
    verbose = args.verbose
    experiment_config = json.load(open(args.config, 'r'))
    # CLI takes precendece over config
    experiment_config['experiments']['update_code'] = args.update
    experiment_config['experiments']['deployment'] = 'local'
    experiment_config['experiments']['language'] = args.language
    experiment_config['experiments']['runtime'] = experiment_config['local']['runtime'][args.language]

    systems_config = json.load(open(os.path.join(SCRIPT_DIR, os.pardir, 'config', 'systems.json'), 'r'))
    cache_client = Cache(args.cache)
    deployment_client = local(cache_client, experiment_config, docker_client, args.language)
    deployment = 'local'

    # 1. Create output dir
    output_dir = experiment_utils.create_output(args.output_dir, False, args.verbose)
    logging.info('Created experiment output at {}'.format(output_dir))

    # Verify if the experiment is supported for the language
    supported_experiments = systems_config['local']['experiments'][args.language]
    if args.experiment != 'all':
        selected_experiments = [args.experiment]
    else:
        selected_experiments = list(experiments.keys())
        selected_experiments.remove('all')
    if any(val not in supported_experiments for val in selected_experiments):
        raise RuntimeError('Experiment {} is not supported for language {}!'.format(args.experiment, args.language))

    # 2. Locate benchmark
    #benchmark_path = find_package_code(args.benchmark, 'benchmarks')
    #logging.info('# Located benchmark {} at {}'.format(args.benchmark, benchmark_path))

    # 6. Create experiment config
    benchmark_config = experiment_config['experiments']
    # CLI overrides JSON config
    if args.repetitions:
        benchmark_config['repetitions'] = args.repetitions
    elif 'repetitions' not in benchmark_config:
        benchmark_config['repetitions'] = 1
    benchmark_config['language'] = args.language
    benchmark_config['runtime'] = experiment_config['local']['runtime'][args.language]
    benchmark_config['deployment'] = {
        'name': 'local',
        'config': experiment_config['local']
    }

    package = CodePackage(args.benchmark, experiment_config, output_dir,
            systems_config[deployment], cache_client, docker_client, args.update)
    # 5. Prepare benchmark input
    input_config = experiment_utils.prepare_input(
        client=deployment_client,
        benchmark=args.benchmark,
        size=args.size,
        update_storage=False
    )
    storage_config = deployment_client.storage().config_to_json()
    if storage_config:
        benchmark_config['storage'] = storage_config

    # 4. Prepare environment
    # TurboBoost, disable HT, power cap, decide on which cores to use

    #code_package, code_size = deployment_client.create_function(args.benchmark,
    #        benchmark_path, experiment_config)
    func = deployment_client.create_function(package, experiment_config)
    app_config = {
            'name': args.benchmark,
            'size': package.code_size,
            'hash': package.hash
    }
    input_config = {
        'input' : input_config,
        'app': app_config,
        'benchmark' : benchmark_config,
    }

    # 7. Select experiments
    volumes = {}
    enabled_experiments = []
    for ex_func in iterable(experiments[args.experiment]):
        enabled_experiments.extend( ex_func(input_config) )

    # 8. Start measurement processes
    for experiment in enabled_experiments:

        home_dir = '/home/{}'.format(systems_config['local']['languages'][args.language]['username'])
        containers = [None] * experiment.instances
        os.makedirs(experiment.name, exist_ok=True)
        logging.info('# Experiment: {} begins.'.format(experiment.name))
        experiment.start()

        instance_volumes = []
        for i in range(0, experiment.instances):

            # results directory for container instance
            dest_dir = os.path.join(experiment.name, 'instance_{}'.format(i))
            os.makedirs(dest_dir, exist_ok=True)
            result_volumes = {}
            for result in ['results', 'logs']:
                res_dir = os.path.join(dest_dir, result)
                os.makedirs(res_dir, exist_ok=True)
                result_volumes[os.path.abspath(res_dir)] = {
                        'bind': os.path.join(home_dir, result),
                        'mode': 'rw'
                }
            instance_volumes.append(result_volumes)


            # 7. Start docker instance with code and input
        for i in range(0, experiment.instances):
            containers[i] = run_container(
                docker_client, args.language, benchmark_config['runtime'],
                {
                    **volumes,
                    **instance_volumes[i],
                    **experiment.get_docker_volumes(output_dir, home_dir)
                },
                os.path.join(output_dir, package.code_location),
                home_dir,
                cpuset=str(i)
            )

        for i in range(0, experiment.instances):
            # 8. Run experiments
            exit_code, out = containers[i].exec_run('/bin/bash run.sh {}.json'.format(experiment.name), detach=experiment.detach)
            if not experiment.detach:
                logging.info('# Experiment: {} exit code: {}'.format(experiment.name, exit_code))
                if exit_code == 0:
                    logging.debug('Output: {}'.format(out.decode('utf-8')))
                else:
                    logging.error('# Experiment {} failed! Exit code {}'.format(experiment.name, exit_code))
                    logging.error(out.decode('utf-8'))

        if experiment.detach:
            experiment.finish(experiment.instances)
            logging.info('Experiment: {} containers finished.'.format(experiment.name, i))

        # Summarize experiment
        summary = {}
        summary['config'] = experiment.config
        summary['instances'] = []
        # 9. Copy result data
        for idx, container in enumerate(containers):

            # Gather docker statistics
            dest_dir = os.path.join(experiment.name, 'instance_{}'.format(idx))
            docker_stats = container.stats(stream=False)
            with open(os.path.join(dest_dir, 'docker_stats.json'), 'w') as out_f:
                json.dump(docker_stats, out_f, indent=2)

            # Wait until log file shows up - indicates the end of command
            # Necessary when command is detached
            # TODO: with fix system where containers report finish by themselves
            found = False
            result_path = os.path.join(dest_dir, 'results')
            while True:
                logs = glob.glob(os.path.join(result_path, '*.json'))
                if len(logs):
                    break
                else:
                    time.sleep(1)

            # 11. Find experiment JSONs and include in summary
            jsons = [json_file for json_file in glob.glob(os.path.join(result_path, '*.json'))]
            summary['instances'].append( {'config': jsons, 'results': experiment.get_result_path(dest_dir)} )

            # 10. Kill docker instance
            if args.shutdown_containers:
                container.stop()


        benchmark_summary['experiments'][experiment.name] = summary

        # 11. Cleanup active measurement processes
        experiment.cleanup()
        deployment_client.storage().download_results(experiment.name)
        deployment_client.storage().clean()

    # Summarize
    benchmark_summary['system'] = {}
    uname = os.uname()
    for val in ['nodename', 'sysname', 'release', 'version', 'machine']:
        benchmark_summary['system'][val] = getattr(uname, val)
    json.dump(benchmark_summary, open('experiments.json', 'w'), indent=2)

except Exception as e:
    logging.error(e)
    traceback.print_exc()
    print('# Experiments failed! See {}/out.log for details'.format(output_dir))
finally:
    if deployment_client:
        deployment_client.shutdown()
