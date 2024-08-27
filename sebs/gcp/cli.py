import logging
import os

import docker

from sebs.config import SeBSConfig
from sebs.gcp.config import GCPCredentials
from sebs.utils import LoggingBase


class GCloudCLI(LoggingBase):
    @staticmethod
    def typename() -> str:
        return "GCP.CLI"

    def __init__(
        self, credentials: GCPCredentials, system_config: SeBSConfig, docker_client: docker.client
    ):

        super().__init__()

        repo_name = system_config.docker_repository()
        image_name = "manage.gcp"
        try:
            docker_client.images.get(repo_name + ":" + image_name)
        except docker.errors.ImageNotFound:
            try:
                logging.info(
                    "Docker pull of image {repo}:{image}".format(repo=repo_name, image=image_name)
                )
                docker_client.images.pull(repo_name, image_name)
            except docker.errors.APIError:
                raise RuntimeError("Docker pull of image {} failed!".format(image_name))

        volumes = {
            os.path.abspath(credentials.gcp_credentials): {
                "bind": "/credentials.json",
                "mode": "ro",
            }
        }
        self.docker_instance = docker_client.containers.run(
            image=repo_name + ":" + image_name,
            volumes=volumes,
            remove=True,
            stdout=True,
            stderr=True,
            detach=True,
            tty=True,
        )
        self.logging.info(f"Started gcloud CLI container: {self.docker_instance.id}.")
        # while True:
        #    try:
        #        dkg = self.docker_instance.logs(stream=True, follow=True)
        #        next(dkg).decode("utf-8")
        #        break
        #    except StopIteration:
        #        pass

    """
        Execute the given command in Azure CLI.
        Throws an exception on failure (commands are expected to execute succesfully).
    """

    def execute(self, cmd: str):
        exit_code, out = self.docker_instance.exec_run(cmd)
        if exit_code != 0:
            raise RuntimeError(
                "Command {} failed at gcloud CLI docker!\n Output {}".format(
                    cmd, out.decode("utf-8")
                )
            )
        return out

    """
        Run gcloud auth command on Docker instance.

        Important: we cannot run "init" as this always requires authenticating through a browser.
        Instead, we authenticate as a service account.

        Setting cloud project will show a warning about missing permissions
        for Cloud Resource Manager API: I don't know why, we don't seem to need it.

        Because of that, it will ask for verification to continue - which we do by passing "Y".
    """

    def login(self, project_name: str):
        self.execute("gcloud auth login --cred-file=/credentials.json")
        self.execute(f"/bin/bash -c 'gcloud config set project {project_name} <<< Y'")
        self.logging.info("gcloud CLI login succesful")

    """
        Shuts down the Docker instance.
    """

    def shutdown(self):
        self.logging.info("Stopping gcloud CLI manage Docker instance")
        self.docker_instance.stop()
