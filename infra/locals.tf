locals {
  environment = "prod"
  prefix      = "invoice-extraction-${local.environment}"

  # Logical resource names. The local stack's boto3 init (src/invoice_extraction/entrypoints/
  # init_resources.py) creates the same names unprefixed; check_against_terraform keeps both in step.
  names = {
    bucket     = "invoices"
    table      = "jobs"
    queue      = "jobs"
    dlq        = "jobs-dlq"
    ssm_gemini = "gemini-api-key"
  }

  common_tags = {
    Project     = "invoice-extraction"
    Environment = local.environment
    ManagedBy   = "terraform"
  }

  # S3 bucket names are global, hence the suffix.
  bucket_name = "${local.prefix}-${local.names.bucket}-${var.bucket_suffix}"

  # Worker: visibility timeout is at least 6x the Lambda timeout (AWS guidance for SQS triggers).
  worker_timeout_seconds = 120
  visibility_timeout     = 6 * local.worker_timeout_seconds
  max_receives           = 5
  upload_ttl_seconds     = 900 # presigned PUT expires after 15 minutes
}
