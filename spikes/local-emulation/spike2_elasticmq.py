"""Spike 2: ElasticMQ JVM image: DLQ after maxReceiveCount, then StartMessageMoveTask redrive."""
import json, time
import boto3

kw = dict(endpoint_url="http://localhost:9324", region_name="us-east-1",
          aws_access_key_id="test", aws_secret_access_key="test")
sqs = boto3.client("sqs", **kw)
dlq = sqs.create_queue(QueueName="dlq")["QueueUrl"]
dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
src = sqs.create_queue(QueueName="src", Attributes={
    "VisibilityTimeout": "1",
    "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"})})["QueueUrl"]
src_arn = sqs.get_queue_attributes(QueueUrl=src, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
sqs.send_message(QueueUrl=src, MessageBody="job-1")

seen = 0
for _ in range(3):
    m = sqs.receive_message(QueueUrl=src, WaitTimeSeconds=3, MaxNumberOfMessages=1,
                            AttributeNames=["ApproximateReceiveCount"]).get("Messages", [])
    assert m, "expected message"
    seen += 1
    print("receive", seen, "count attr:", m[0]["Attributes"]["ApproximateReceiveCount"])
    time.sleep(1.3)  # let visibility expire, no delete
m = sqs.receive_message(QueueUrl=src, WaitTimeSeconds=2).get("Messages", [])
print("4th receive on src (expect none):", len(m))
assert not m
time.sleep(1)
d = sqs.receive_message(QueueUrl=dlq, WaitTimeSeconds=3, VisibilityTimeout=0).get("Messages", [])
print("DLQ has message:", bool(d), d[0]["Body"] if d else None)
assert d and d[0]["Body"] == "job-1"
print("DLQ part PASS")

# redrive
t = sqs.start_message_move_task(SourceArn=dlq_arn, DestinationArn=src_arn)
print("StartMessageMoveTask:", t["TaskHandle"][:20], "...")
for _ in range(10):
    lst = sqs.list_message_move_tasks(SourceArn=dlq_arn)["Results"]
    print("task status:", lst[0]["Status"] if lst else None, lst[0].get("ApproximateNumberOfMessagesMoved") if lst else "")
    if lst and lst[0]["Status"] in ("COMPLETED", "FAILED"): break
    time.sleep(1)
back = sqs.receive_message(QueueUrl=src, WaitTimeSeconds=3).get("Messages", [])
print("message back on src:", bool(back), back[0]["Body"] if back else None)
assert back and back[0]["Body"] == "job-1"
print("SPIKE2 PASS")
