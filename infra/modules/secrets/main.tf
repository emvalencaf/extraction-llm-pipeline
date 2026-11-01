variable "gemini_parameter_name" {
  type = string
}

# SSM Standard SecureString encrypted with the AWS-managed key alias/aws/ssm: no KMS charge.
# Terraform only creates the parameter; the real key is written out of band
# (`aws ssm put-parameter --overwrite`), so it never enters the state or the repo.
resource "aws_ssm_parameter" "gemini_api_key" {
  name  = var.gemini_parameter_name
  type  = "SecureString"
  tier  = "Standard"
  value = "replace-me"

  lifecycle {
    ignore_changes = [value]
  }
}

output "gemini_parameter_name" {
  value = aws_ssm_parameter.gemini_api_key.name
}

output "gemini_parameter_arn" {
  value = aws_ssm_parameter.gemini_api_key.arn
}
