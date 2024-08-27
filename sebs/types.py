from enum import Enum


class BenchmarkModule(str, Enum):
    STORAGE = "storage"
    NOSQL = "nosql"


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


class NoSQLStorage(str, Enum):
    AWS_DYNAMODB = "aws-dynamodb"
    AZURE_COSMOSDB = "azure-cosmosdb"
    GCP_DATASTORE = "google-cloud-datastore"
    SCYLLADB = "scylladb"
