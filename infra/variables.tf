variable "region" {
  description = "Single AWS region of the stack."
  type        = string
  default     = "us-east-1"
}

variable "bucket_suffix" {
  description = "Suffix that makes the globally unique S3 bucket name yours (for example your account id)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.bucket_suffix))
    error_message = "bucket_suffix must be 3-20 lowercase letters, digits or hyphens."
  }
}

variable "image_tag" {
  description = "Tag of the shared Lambda image in ECR; scripts/deploy-infra.sh passes the commit SHA."
  type        = string
}

# Observability (spec #27, decisions #22 and #36).
variable "alert_email" {
  description = "Address that receives alarm and budget notifications; confirm the SNS email once."
  type        = string
}

variable "budget_usd" {
  description = "Monthly USD budget for resources tagged Project=invoice-extraction."
  type        = number
  default     = 10
}

# Usage plan (spec #27, decision #26).
variable "rate_limit" {
  description = "Steady-state requests per second for POST /jobs."
  type        = number
  default     = 1
}

variable "burst_limit" {
  description = "Burst size for POST /jobs."
  type        = number
  default     = 2
}

variable "get_rate_limit" {
  description = "Steady-state requests per second for GET /jobs/{job_id}, throttled apart from POST."
  type        = number
  default     = 20
}

variable "get_burst_limit" {
  description = "Burst size for GET /jobs/{job_id}."
  type        = number
  default     = 40
}

variable "daily_quota" {
  description = <<-EOT
    Requests per day allowed by the usage plan. API Gateway quotas are plan-wide, not per
    method, so GET polling counts too: the default leaves room for 100 POST/day plus polling.
  EOT
  type        = number
  default     = 1000
}
