"""DynamoDB implementation of the JobRepository port (one item per job).

Idempotency keys live in the same table as items keyed `idem#<key>` pointing at a job.
Every status change is a conditional write.
"""

from collections.abc import Collection
from dataclasses import asdict

from botocore.exceptions import ClientError

from invoice_extraction.domain.job import Job, JobUpdate
from invoice_extraction.domain.status import IllegalTransitionError, JobStatus

_CONDITION_FAILED = "ConditionalCheckFailedException"
_IDEMPOTENCY_PREFIX = "idem#"


def _conflict(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == _CONDITION_FAILED


class DynamoJobRepository:
    def __init__(self, table) -> None:
        self._table = table

    def create(self, job: Job) -> None:
        self._table.put_item(
            Item={
                "job_id": job.job_id,
                "status": str(job.status),
                "key": job.key,
                "created_at": job.created_at,
            },
            ConditionExpression="attribute_not_exists(job_id)",
        )

    def get(self, job_id: str) -> Job | None:
        if job_id.startswith(_IDEMPOTENCY_PREFIX):  # key records are not jobs
            return None
        item = self._table.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
        if item is None:
            return None
        return Job(
            job_id=item["job_id"],
            status=JobStatus(item["status"]),
            key=item["key"],
            created_at=int(item.get("created_at", 0)),
            errors=item.get("errors", []),
            reason=item.get("reason"),
            result=item.get("result"),
            failure_cause=item.get("failure_cause"),
        )

    def transition(
        self,
        job_id: str,
        to: JobStatus,
        *,
        expected: Collection[JobStatus],
        requires: dict[str, str] | None = None,
        update: JobUpdate | None = None,
    ) -> None:
        fields = {k: v for k, v in asdict(update or JobUpdate()).items() if v is not None}
        sets = {"status": str(to), **fields}
        names = {f"#{k}": k for k in sets}
        values = {f":{k}": v for k, v in sets.items()}
        allowed = [str(s) for s in expected]
        marks = ", ".join(f":from{i}" for i in range(len(allowed)))
        condition = f"attribute_exists(job_id) AND #status IN ({marks})"
        values |= {f":from{i}": s for i, s in enumerate(allowed)}
        for i, (name, value) in enumerate((requires or {}).items()):
            condition += f" AND #req{i} = :req{i}"
            names[f"#req{i}"] = name
            values[f":req{i}"] = value
        try:
            self._table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in sets),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression=condition,
            )
        except ClientError as error:
            if _conflict(error):
                raise IllegalTransitionError(f"job {job_id}: cannot move to {to}") from error
            raise

    def claim_idempotency_key(self, key: str, job_id: str) -> str:
        item_id = f"{_IDEMPOTENCY_PREFIX}{key}"
        try:
            self._table.put_item(
                Item={"job_id": item_id, "target": job_id},
                ConditionExpression="attribute_not_exists(job_id)",
            )
            return job_id
        except ClientError as error:
            if not _conflict(error):
                raise
        return self._table.get_item(Key={"job_id": item_id}, ConsistentRead=True)["Item"]["target"]

    def discard(self, job_id: str) -> None:
        self._table.delete_item(Key={"job_id": job_id})
