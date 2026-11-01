variable "name" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "timeout_seconds" {
  type = number
}

variable "memory_mb" {
  description = "Presidio and spaCy load at cold start; memory also buys CPU."
  type        = number
  default     = 2048
}

variable "jobs_table_name" {
  type = string
}

variable "jobs_table_arn" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "bucket_arn" {
  type = string
}

variable "jobs_queue_arn" {
  type = string
}

variable "jobs_queue_url" {
  type = string
}

variable "max_receives" {
  type = number
}

variable "gemini_parameter_name" {
  type = string
}

variable "gemini_parameter_arn" {
  type = string
}

variable "max_concurrency" {
  description = "Concurrent worker invocations; 2 keeps Gemini inside its free-tier rate limit."
  type        = number
  default     = 2
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 14
}

# Least privilege: this role cannot create jobs or presign uploads; the api role cannot read
# uploads or the queue.
data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid       = "JobsTable"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [var.jobs_table_arn]
  }

  statement {
    sid       = "ReadUploads"
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
  }

  statement {
    # Without s3:ListBucket a missing key answers 403 instead of 404.
    sid       = "ListUploads"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }

  statement {
    sid = "ConsumeJobs"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [var.jobs_queue_arn]
  }

  statement {
    sid       = "GeminiKey"
    actions   = ["ssm:GetParameter"]
    resources = [var.gemini_parameter_arn]
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "permissions"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_lambda_function" "this" {
  function_name = var.name
  role          = aws_iam_role.this.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = var.timeout_seconds
  memory_size   = var.memory_mb

  image_config {
    command = ["invoice_extraction.entrypoints.worker_handler.handler"]
  }

  environment {
    variables = {
      JOBS_TABLE                   = var.jobs_table_name
      BUCKET                       = var.bucket_name
      JOBS_QUEUE_URL               = var.jobs_queue_url
      MAX_RECEIVES                 = tostring(var.max_receives)
      RETRY_BASE_SECONDS           = "30"
      RETRY_CAP_SECONDS            = "900"
      GEMINI_API_KEY_SSM_PARAMETER = var.gemini_parameter_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

# Batch 1, concurrency 2, partial-batch responses: a failed record is retried alone.
resource "aws_lambda_event_source_mapping" "jobs" {
  event_source_arn        = var.jobs_queue_arn
  function_name           = aws_lambda_function.this.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.max_concurrency
  }
}

output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}
