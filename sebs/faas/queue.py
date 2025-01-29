from abc import ABC
from abc import abstractmethod
from enum import Enum

from sebs.utils import LoggingBase


class QueueType(str, Enum):
    TRIGGER = "trigger"
    RESULT = "result"


class Queue(ABC, LoggingBase):

    @staticmethod
    @abstractmethod
    def deployment_name() -> str:
        pass

    @property
    def region(self):
        return self._region

    @property
    def queue_type(self):
        return self._queue_type

    @property
    def name(self):
        return self._name

    def __init__(
        self,
        benchmark: str,
        queue_type: QueueType,
        region: str
    ):
        super().__init__()
        self._name = benchmark

        # Convention: the trigger queue carries the name of the function. The
        # result queue carries the name of the function + "-result".
        if (queue_type == QueueType.RESULT and not benchmark.endswith("-result")):
            self._name = "{}-{}".format(benchmark, queue_type)

        self._queue_type = queue_type
        self._region = region

    @abstractmethod
    def create_queue(self):
        pass

    @abstractmethod
    def remove_queue(self):
        pass

    @abstractmethod
    def send_message(self, serialized_message: str):
        pass

    @abstractmethod
    def receive_message(self) -> str:
        pass
