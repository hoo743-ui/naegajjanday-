output "domain_name" {
  description = "Name of the OpenSearch domain (CloudWatch DomainName dimension)."
  value       = aws_opensearch_domain.this.domain_name
}

output "domain_arn" {
  description = "ARN of the OpenSearch domain."
  value       = aws_opensearch_domain.this.arn
}

output "endpoint" {
  description = "VPC endpoint host name of the domain (no scheme)."
  value       = aws_opensearch_domain.this.endpoint
}

output "url" {
  description = "HTTPS URL of the domain."
  value       = "https://${aws_opensearch_domain.this.endpoint}:443"
}

output "security_group_id" {
  description = "Security group attached to the domain."
  value       = aws_security_group.this.id
}

output "credentials_secret_arn" {
  description = "Secrets Manager secret with JSON keys username, password, endpoint and url (endpoint with embedded basic auth)."
  value       = aws_secretsmanager_secret.credentials.arn
}

output "nori_user_dictionary_package_id" {
  description = "Package id to reference as analyzers/<id> in the nori tokenizer, or null."
  value       = one(aws_opensearch_package.nori_user_dictionary[*].id)
}
