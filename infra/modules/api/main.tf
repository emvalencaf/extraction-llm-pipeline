variable "name" {
  type = string
}

variable "image_uri" {
  type = string
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

variable "upload_ttl_seconds" {
  description = "Lifetime of the presigned PUT URL."
  type        = number
}

variable "rate_limit" {
  type = number
}

variable "burst_limit" {
  type = number
}

variable "get_rate_limit" {
  type = number
}

variable "get_burst_limit" {
  type = number
}

variable "daily_quota" {
  type = number
}

variable "stage_name" {
  type    = string
  default = "v1"
}

# ---- Lambda (default image command is the API handler) ----

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
    # Signs the presigned PUT for uploads/<job_id>.pdf; the URL carries these rights.
    sid       = "PresignUploads"
    actions   = ["s3:PutObject"]
    resources = ["${var.bucket_arn}/uploads/*"]
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
  timeout       = 10 # API Gateway answers at 29 s at most
  memory_size   = 512

  image_config {
    command = ["invoice_extraction.entrypoints.api_handler.handler"]
  }

  environment {
    variables = {
      JOBS_TABLE         = var.jobs_table_name
      BUCKET             = var.bucket_name
      UPLOAD_TTL_SECONDS = tostring(var.upload_ttl_seconds)
      # The API only creates and reads jobs, never calls the model: the fake URL is a placeholder
      # that composition/runtime.py needs when no Gemini key is configured.
      FAKE_GEMINI_URL = "http://unused.invalid"
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

# ---- API Gateway (REST) ----

resource "aws_api_gateway_rest_api" "this" {
  name = var.name

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "jobs" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "jobs"
}

resource "aws_api_gateway_resource" "job" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.jobs.id
  path_part   = "{job_id}"
}

locals {
  # method -> resource; every method requires the API key (missing or bad key: 403 JSON).
  methods = {
    post_jobs = { resource_id = aws_api_gateway_resource.jobs.id, http_method = "POST" }
    get_job   = { resource_id = aws_api_gateway_resource.job.id, http_method = "GET" }
  }
}

resource "aws_api_gateway_method" "this" {
  for_each = local.methods

  rest_api_id      = aws_api_gateway_rest_api.this.id
  resource_id      = each.value.resource_id
  http_method      = each.value.http_method
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "this" {
  for_each = local.methods

  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.this[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.this.invoke_arn
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.jobs.id,
      aws_api_gateway_resource.job.id,
      aws_api_gateway_method.this,
      aws_api_gateway_integration.this,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name
}

# Per-method throttling: POST and GET are limited apart so polling cannot starve job creation.
resource "aws_api_gateway_method_settings" "post_jobs" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "jobs/POST"

  settings {
    throttling_rate_limit  = var.rate_limit
    throttling_burst_limit = var.burst_limit
  }
}

resource "aws_api_gateway_method_settings" "get_job" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "jobs/{job_id}/GET"

  settings {
    throttling_rate_limit  = var.get_rate_limit
    throttling_burst_limit = var.get_burst_limit
  }
}

# ---- API key and usage plan ----
# A single key. Rotate by `terraform apply -replace=module.api.aws_api_gateway_api_key.this`.

resource "aws_api_gateway_api_key" "this" {
  name    = var.name
  enabled = true
}

resource "aws_api_gateway_usage_plan" "this" {
  name = var.name

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.this.stage_name
  }

  throttle_settings {
    rate_limit  = var.rate_limit
    burst_limit = var.burst_limit
  }

  quota_settings {
    limit  = var.daily_quota
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "this" {
  key_id        = aws_api_gateway_api_key.this.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.this.id
}

output "invoke_url" {
  value = aws_api_gateway_stage.this.invoke_url
}

output "api_key_id" {
  value = aws_api_gateway_api_key.this.id
}

output "function_name" {
  value = aws_lambda_function.this.function_name
}
