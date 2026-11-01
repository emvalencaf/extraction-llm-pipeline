output "api_url" {
  description = "Invoke URL of the API (POST /jobs, GET /jobs/{job_id})."
  value       = module.api.invoke_url
}

output "api_key_id" {
  description = "ID of the API key; read its value with `aws apigateway get-api-key --include-value`."
  value       = module.api.api_key_id
}

output "bucket_name" {
  value = module.storage.bucket_name
}

output "jobs_table_name" {
  value = module.jobs_table.name
}

output "jobs_queue_url" {
  value = module.queue.jobs_queue_url
}

output "dlq_url" {
  value = module.queue.dlq_url
}

output "ecr_repository_url" {
  value = module.registry.repository_url
}

output "gemini_parameter_name" {
  description = "SSM SecureString to fill with the Gemini API key (see scripts/deploy-infra.sh)."
  value       = module.secrets.gemini_parameter_name
}

output "alerts_topic_arn" {
  description = "SNS topic every alarm and the budget publish to."
  value       = module.observability.alerts_topic_arn
}

output "dashboard_name" {
  value = module.observability.dashboard_name
}

output "worker_function_name" {
  value = module.worker.function_name
}

output "api_function_name" {
  value = module.api.function_name
}
