import logging
import os
import subprocess
import time
import yaml


# Common utils

def run_check_process(cmd: str, **kwargs) -> None:
    env = os.environ.copy()
    env = {**env, **kwargs}

    subprocess.run(
        cmd.split(),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


# helm utils

def install_helm() -> None:
    try:
        logging.info('Installing helm...')
        helm_package = subprocess.run(
            "curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3".split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            "sh -".split(),
            input=helm_package.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        logging.info('Helm has been installed')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot install helm, reason: {}'.format(e))
        exit(1)


def check_helm_installation() -> None:
    try:
        logging.info("Checking helm installation...")
        run_check_process('helm version')
        logging.info("helm is installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error('helm is not installed, attempting to install...')
        install_helm()


# kubectl utils

def install_kubectl(kubectl_version: str = "v1.18.0") -> None:
    try:
        logging.info('Installing kubectl...')
        home_path = os.environ['HOME']
        kubectl_path = '{}/.local/bin/kubectl'.format(home_path)
        run_check_process("curl -L -o {} "
                          "https://storage.googleapis.com/kubernetes-release/release/{}/bin"
                          "/linux/amd64/kubectl".format(kubectl_path, kubectl_version))
        run_check_process("chmod +x {}".format(kubectl_path))
        logging.info('Kubectl has been installed')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot install kubectl, reason: {}'.format(e))
        exit(1)


def check_kubectl_installation() -> None:
    try:
        logging.info("Checking kubectl installation...")
        run_check_process('kubectl version --client=true')
        logging.info("kubectl is installed")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Kubectl is not installed, attempting to install...')
        install_kubectl()


# kind utils

def install_kind(kind_version: str = "v0.8.1") -> None:
    try:
        logging.info('Installing kind...')
        env = os.environ.copy()
        env['GO111MODULE'] = "on"
        subprocess.run(
            "go get sigs.k8s.io/kind@{}".format(kind_version).split(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        logging.info('Kind has been installed')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot install kind, reason: {}'.format(e))
        exit(1)


def check_kind_installation() -> None:
    try:
        logging.info("Checking go installation...")
        run_check_process('go version')
        logging.info("go is installed")
        try:
            logging.info("Checking kind installation...")
            run_check_process('kind version')
            logging.info('kind is installed')
        except (subprocess.CalledProcessError, FileNotFoundError):
            logging.warning('Cannot find kind, proceeding with installation')
            install_kind()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot find go, reason: {}'.format(e))
        exit(1)


def label_nodes() -> None:
    def label_node(node: str, role: str) -> None:
        run_check_process("kubectl label node {} openwhisk-role={}".format(node, role))

    try:
        logging.info('Labelling nodes')
        label_node('kind-worker', 'core')
        label_node('kind-worker2', 'invoker')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot label nodes, reason: {}'.format(e))
        exit(1)


def get_worker_ip(worker_node_name: str = "kind-worker") -> str:
    try:
        logging.info("Retrieving worker IP...")
        internal_ip_proc = subprocess.run(
            ["kubectl", "get", "node", worker_node_name, "-o",
             "go-template='{{ (index .status.addresses 0).address }}'"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return internal_ip_proc.stdout.decode("utf-8").replace("'", "")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot retrieve node IP, reason: {}".format(e))
        exit(1)


def create_kind_cluster() -> None:
    try:
        run_check_process("kind create cluster --config openwhisk/kind-cluster.yaml")
        while True:
            nodes = subprocess.run(
                "kubectl get nodes".split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            node_grep = subprocess.run(
                "grep kind".split(),
                input=nodes.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            awk = subprocess.run(
                ["awk", r'{print $2}'],
                check=True,
                input=node_grep.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            node_statuses = awk.stdout.decode('utf-8').split()
            if all(node_status == 'Ready' for node_status in node_statuses):
                break
            time.sleep(1)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot create kind cluster. reason: {}".format(e))
        exit(1)


def check_kind_cluster() -> None:
    try:
        kind_clusters_process = subprocess.run(
            "kind get clusters".split(),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        kind_clusters = set(kind_clusters_process.stdout.decode('utf-8').split())
        if "kind" not in kind_clusters:
            logging.info("Creating kind cluster...")
            create_kind_cluster()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot check kind cluster, reason: {}".format(e))


def delete_cluster():
    try:
        logging.info('Deleting KinD cluster...')
        run_check_process('kind delete cluster')
        logging.info('KinD cluster deleted...')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot delete cluster, reason: {}".format(e))


# openwhisk deployment utils

def check_wsk_installation() -> None:
    try:
        logging.info("Checking wsk installation...")
        run_check_process('wsk')
        logging.info("wsk is installed")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f'Cannot find wsk, reason: {e}')
        exit(1)


def prepare_wsk() -> None:
    try:
        ip = get_worker_ip()
        auth = "23bc46b1-71f6-4ed5-8c54-816aa4f8c502:123zO3xZCLrMN6v2BKK1dXYFpXlPkccOFqm12CdAsMgRU4VrNZ9lyGVCGuMDGIwP"
        subprocess.run(
            f"wsk property set --apihost {ip} --auth {auth}",
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Cannot find wsk on system, reason: {e}")
        exit(1)


def expose_couchdb() -> None:
    try:
        run_check_process("kubectl apply -f openwhisk/couchdb-service.yaml")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot expose Couch DB, reason: {}".format(e))


def clone_openwhisk_chart() -> None:
    try:
        run_check_process("git clone git@github.com:apache/openwhisk-deploy-kube.git /tmp/openwhisk-deploy-kube")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot clone openwhisk chart, reason: {}".format(e))


def prepare_openwhisk_config() -> None:
    worker_ip = get_worker_ip()
    with open('openwhisk/mycluster_template.yaml', 'r') as openwhisk_config_template:
        data = yaml.unsafe_load(openwhisk_config_template)
        data['whisk']['ingress']['apiHostName'] = worker_ip
        data['whisk']['ingress']['apiHostPort'] = 31001
        data['nginx']['httpsNodePort'] = 31001
    if not os.path.exists('/tmp/openwhisk-deploy-kube/mycluster.yaml'):
        with open('/tmp/openwhisk-deploy-kube/mycluster.yaml', 'a+') as openwhisk_config:
            openwhisk_config.write(yaml.dump(data, default_flow_style=False))


def deploy_openwhisk_on_k8s(namespace: str = "openwhisk") -> None:
    try:
        run_check_process(
            "helm install owdev /tmp/openwhisk-deploy-kube/helm/openwhisk -n {} --create-namespace -f "
            "/tmp/openwhisk-deploy-kube/mycluster.yaml".format(namespace)
        )
        while True:
            pods = subprocess.run(
                "kubectl get pods -n {}".format(namespace).split(),
                stderr=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
            )
            check_result = subprocess.run(
                "grep install-packages".split(),
                input=pods.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            install_packages_status = check_result.stdout.decode('utf-8').split()[2]
            if install_packages_status == 'Completed':
                break

            time.sleep(1)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error("Cannot install openwhisk, reason: {}".format(e))
        exit(1)


def get_openwhisk_url() -> str:
    ip = get_worker_ip()
    return '{}:{}'.format(ip, 31001)


def get_couchdb_url() -> str:
    ip = get_worker_ip()
    return '{}:{}'.format(ip, 31201)


def install_wsk() -> None:
    try:
        logging.info('Installing wsk...')
        home_path = os.environ['HOME']
        wsk_path = '{}/.local/bin/wsk'.format(home_path)
        subprocess.run("go get github.com/apache/openwhisk-cli".split())
        run_check_process("go get -u github.com/jteeuwen/go-bindata/...")
        instalation_dir = "{}/src/github.com/apache/openwhisk-cli".format(os.environ['GOPATH'])

        def custom_subproces(comand):
            subprocess.run(comand.split(),
                           cwd=instalation_dir,
                           check=True)
        custom_subproces("go-bindata -pkg wski18n -o wski18n/i18n_resources.go wski18n/resources")
        custom_subproces("go build -o wsk")
        run_check_process("ln -sf {}/wsk {}".format(instalation_dir, wsk_path))
        run_check_process("chmod +x {}".format(wsk_path))
        logging.info('Wsk has been installed')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error('Cannot install wsk, reason: {}'.format(e))
        exit(1)


def check_wsk_installation() -> None:
    try:
        logging.info("Checking wsk installation...")
        run_check_process("wsk")
        logging.info("Wsk is installed")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.info("Wsk is not installed, proceeding to install...")
        install_wsk()
# mixup


def initiate_all():
    check_kubectl_installation()
    check_wsk_installation()
    check_helm_installation()
    check_kind_installation()
    check_kind_cluster()
    label_nodes()
    clone_openwhisk_chart()
    prepare_openwhisk_config()
    deploy_openwhisk_on_k8s()
    expose_couchdb()
