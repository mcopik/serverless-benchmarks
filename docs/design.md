
# Design

In this document, we present the overview of repository structure, explanation of the interfaces implemented,
and the external dependencies of SeBS.

## Directory structure


`sebs.py` - the CLI for SeBS (see next section for details).

### Benchmarks

`benchmarks` - the directory contains the code of each function, the list of its dependencies, and
installation intructions.

`benchmarks/wrappers` - contains the lightweight shims implementing cloud and storage interfaces
that are deployed with each function. These help us to maintain a single implementation
of a function and provide cloud compatibility with those wrappers.

`benchmark-data` - a submodule for the repository with input data for each function.

### Management

`config` - JSON configuration files for SeBS, and examples of user configuration files
provided to the `sebs.py` with flag `--config`.

`.black.toml, .mypy.ini, .flake8.cfg` - configuration files for PEP8 linting and verification
of static types.

`install.py` - install SeBS with all dependencies (see README for details).

### SeBS Library

`sebs/benchmark.py` - the main class encapsulating a benchmark with its language and resource
configuration (class `BenchmarkConfig`).

`sebs/cache.py` - implements the local cache used to store functions and cloud resources,
provides methods for reading and modifying cache contents.

`sebs/config.py` - implements the common configuration parameters.

`sebs/regression.py` - implements the regression test suite - deploy and invoke all functions
on a given platform, in parallel.

`sebs/sebs.py` - provides `SeBS` class, entrypoint for all functionalities - benchmarks, experiments, platforms,
configuration.

`sebs/statistics.py` - implements common statistics routines.

`sebs/utils.py` - implements serialization and logging configuration used by SeBS.

`sebs/faas/` - the abstract interface for all FaaS platforms, see [below](#faas-interface) for details.

`sebs/experiments/` - implements the SeBS experiments.

`sebs/{aws,azure,gcp}/` - implementation of the FaaS interface for each platform.

`sebs/local/` - implements the local invocations of functions with Docker containers
and `minio` storage.

### Created Directories

`python-virtualenv` - the default directory with Python's `venv` instance.
We use it to install locally all SeBS dependencies.

`cache` - the default cache directory used to store locally the information on created
cloud resources.

`regression-cache` - the cache directory for regression tests.

`regression-output` - results and log files of regression tests.

### Other

`tools` scripts used to automatize additional functionalities, such as cloud credentials creation
or Docker image rebuild.

`third-party/pypapi/` - a submodule for [our fork of pypapi](https://github.com/mcopik/pypapi),
used for microarchitectural analysis of local invocations.

`scripts` - legacy scripts for low-level analysis of functions.

## CLI Interface

`sebs.py benchmark invoke` - the workflow begins by creating an instance of `sebs.faas.System`
for the selected platform. Then, an instance of `sebs.Benchmark` is created, and both objects
are used to create or update function code package and upload or update input data in the cloud
storage with the help of `sebs.faas.PersistentStorage` implementation.
In the end, an object of `sebs.faas.benchmark.Function` is created with exposes a list of triggers
encapsulated in `sebs.faas.benchmark.Trigger`. The function is invoked via a selected trigger,
and the output includes a JSON file with invocation ID and results.

`sebs.py benchmark process` - the JSON result from benchmark invocation is read, deserialized,
and the cloud instance is queried for performance metrics related to these invocations.
Afterward, the updated JSON is written to the output directory.

`sebs.py benchmark regression` - this workflow uses the `regression_suite` function from
`sebs/regresion.py` to deploy all benchmarks to the selected cloud platform.
The function reports all errors encountered during deployment and invocation.

`sebs.py experiment invoke` - an instance of `sebs.experiments.Experiment` is created,
and the `run` function implementing experiment logic is executed. The configuration of experiment
is passed by the user in the config JSON.

`sebs.py experiment process` - similarly to the benchmark processing, the cloud metrics are queried
for all invocations in the experiment, and the results are stored as dataframes in .csv files.

## FaaS Interface

`sebs/faas/system.py` - the `System` class defines the interface
that must be implemented for each FaaS platform: initialization (such as starting a Docker container
with cloud CLI management tool); creating storage instance; packaging benchmark source code to conform
to cloud provider standards; creating, loading, and updating a serverless function; enforcing
cold start of each function; modifying function name to limitations enforced by the cloud provider;
and querying cloud metrics.

`sebs/faas/storage.py` - the `PersistentStorage` class defines the interface used to encapsulate
provider-specific APIs for their own storage types (AWS S3, Azure Blob Storage, GC Storage):
creating storage buckets; downloading and uploading files; listing and cleaning buckets;
and exposing `uploader` function used by benchmarks to upload input files.

`sebs/faas/config.py` - provides abstract interfaces for cloud configuration - `Credentials` and `Resources`.

`sebs/faas/function.py` - provides the interface for `Function` and `Trigger`.
Each `Trigger` implementation must implement two basic functionalities: `sync_invoke` and `async_invoke`.
The abstract class contains a generic implementation of HTTP invocation with the help of `pycurl`.
In addition, the module contains an implementation of `ExecutionResult` class used to represent
each invocation of a serverless function.

## Docker Images

SeBS uses three types of Docker images:
* `build` - these are use to install dependencies of each function before deploying it.
The image is supposed to represent an environment as close to the execution sandbox.
* `run` - languase-based Docker images for local function invocations.
* `manage` - currently we use a single management image - `manage.azure` running the Azure CLI.

The `docker` directory contains all necessary Dockerfiles, and the script
`tools/build_docker_images.py` conducts the rebuild of all images.

## Local Execution

We build a fleet of Docker images that run a simple HTTP server that accept invocations of
Python and Node.js functions.
In addition to a server with a language worker, they can contain our fork of `pypapi`, the Python version
of PAPI library for hardware counters. These can be used for low-overhead, detailed profiling
of functions.

The `sebs/local/` directory implements the FaaS interface for a local deployment,
and implements the `minio` storage as a replacement for cloud storage.

