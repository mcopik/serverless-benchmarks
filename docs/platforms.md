
SeBS supports three commercial serverless platforms: AWS Lambda, Azure Functions, and Google Cloud Functions.
Furthermore, we support the open source FaaS system OpenWhisk.

The file `config/example.json` contains all parameters that users can change
to customize the deployment.
Some of these parameters, such as cloud credentials or storage instance address,
are required.
In the following subsections, we discuss the mandatory and optional customization
points for each platform.

> [!WARNING]
> On many platforms, credentials can be provided as environment variables or through the SeBS configuration. SeBS will not store your credentials in the cache. When saving results, SeBS stores user benchmark and experiment configuration for documentation and reproducibility, except for credentials that are erased. If you provide the credentials through JSON input configuration, do not commit nor publish these files anywhere.

Supported platforms
* [Amazon Web Services (AWS) Lambda](#aws-lambda)
* [Microsoft Azure Functions](#azure-functions)
* [Google Cloud (GCP) Functions](#google-cloud-functions)
* [OpenWhisk](#openwhisk)

### Cloud Account Identifiers

SeBS ensures that all locally cached cloud resources are valid by storing a unique identifier associated with each cloud account. Furthermore, we store this identifier in experiment results to easily match results with the cloud account or subscription that was used to obtain them. We use non-sensitive identifiers such as account IDs on AWS, subscription IDs on Azure, and Google Cloud project IDs.

If you have JSON result files, such as `experiment.json` from a benchmark run or '<experiment>/*.json' from an experiment, you can remove all identifying information by removing the JSON object `.config.deployment.credentials`. This can be achieved easily with the CLI tool `jq`:

```
jq 'del(.config.deployment.credentials)' <file.json> | sponge <file.json>
```

## AWS Lambda

AWS provides one year of free services, including a significant amount of computing time in AWS Lambda.
To work with AWS, you need to provide access and secret keys to a role with permissions
sufficient to manage functions and S3 resources.
Additionally, the account must have `AmazonAPIGatewayAdministrator` permission to set up
automatically AWS HTTP trigger.
You can provide a [role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)
with permissions to access AWS Lambda and S3; otherwise, one will be created automatically.
To use a user-defined lambda role, set the name in config JSON - see an example in `config/example.json`.

You can pass the credentials either using the default AWS-specific environment variables:

```
export AWS_ACCESS_KEY_ID=XXXX
export AWS_SECRET_ACCESS_KEY=XXXX
```

or in the JSON input configuration:

```json
"deployment": {
  "name": "aws",
  "aws": {
    "region": "us-east-1",
    "lambda-role": "",
    "credentials": {
      "access_key": "YOUR AWS ACCESS KEY",
      "secret_key": "YOUR AWS SECRET KEY"
    }
  }
}
```

## Azure Functions

Azure provides a free tier for 12 months.
You need to create an account and add a [service principal](https://docs.microsoft.com/en-us/azure/active-directory/develop/howto-create-service-principal-portal)
to enable non-interactive login through CLI.
Since this process has [an easy, one-step CLI solution](https://docs.microsoft.com/en-us/cli/azure/ad/sp?view=azure-cli-latest#az-ad-sp-create-for-rbac),
we added a small tool **tools/create_azure_credentials** that uses the interactive web-browser
authentication to login into Azure CLI and create a service principal.

```console
Please provide the intended principal name
XXXXX
Please follow the login instructions to generate credentials...
To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code YYYYYYY to authenticate.

Login succesfull with user {'name': 'ZZZZZZ', 'type': 'user'}
Created service principal http://XXXXX

AZURE_SECRET_APPLICATION_ID = XXXXXXXXXXXXXXXX
AZURE_SECRET_TENANT = XXXXXXXXXXXX
AZURE_SECRET_PASSWORD = XXXXXXXXXXXXX
```

**Save these credentials - the password is non-retrievable! Provide them to SeBS and we will create additional resources (storage account, resource group) to deploy functions. We will create a storage account and the resource group and handle access keys.

You can pass the credentials either using the environment variables:

```
export AZURE_SECRET_APPLICATION_ID = XXXXXXXXXXXXXXXX
export AZURE_SECRET_TENANT = XXXXXXXXXXXX
export AZURE_SECRET_PASSWORD = XXXXXXXXXXXXX
```

or in the JSON input configuration:

```json
"deployment": {
  "name": "azure",
  "azure": {
    "region": "westeurope"
    "credentials": {
      "appID": "YOUR SECRET APPLICATION ID",
      "tenant": "YOUR SECRET TENANT",
      "password": "YOUR SECRET PASSWORD"
    }
  }
}
```

> [!WARNING]
> The tool assumes there is only one subscription active on the account. If you want to bind the newly created service principal to a specific subscription, or the created credentials do not work with SeBS and you see errors such as "No subscriptions found for X", then you must specify a subscription when creating the service principal. Check your subscription ID on in the Azure portal, and use the CLI option `tools/create_azure_credentials.py --subscription <SUBSCRIPTION_ID>`.

> [!WARNING]
> When you log in for the first time on a device, Microsoft might require authenticating your login with Multi-Factor Authentication (MFA). In this case, we will return an error such as: "The following tenants require Multi-Factor Authentication (MFA). Use 'az login --tenant TENANT_ID' to explicitly login to a tenant.". Then, you can pass the tenant ID by using the `--tenant <tenant-id>` flag.

### Resources

* By default, all functions are allocated in the single resource group.
* Each function has a separate storage account allocated, following [Azure guidelines](https://docs.microsoft.com/en-us/azure/azure-functions/functions-best-practices#scalability-best-practices).
* All benchmark data is stored in the same storage account.

## Google Cloud Functions

The Google Cloud Free Tier gives free resources. It has two parts:

- A 12-month free trial with $300 credit to use with any Google Cloud services.
- Always Free, which provides limited access to many common Google Cloud resources, free of charge.

You need to create an account and add [service account](https://cloud.google.com/iam/docs/service-accounts) to permit operating on storage and functions. From the cloud problem, download the cloud credentials saved as a JSON file.
You should have at least write access to **Cloud Functions** (`Cloud Functions Admin`) and **Logging** Furthermore, SeBS needs the permissions to create Firestore databases through
Google Cloud CLI tool; the `Firestore Service Agent` role allows for that.

You can pass the credentials either using the default GCP-specific environment variable:

```
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/project-credentials.json
```

using the SeBS environment variable:

```
export GCP_SECRET_APPLICATION_CREDENTIALS=/path/to/project-credentials.json
```

or in the JSON input configuration:

```json
"deployment": {
  "name": "gcp",
  "gcp": {
    "region": "europe-west1",
    "credentials": "/path/to/project-credentials.json"
  }
}
```

## OpenWhisk

SeBS expects users to deploy and configure an OpenWhisk instance.
Below, you will find example of instruction for deploying OpenWhisk instance.
The configuration parameters of OpenWhisk for SeBS can be found
in `config/example.json` under the key `['deployment']['openwhisk']`.
In the subsections below, we discuss the meaning and use of each parameter.
To correctly deploy SeBS functions to OpenWhisk, following the
subsections on *Toolchain* and *Docker* configuration is particularly important.

> [!WARNING]
> Some benchmarks might require larger memory allocations, e.g., 2048 MB. Not all OpenWhisk deployments support this out-of-the-box.
> The deployment section below shows an example of changing the default function memory limit from 512 MB to a higher value.

### Deployment

In `tools/openwhisk_preparation.py`, we include scripts that help install
[kind (Kubernetes in Docker)](https://kind.sigs.k8s.io/) and deploy
OpenWhisk on a `kind` cluster. Alternatively, you can deploy to an existing
cluster by [using offical deployment instructions](https://github.com/apache/openwhisk-deploy-kube/blob/master/docs/k8s-kind.md):

```shell
./deploy/kind/start-kind.sh
helm install owdev ./helm/openwhisk -n openwhisk --create-namespace -f deploy/kind/mycluster.yaml
kubectl get pods -n openwhisk --watch
```

To change the maximum memory allocation per function, edit the `max` value under `memory` in file `helm/openwhisk/values.yaml`.
To run all benchmarks, we recommend of at least "2048m".

### Toolchain

We use OpenWhisk's CLI tool [wsk](https://github.com/apache/openwhisk-cli)
to manage the deployment of functions to OpenWhisk.
Please install `wsk`and configure it to point to your OpenWhisk installation.
By default, SeBS assumes that `wsk` is available in the `PATH`.
To override this, set the configuration option `wskExec` to the location
of your `wsk` executable.
If you are using a local deployment of OpenWhisk with a self-signed
certificate, you can skip certificate validation with the `wsk` flag `--insecure`.
To enable this option, set `wskBypassSecurity` to `true`.
At the moment, all functions are deployed as [*web actions*](https://github.com/apache/openwhisk/blob/master/docs/webactions.md)
that do not require credentials to invoke functions.

Furthermore, SeBS can be configured to remove the `kind`
cluster after finishing experiments automatically.
The boolean option `removeCluster` helps to automate the experiments
that should be conducted on fresh instances of the system.

### Docker

In FaaS platforms, the function's code can usually be deployed as a code package
or a Docker image with all dependencies preinstalled.
However, OpenWhisk has a very low code package size limit of only 48 megabytes.
So, to circumvent this limit, we deploy functions using pre-built Docker images.

**Important**: OpenWhisk requires that all Docker images are available
in the registry, even if they have been cached on a system serving OpenWhisk
functions.
Function invocations will fail when the image is not available after a
timeout with an error message that does not directly indicate image availability issues.
Therefore, all SeBS benchmark functions are available on the Docker Hub.

When adding new functions and extending existing functions with new languages
and new language versions, Docker images must be placed in the registry.
However, pushing the image to the default `spcleth/serverless-benchmarks`
repository on Docker Hub requires permissions.
To use a different Docker Hub repository, change the key
`['general']['docker_repository']` in `config/systems.json`.


Alternatively, OpenWhisk users can configure the FaaS platform to use a custom and
private Docker registry and push new images there.
A local Docker registry can speed up development when debugging a new function.
SeBS can use alternative Docker registry - see `dockerRegistry` settings
in the example to configure registry endpoint and credentials.
When the `registry` URL is not provided, SeBS will use Docker Hub.
When `username` and `password` are provided, SeBS will log in to the repository
and push new images before invoking functions.
See the documentation on the
[Docker registry](https://github.com/apache/openwhisk-deploy-kube/blob/master/docs/private-docker-registry.md)
and [OpenWhisk configuration](https://github.com/apache/openwhisk-deploy-kube/blob/master/docs/private-docker-registry.md)
for details.

**Warning**: this feature is experimental and has not been tested extensively.
At the moment, it cannot be used on a `kind` cluster due to issues with
Docker authorization on invoker nodes. [See the OpenWhisk issue for details](https://github.com/apache/openwhisk-deploy-kube/issues/721).

### Code Deployment

SeBS builds and deploys a new code package when constructing the local cache,
when the function's contents have changed, and when the user requests a forced rebuild.
In OpenWhisk, this setup is changed - SeBS will first attempt to verify 
if the image exists already in the registry and skip building the Docker
image when possible.
Then, SeBS can deploy seamlessly to OpenWhisk using default images
available on Docker Hub.
Furthermore, checking for image existence in the registry helps
avoid failing invocations in OpenWhisk.
For performance reasons, this check is performed only once when 
initializing the local cache for the first time.

When the function code is updated,
SeBS will build the image and push it to the registry.
Currently, the only available option of checking image existence in
the registry is pulling the image.
However, Docker's [experimental `manifest` feature](https://docs.docker.com/engine/reference/commandline/manifest/)
allows checking image status without downloading its contents, saving bandwidth and time.
To use that feature in SeBS, set the `experimentalManifest` flag to true.

### Storage 

To provide persistent object storage in OpenWhisk, users must first deploy an instance
of [`Minio`](https://github.com/minio/minio) storage.
The storage instance is deployed as a Docker container, and it can be retained
across many experiments.
OpenWhisk functions must be able to reach the storage instance.
Even on a local machine, it's necessary to configure the network address, as OpenWhisk functions
are running isolated from the host network and won't be able to reach other containers running on the Docker bridge.

Use the following command to deploy the storage instance locally and map the host public port 9011 to Minio instance.

```bash
./sebs.py storage start minio --port 9011 --output-json out_storage.json
```

The output will look similar to the one below.
As we can see, the storage container is running on the default Docker bridge network with address `172.17.0.2` and uses port `9000`.
From the host network, port `9011` is mapped to the container's port `9000` to allow external parties - such as OpenWhisk functions - to reach the storage.

```
{
  "address": "172.17.0.2:9000",
  "mapped_port": 9011,
  "access_key": "XXX",
  "secret_key": "XXX",
  "instance_id": "XXX",
  "input_buckets": [],
  "output_buckets": [],
  "type": "minio"
}
```

The storage configuration found in `out_storage.json` needs to be provided to
SeBS via the SeBS configuration, however the address in `out_storage.json` is likely incorrect.  By
default, it is a address in the local bridge network not accessible to most of
the Kubernetes cluster. It should be replaced with an external address of the
machine and the mapped port. You can typically find an externally accessible address via `ip addr`.

For example, for an external address `10.10.1.15` (a LAN-local address on CloudLab) and mapped port `9011`, set the SeBS configuration as follows:

```
jq --argfile file1 out_storage.json '.deployment.openwhisk.storage = $file1 | .deployment.openwhisk.storage.address = "10.10.1.15:9011"' config/example.json > config/openwhisk.json
```

You can validate this is the correct address by use `curl` to access the Minio instance from another machine or container:

```
$ curl -i 10.10.1.15:9011/minio/health/live
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Length: 0
Content-Security-Policy: block-all-mixed-content
Server: MinIO
Strict-Transport-Security: max-age=31536000; includeSubDomains
Vary: Origin
X-Amz-Request-Id: 16F3D9B9FDFFA340
X-Content-Type-Options: nosniff
X-Xss-Protection: 1; mode=block
Date: Mon, 30 May 2022 10:01:21 GMT
```

The `shutdownStorage` switch controls the behavior of SeBS.
When set to true, SeBS will remove the Minio instance after finishing all 
work.
Otherwise, the container will be retained, and future experiments with SeBS
will automatically detect an existing Minio instance.
Reusing the Minio instance helps run experiments faster and smoothly since
SeBS does not have to re-upload function's data on each experiment.

