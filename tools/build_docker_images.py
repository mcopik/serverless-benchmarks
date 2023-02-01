#!/usr/bin/env python3

import argparse
import docker
import json
import os

PROJECT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, "docker")

parser = argparse.ArgumentParser(description="Run local app experiments.")
parser.add_argument(
    "--deployment", default=None, choices=["local", "aws", "azure", "gcp"], action="store"
)
parser.add_argument("--type", default=None, choices=["build", "dependencies", "run", "manage"], action="store")
parser.add_argument("--type-tag", default=None, type=str, action="store")
parser.add_argument("--language", default=None, choices=["python", "nodejs", "cpp"], action="store")
parser.add_argument('--parallel', default=1, type=int, action='store')
args = parser.parse_args()
config = json.load(open(os.path.join(PROJECT_DIR, "config", "systems.json"), "r"))
client = docker.from_env()


def build(image_type, system, language=None, version=None, version_name=None):

    msg = "Build *{}* Dockerfile for *{}* system".format(image_type, system)
    if language:
        msg += " with language *" + language + "*"
    if version:
        msg += " with version *" + version + "*"
    print(msg)
    if language is not None:
        dockerfile = os.path.join(PROJECT_DIR, "docker", system, language, f"Dockerfile.{image_type}")
    else:
        dockerfile = os.path.join(PROJECT_DIR, "docker", system, f"Dockerfile.{image_type}")
    target = f'{config["general"]["docker_repository"]}:{image_type}.{system}'
    if language:
        target += "." + language
    if version:
        target += "." + version

    # if we pass an integer, the build will fail with 'connection reset by peer'
    buildargs = {
        "VERSION": version,
        'WORKERS': str(args.parallel),
        'BASE_REPOSITORY': config["general"]["docker_repository"]
    }
    if version:
        buildargs["BASE_IMAGE"] = version_name
    print(
        "Build img {} in {} from file {} with args {}".format(
            target, PROJECT_DIR, dockerfile, buildargs
        )
    )
    client.images.build(path=PROJECT_DIR, dockerfile=dockerfile, buildargs=buildargs, tag=target)

def build_language(system, language, language_config):
    configs = []
    if "base_images" in language_config:
        for version, base_image in language_config["base_images"].items():
            configs.append([version, base_image])
    else:
        configs.append([None, None])

    for image in configs:
        if args.type is None:
            for image_type in language_config["images"]:
                build(image_type, system, language, *image)
        else:
            build(args.type, system, language, *image)


def build_systems(system, system_config):

    if args.type == "manage":
        if "images" in system_config:
            build(args.type, system)
        else:
            print(f"Skipping manage image for {system}")
    elif args.type == "dependencies":
        if args.language:
            if "dependencies" in system_config["languages"][args.language]:
                language_config = system_config["languages"][args.language]
                # for all dependencies 
                if args.type_tag:
                    # for all image versions
                    for version, base_image in language_config["base_images"].items():
                        build(f"{args.type}-{args.type_tag}", system, args.language, version, base_image)
                else:
                    for dep in system_config["languages"][args.language]["dependencies"]:
                        # for all image versions
                        for version, base_image in language_config["base_images"].items():
                            build(f"{args.type}-{dep}", system, args.language, version, base_image)
        else:
            raise RuntimeError('Language must be specified for dependencies')
    else:
        if args.language:
            build_language(system, args.language, system_config["languages"][args.language])
        else:
            for language, language_dict in system_config["languages"].items():
                build_language(system, language, language_dict)
            # Build additional types
            if "images" in system_config:
                for image_type, image_config in system_config["images"].items():
                    build(image_type, system)


if args.deployment is None:
    for system, system_dict in config.items():
        if system == "general":
            continue
        build_systems(system, system_dict)
else:
    build_systems(args.deployment, config[args.deployment])
