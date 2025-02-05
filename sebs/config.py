import json
from typing import Dict, List, Optional

from sebs.utils import project_absolute_path


class SeBSConfig:
    def __init__(self):
        with open(project_absolute_path("config", "systems.json"), "r") as cfg:
            self._system_config = json.load(cfg)
        self._image_tag_prefix = ""

    @property
    def image_tag_prefix(self) -> str:
        return self._image_tag_prefix

    @image_tag_prefix.setter
    def image_tag_prefix(self, tag: str):
        self._image_tag_prefix = tag

    def docker_repository(self) -> str:
        return self._system_config["general"]["docker_repository"]

    def deployment_packages(self, deployment_name: str, language_name: str) -> Dict[str, str]:
        return self._system_config[deployment_name]["languages"][language_name]["deployment"][
            "packages"
        ]

    def deployment_files(self, deployment_name: str, language_name: str) -> List[str]:
        return self._system_config[deployment_name]["languages"][language_name]["deployment"][
            "files"
        ]

    def docker_image_types(self, deployment_name: str, language_name: str) -> List[str]:
        return self._system_config[deployment_name]["languages"][language_name]["images"]

    def supported_language_versions(
        self, deployment_name: str, language_name: str, architecture: str
    ) -> List[str]:
        languages = self._system_config.get(deployment_name, {}).get("languages", {})
        base_images = languages.get(language_name, {}).get("base_images", {})

        if deployment_name == "local":
            return list(base_images.keys())
        return list(base_images.get(architecture, {}).keys())

    def supported_architecture(self, deployment_name: str) -> List[str]:
        return self._system_config[deployment_name]["architecture"]

    def supported_package_deployment(self, deployment_name: str) -> bool:
        return "package" in self._system_config[deployment_name]["deployments"]

    def supported_container_deployment(self, deployment_name: str) -> bool:
        return "container" in self._system_config[deployment_name]["deployments"]

    def benchmark_base_images(
        self, deployment_name: str, language_name: str, architecture: str
    ) -> Dict[str, str]:
        return self._system_config[deployment_name]["languages"][language_name]["base_images"][
            architecture
        ]

    def benchmark_image_name(
        self,
        system: str,
        benchmark: str,
        language_name: str,
        language_version: str,
        architecture: str,
        registry: Optional[str] = None,
    ) -> str:

        tag = self.benchmark_image_tag(
            system, benchmark, language_name, language_version, architecture
        )
        repo_name = self.docker_repository()
        if registry is not None:
            return f"{registry}/{repo_name}:{tag}"
        else:
            return f"{repo_name}:{tag}"

    def benchmark_image_tag(
        self,
        system: str,
        benchmark: str,
        language_name: str,
        language_version: str,
        architecture: str,
    ) -> str:
        tag = f"function.{system}.{benchmark}.{language_name}-{language_version}-{architecture}"
        if self.image_tag_prefix:
            tag = f"{tag}-{self.image_tag_prefix}"
        sebs_version = self._system_config["general"].get("SeBS_version", "unknown")
        tag = f"{tag}.{sebs_version}"
        return tag

    def username(self, deployment_name: str, language_name: str) -> str:
        return self._system_config[deployment_name]["languages"][language_name]["username"]
