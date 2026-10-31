terraform {
  # >= 1.10 for S3-native state locking (use_lockfile), no DynamoDB lock table.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Partial configuration: `terraform init -backend-config=backend.hcl`
  # (see backend.hcl.example). The state bucket comes from infra/bootstrap.
  backend "s3" {
    key          = "prod/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.common_tags
  }
}
