# Secrets in SSM Standard SecureString

The production Gemini key and the API key live in SSM SecureString parameters of
the Standard tier, encrypted with the AWS-managed `aws/ssm` key, which is free.
Terraform creates a placeholder with `ignore_changes = [value]` and the operator
sets the real value once by hand, so secrets never enter state or the repo. A
customer-managed KMS key (about US$ 1 a month), Advanced parameters and Secrets
Manager were rejected as outside the free tier.
