output "instance_id" {
  description = "Identifier of the primary instance (CloudWatch DBInstanceIdentifier dimension)."
  value       = aws_db_instance.this.identifier
}

output "instance_arn" {
  description = "ARN of the primary instance."
  value       = aws_db_instance.this.arn
}

output "address" {
  description = "Hostname of the primary instance."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Name of the initial database."
  value       = var.db_name
}

output "replica_address" {
  description = "Hostname of the read replica, or null when none exists."
  value       = one(aws_db_instance.replica[*].address)
}

output "replica_instance_id" {
  description = "Identifier of the read replica, or null when none exists."
  value       = one(aws_db_instance.replica[*].identifier)
}

output "security_group_id" {
  description = "Security group attached to the database."
  value       = aws_security_group.this.id
}

output "credentials_secret_arn" {
  description = "Secrets Manager secret with JSON keys username, password, host, port, dbname and url (ready-to-use DSN)."
  value       = aws_secretsmanager_secret.credentials.arn
}
