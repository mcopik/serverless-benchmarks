from sebs.faas.queue import Queue, QueueType

from google.api_core import retry
from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

import os


class GCPQueue(Queue):
    @staticmethod
    def typename() -> str:
        return "GCP.Queue"

    @staticmethod
    def deployment_name():
        return "gcp"

    @property
    def topic_name(self):
        return self._topic_name

    @property
    def subscription_name(self):
        return self._subscription_name

    @property
    def subscription_client(self):
        return self._subscription_client

    def __init__(
        self,
        benchmark: str,
        queue_type: QueueType,
        region: str
    ):
        super().__init__(
            benchmark,
            queue_type,
            region
        )
        self.client = pubsub_v1.PublisherClient()
        self._subscription_client = pubsub_v1.SubscriberClient()

        self._topic_name = 'projects/{project_id}/topics/{topic}'.format(
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT'),
            topic=self.name,
        )
        self._subscription_name = 'projects/{project_id}/subscriptions/{sub}'.format(
            project_id=os.getenv('GOOGLE_CLOUD_PROJECT'),
            sub=self.name,
        )

    def create_queue(self):
        self.logging.info(f"Creating queue {self.name}")
        try:
            self.client.create_topic(name=self.topic_name)
            self.logging.info("Created queue")
        except AlreadyExists:
            self.logging.info("Queue already exists, reusing...")

        # GCP additionally needs a 'subscription' resource which is the
        # actual receiver of the messages. It is constructed and destructed
        # alongside the topic at all times.
        self.logging.info("Creating queue subscription")
        try:
            self.subscription_client.create_subscription(
                name=self.subscription_name,
                topic=self.topic_name
            )
            self.logging.info("Created queue subscription")
        except AlreadyExists:
            self.logging.info("Subscription already exists, reusing...")

    def remove_queue(self):
        self.logging.info(f"Deleting queue and associated subscription{self.name}")

        self.client.delete_topic(topic=self.topic_name)
        self.subscription_client.delete_subscription(subscription=self.subscription_name)

        self.logging.info("Deleted queue and associated subscription")

    def send_message(self, serialized_message: str):
        self.client.publish(self.topic_name, serialized_message.decode("utf-8"))
        self.logging.info(f"Sent message to queue {self.name}")

    # Receive messages through the 'pull' (sync) method.
    def receive_message(self) -> str:
        self.logging.info(f"Pulling a message from {self.name}")

        response = self.subscription_client.pull(
            subscription=self.subscription_name,
            max_messages=1,
            retry=retry.Retry(deadline=5),
        )

        if (len(response.received_messages) == 0):
            self.logging.info("No messages to be received")
            return ""

        # Acknowledge the received message so it is not sent again.
        received_message = response.received_messages[0]
        self.subscription_client.acknowledge(
            subscription=self.subscription_name,
            ack_ids=[received_message.ack_id],
        )
        self.logging.info(f"Received a message from {self.name}")

        return received_message.message.data

    def serialize(self) -> dict:
        return {
            "name": self.name,
            "type": self.queue_type,
            "region": self.region,
        }

    @staticmethod
    def deserialize(obj: dict) -> "GCPQueue":
        return GCPQueue(
            obj["name"],
            obj["type"],
            obj["region"],
        )
