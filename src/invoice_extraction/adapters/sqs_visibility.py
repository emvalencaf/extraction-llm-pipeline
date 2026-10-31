"""SQS implementation of the QueueDelayer port: grow the visibility delay of a message."""


class SqsVisibility:
    def __init__(self, client, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url

    def delay(self, receipt_handle: str, seconds: int) -> None:
        self._client.change_message_visibility(
            QueueUrl=self._queue_url, ReceiptHandle=receipt_handle, VisibilityTimeout=seconds
        )
