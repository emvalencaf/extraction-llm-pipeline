# Presigned S3 upload, with S3 events going straight to SQS

`POST /jobs` returns a presigned PUT URL and the client uploads the PDF to
`raw/{job_id}.pdf`, so the 10 MB and 29 s API Gateway limits never apply to the
document. The S3 `ObjectCreated` notification goes directly to SQS with no
intermediate Lambda, and the worker derives `job_id` from the key. Size and page
limits are enforced by `content-length-range` on the upload and rechecked by the
worker.
