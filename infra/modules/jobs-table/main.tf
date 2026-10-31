variable "name" {
  type = string
}

# Jobs and idempotency keys (`idem#<key>` items) share the table; both are keyed by job_id.
resource "aws_dynamodb_table" "this" {
  name         = var.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  server_side_encryption {
    enabled = false # false = AWS-owned key (free); true would bill a KMS key
  }
}

output "name" {
  value = aws_dynamodb_table.this.name
}

output "arn" {
  value = aws_dynamodb_table.this.arn
}
