variable "bucket_name" {
  type = string
}

variable "jobs_queue_arn" {
  type = string
}

variable "queue_policy_ref" {
  description = "Queue policy id: forces the policy to exist before S3 validates the notification."
  type        = string
}

# One bucket, two zones by prefix: uploads/ (raw PDFs, from the presigned PUT) and processed/.
resource "aws_s3_bucket" "this" {
  bucket        = var.bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket     = aws_s3_bucket.this.id
  policy     = data.aws_iam_policy_document.tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}

# Abandoned uploads and old results do not accumulate past the free 5 GB.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "expire-uploads"
    status = "Enabled"
    filter { prefix = "uploads/" }
    expiration { days = 7 }
  }

  rule {
    id     = "expire-processed"
    status = "Enabled"
    filter { prefix = "processed/" }
    expiration { days = 30 }
  }
}

# The upload triggers processing: S3 -> jobs queue -> worker (the local poller relays the same event).
resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.this.id

  queue {
    queue_arn     = var.jobs_queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "uploads/"
  }

  depends_on = [var.queue_policy_ref]
}

output "bucket_name" {
  value = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}
