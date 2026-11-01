variable "jobs_name" {
  type = string
}

variable "dlq_name" {
  type = string
}

variable "visibility_timeout" {
  description = "Seconds; at least 6x the worker Lambda timeout."
  type        = number
}

variable "max_receives" {
  description = "Receives before a message moves to the DLQ."
  type        = number
}

variable "source_bucket_arn" {
  description = "Bucket allowed to publish upload notifications to the jobs queue."
  type        = string
}

data "aws_caller_identity" "current" {}

resource "aws_sqs_queue" "dlq" {
  name                      = var.dlq_name
  message_retention_seconds = 1209600 # 14 days, the maximum
}

resource "aws_sqs_queue" "jobs" {
  name                       = var.jobs_name
  visibility_timeout_seconds = var.visibility_timeout
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receives
  })
}

# Native DLQ redrive (`make redrive`, entrypoints/redrive) needs the DLQ to name the jobs queue as its source.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.jobs.arn]
  })
}

data "aws_iam_policy_document" "s3_to_jobs" {
  statement {
    sid       = "AllowS3Notifications"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.jobs.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [var.source_bucket_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "jobs" {
  queue_url = aws_sqs_queue.jobs.id
  policy    = data.aws_iam_policy_document.s3_to_jobs.json
}

output "jobs_queue_arn" {
  value = aws_sqs_queue.jobs.arn
}

output "jobs_queue_url" {
  value = aws_sqs_queue.jobs.url
}

output "jobs_queue_name" {
  value = aws_sqs_queue.jobs.name
}

output "dlq_name" {
  value = aws_sqs_queue.dlq.name
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}

output "policy_id" {
  description = "Changes when the queue policy does; storage depends on it."
  value       = aws_sqs_queue_policy.jobs.id
}
