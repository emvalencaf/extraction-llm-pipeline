"""Spike 1: moto server: S3 presigned PUT, then S3 notification lands on a moto SQS queue."""
import json, sys, time
import boto3, requests
from botocore.config import Config

EP = "http://localhost:5000"
kw = dict(endpoint_url=EP, region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
s3 = boto3.client("s3", config=Config(s3={"addressing_style": "path"}), **kw)
sqs = boto3.client("sqs", **kw)

s3.create_bucket(Bucket="uploads")
q = sqs.create_queue(QueueName="ingest")["QueueUrl"]
arn = sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
s3.put_bucket_notification_configuration(
    Bucket="uploads",
    NotificationConfiguration={"QueueConfigurations": [
        {"QueueArn": arn, "Events": ["s3:ObjectCreated:*"]}]},
)
url = s3.generate_presigned_url("put_object", Params={"Bucket": "uploads", "Key": "inv/1.pdf",
                                "ContentType": "application/pdf"}, ExpiresIn=60)
print("presigned:", url.split("?")[0])
r = requests.put(url, data=b"%PDF-fake", headers={"Content-Type": "application/pdf"})
print("PUT status:", r.status_code)
assert r.status_code == 200, r.text
assert s3.get_object(Bucket="uploads", Key="inv/1.pdf")["Body"].read() == b"%PDF-fake"
from urllib.parse import unquote
rec = None
for _ in range(5):
    for m in sqs.receive_message(QueueUrl=q, WaitTimeSeconds=2, MaxNumberOfMessages=10).get("Messages", []):
        body = json.loads(m["Body"])
        if "Records" not in body:
            print("non-record message (moto test event):", body.get("Event"))
            continue
        rec = body["Records"][0]
    if rec: break
assert rec, "no notification on SQS"
rec["s3"]["object"]["key"] = unquote(rec["s3"]["object"]["key"])  # keys arrive URL-encoded, as on real S3
print("event:", rec["eventName"], rec["s3"]["bucket"]["name"], rec["s3"]["object"]["key"])
assert rec["eventName"].startswith("ObjectCreated") and rec["s3"]["object"]["key"] == "inv/1.pdf"

# extra: presigned PUT with wrong content-type / expired
bad = s3.generate_presigned_url("put_object", Params={"Bucket": "uploads", "Key": "inv/2.pdf"}, ExpiresIn=1)
time.sleep(2.5)
r2 = requests.put(bad, data=b"x")
print("expired URL PUT status (informational):", r2.status_code)
print("SPIKE1 PASS")
