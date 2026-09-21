output "replication_group_id" {
  description = "ID of the replication group."
  value       = aws_elasticache_replication_group.this.id
}

output "member_cluster_ids" {
  description = "Deterministic member cluster ids (CloudWatch CacheClusterId dimension)."
  value       = local.member_cluster_ids
}

output "primary_endpoint_address" {
  description = "Primary (read/write) endpoint."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "reader_endpoint_address" {
  description = "Reader endpoint."
  value       = aws_elasticache_replication_group.this.reader_endpoint_address
}

output "port" {
  description = "Redis port."
  value       = local.port
}

output "url_scheme" {
  description = "redis or rediss depending on transit encryption."
  value       = var.transit_encryption_enabled ? "rediss" : "redis"
}

output "security_group_id" {
  description = "Security group attached to the replication group."
  value       = aws_security_group.this.id
}
