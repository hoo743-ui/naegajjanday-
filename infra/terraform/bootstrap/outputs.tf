output "state_bucket_name" {
  description = "Put this value into bucket = ... of every envs/*/backend.hcl."
  value       = aws_s3_bucket.state.bucket
}

output "lock_table_name" {
  description = "DynamoDB table used for state locking."
  value       = aws_dynamodb_table.lock.name
}
