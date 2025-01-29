from typing import Optional
from sebs.faas.queue import Queue, QueueType

import boto3


class SQS(Queue):
    @staticmethod
    def typename() -> str:
        return "AWS.SQS"

    @staticmethod
    def deployment_name():
        return "aws"

    @property
    def queue_url(self):
        return self._queue_url

    @property
    def queue_arn(self):
        return self._queue_arn

    def __init__(
        self,
        benchmark: str,
        queue_type: QueueType,
        region: str,
        queue_url: Optional[str] = None,
        queue_arn: Optional[str] = None
    ):
        super().__init__(
            benchmark,
            queue_type,
            region
        )
        self._queue_url = queue_url
        self._queue_arn = queue_arn

        self.client = boto3.session.Session().client(
            'sqs',
            region_name=self.region
        )

    def create_queue(self) -> str:
        self.logging.debug(f"Creating queue {self.name}")

        if (self._queue_url and self._queue_arn):
            self.logging.debug("Queue already exists, reusing...")
            return

        self._queue_url = self.client.create_queue(QueueName=self.name)["QueueUrl"]
        self._queue_arn = self.client.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=["QueueArn"],
        )["Attributes"]["QueueArn"]

        self.logging.debug("Created queue")

    def remove_queue(self):
        self.logging.info(f"Deleting queue {self.name}")

        self.client.delete_queue(QueueUrl=self.queue_url)

        self.logging.info("Deleted queue")

    def send_message(self, serialized_message: str):
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=serialized_message,
        )
        self.logging.info(f"Sent message to queue {self.name}")

    def receive_message(self) -> str:
        self.logging.info(f"Pulling a message from {self.name}")

        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            AttributeNames=["SentTimestamp"],
            MaxNumberOfMessages=1,
            MessageAttributeNames=["All"],
            WaitTimeSeconds=5,
        )

        if ("Messages" not in response):
            self.logging.info("No messages to be received")
            return ""

        self.logging.info(f"Received a message from {self.name}")

        # Delete the message from the queue - serves as an acknowledgement
        # that it was received.
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=response["Messages"][0]["ReceiptHandle"],
        )

        return response["Messages"][0]["Body"]

    def serialize(self) -> dict:
        return {
            "name": self.name,
            "type": self.queue_type,
            "region": self.region,
            "queue_url": self.queue_url,
            "queue_arn": self.queue_arn,
        }

    @staticmethod
    def deserialize(obj: dict) -> "SQS":
        return SQS(
            obj["name"],
            obj["type"],
            obj["region"],
            obj["queue_url"],
            obj["queue_arn"]
        )
