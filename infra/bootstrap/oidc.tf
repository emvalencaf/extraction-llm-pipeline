# GitHub Actions federation (spec #27, ticket #44). Lives here, not in the main stack, so the
# deploy role can never modify the roles that grant it access: bootstrap is applied by hand.

variable "github_repo" {
  description = "owner/name of the repository whose workflows may assume the roles."
  type        = string
  default     = "emvalencaf/extraction-llm-pipeline"
}

variable "create_oidc_provider" {
  description = "Set false when the account already has the GitHub OIDC provider (one per account)."
  type        = bool
  default     = true
}

variable "deploy_environment" {
  description = "GitHub Environment whose required-reviewer approval gates the deploy role."
  type        = string
  default     = "production"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1

  url = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  oidc_host         = "token.actions.githubusercontent.com"
  plan_role_name    = "invoice-extraction-prod-gha-plan"
  deploy_role_name  = "invoice-extraction-prod-gha-deploy"
}

# Plan: only `pull_request` runs of this repository. Read-only, and workflows run it with
# `-lock=false` because taking the S3 lock would be a write.
data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["repo:${var.github_repo}:pull_request"]
    }
  }
}

resource "aws_iam_role" "plan" {
  name                 = local.plan_role_name
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Deploy: only jobs that target the `production` Environment (required reviewers) AND run the
# deploy workflow from master. The sub claim carries the Environment, job_workflow_ref the ref.
data "aws_iam_policy_document" "deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["repo:${var.github_repo}:environment:${var.deploy_environment}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:job_workflow_ref"
      values   = ["${var.github_repo}/.github/workflows/deploy.yml@refs/heads/master"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = local.deploy_role_name
  assume_role_policy   = data.aws_iam_policy_document.deploy_trust.json
  max_session_duration = 3600
}

# The stack creates IAM roles, ECR, API Gateway, Lambda, SQS, SNS, budgets and more, so the
# role is broad; the explicit deny below keeps it from touching its own and the plan role.
resource "aws_iam_role_policy_attachment" "deploy_admin" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

data "aws_iam_policy_document" "deploy_guard" {
  statement {
    sid    = "ProtectFederation"
    effect = "Deny"
    actions = [
      "iam:*",
    ]
    resources = [
      aws_iam_role.plan.arn,
      aws_iam_role.deploy.arn,
      local.oidc_provider_arn,
    ]
  }
}

resource "aws_iam_role_policy" "deploy_guard" {
  name   = "protect-federation"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_guard.json
}

output "plan_role_arn" {
  description = "Repository variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arn" {
  description = "Repository variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.deploy.arn
}
