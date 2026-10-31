"""S3 implementation of the BlobStore port."""

from botocore.exceptions import ClientError

from invoice_extraction.application.ports import BlobNotFoundError


class S3BlobStore:
    def __init__(self, client, bucket: str, presign_client=None, expires: int = 900) -> None:
        self._client = client
        self._bucket = bucket
        # Presigned URLs must name a host the uploader can reach, which may differ
        # from the one the service itself uses (containers vs host).
        self._presigner = presign_client or client
        self._expires = expires

    def presign_put(self, key: str) -> str:
        return self._presigner.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._expires,
        )

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as error:
            if error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise BlobNotFoundError(key) from error
            raise
