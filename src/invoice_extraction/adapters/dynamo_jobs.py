"""DynamoDB implementation of the JobRepository port (one item per job)."""

from typing import Any


class DynamoJobRepository:
    def __init__(self, table) -> None:
        self._table = table

    def create(self, job: dict[str, Any]) -> None:
        self._table.put_item(
            Item={**job, "status": str(job["status"])},
            ConditionExpression="attribute_not_exists(job_id)",
        )

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._table.get_item(Key={"job_id": job_id}).get("Item")

    def update(self, job_id: str, **fields: Any) -> None:
        fields = {k: str(v) if k == "status" else v for k, v in fields.items()}
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        self._table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(job_id)",
        )
