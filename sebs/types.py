from __future__ import annotations
from enum import Enum


class Platforms(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    LOCAL = "local"
    OPENWHISK = "openwhisk"


class Storage(str, Enum):
    AWS_S3 = "aws-s3"
    AZURE_BLOB_STORAGE = "azure-blob-storage"
    GCP_STORAGE = "google-cloud-storage"
    MINIO = "minio"


class Language(str, Enum):
    PYTHON = "python"
    NODEJS = "nodejs"
    CPP = "cpp"

    @staticmethod
    def deserialize(val: str) -> Language:
        for member in Language:
            if member.value == val:
                return member
        raise Exception(f"Unknown language type {member}")


class Architecture(str, Enum):
    X86 = "x86"
    ARM = "arm"

    def serialize(self) -> str:
        return self.value

    @staticmethod
    def deserialize(val: str) -> Architecture:
        for member in Architecture:
            if member.value == val:
                return member
        raise Exception(f"Unknown architecture type {member}")
