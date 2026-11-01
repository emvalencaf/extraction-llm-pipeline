# Bootstrap: the remote-state bucket for ../ . Run once by hand with LOCAL state
# (`terraform -chdir=infra/bootstrap init && terraform -chdir=infra/bootstrap apply`);
# its own state file stays on disk and is git-ignored. Destroy it last.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_suffix" {
  description = "Makes the globally unique bucket name yours (for example your account id)."
  type        = string
}

locals {
  state_bucket = "invoice-extraction-prod-tfstate-${var.bucket_suffix}"
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "invoice-extraction"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# force_destroy so anyone can tear the whole project down, state included.
resource "aws_s3_bucket" "state" {
  bucket        = local.state_bucket
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

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

resource "aws_s3_bucket_policy" "state" {
  bucket     = aws_s3_bucket.state.id
  policy     = data.aws_iam_policy_document.tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.state]
}

output "state_bucket" {
  description = "Put this in infra/backend.hcl."
  value       = aws_s3_bucket.state.bucket
}
