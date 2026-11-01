module "registry" {
  source = "./modules/registry"

  name = "${local.prefix}-lambda"
}

module "jobs_table" {
  source = "./modules/jobs-table"

  name = "${local.prefix}-${local.names.table}"
}

module "queue" {
  source = "./modules/queue"

  jobs_name          = "${local.prefix}-${local.names.queue}"
  dlq_name           = "${local.prefix}-${local.names.dlq}"
  visibility_timeout = local.visibility_timeout
  max_receives       = local.max_receives
  source_bucket_arn  = "arn:aws:s3:::${local.bucket_name}" # built from the name to avoid a cycle
}

module "storage" {
  source = "./modules/storage"

  bucket_name      = local.bucket_name
  jobs_queue_arn   = module.queue.jobs_queue_arn
  queue_policy_ref = module.queue.policy_id # notification needs the queue policy first
}

module "secrets" {
  source = "./modules/secrets"

  gemini_parameter_name = "/${local.prefix}/${local.names.ssm_gemini}"
}

module "worker" {
  source = "./modules/worker"

  name                  = "${local.prefix}-worker"
  image_uri             = "${module.registry.repository_url}:${var.image_tag}"
  timeout_seconds       = local.worker_timeout_seconds
  jobs_table_name       = module.jobs_table.name
  jobs_table_arn        = module.jobs_table.arn
  bucket_name           = module.storage.bucket_name
  bucket_arn            = module.storage.bucket_arn
  jobs_queue_arn        = module.queue.jobs_queue_arn
  jobs_queue_url        = module.queue.jobs_queue_url
  max_receives          = local.max_receives
  gemini_parameter_name = module.secrets.gemini_parameter_name
  gemini_parameter_arn  = module.secrets.gemini_parameter_arn
}

module "api" {
  source = "./modules/api"

  name               = "${local.prefix}-api"
  image_uri          = "${module.registry.repository_url}:${var.image_tag}"
  jobs_table_name    = module.jobs_table.name
  jobs_table_arn     = module.jobs_table.arn
  bucket_name        = module.storage.bucket_name
  bucket_arn         = module.storage.bucket_arn
  upload_ttl_seconds = local.upload_ttl_seconds
  rate_limit         = var.rate_limit
  burst_limit        = var.burst_limit
  get_rate_limit     = var.get_rate_limit
  get_burst_limit    = var.get_burst_limit
  daily_quota        = var.daily_quota
}
