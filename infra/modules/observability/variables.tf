variable "prefix" {
  description = "Name prefix of the stack; alarms, topic, dashboard and budget are named from it."
  type        = string
}

variable "alert_email" {
  description = "Address subscribed to the alerts topic. AWS emails a confirmation link to it."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "region" {
  description = "Region of the stack, used by the dashboard widgets."
  type        = string
}

variable "worker_function_name" {
  type = string
}

variable "api_function_name" {
  type = string
}

variable "jobs_queue_name" {
  type = string
}

variable "dlq_name" {
  type = string
}

variable "worker_timeout_seconds" {
  description = "Worker Lambda timeout; job-duration-high fires at 80% of it."
  type        = number
}

variable "queue_age_threshold_seconds" {
  description = "Age of the oldest queued message that means the worker is not keeping up."
  type        = number
  default     = 900
}

variable "grounding_rate_floor" {
  description = "Average Grounding Rate below this over the period raises grounding-rate-low."
  type        = number
  default     = 0.8
}

variable "budget_usd" {
  description = "Monthly cost budget in USD, filtered by the Project tag."
  type        = number
  default     = 10
}

variable "budget_tag_key" {
  type    = string
  default = "Project"
}

variable "budget_tag_value" {
  type = string
}
