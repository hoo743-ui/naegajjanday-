output "name_prefix" {
  description = "Resource name prefix (<project>-<environment>)."
  value       = local.name_prefix
}

output "site_url" {
  description = "Public URL of the web app."
  value       = local.site_url
}

output "api_base_url" {
  description = "Public base URL of the API (docs/03-api-spec.md)."
  value       = "https://${local.api_host}/v1"
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (ECS tasks)."
  value       = module.network.private_subnet_ids
}

output "nat_gateway_public_ips" {
  description = "Egress IPs of the environment (for third-party API allowlists)."
  value       = module.network.nat_gateway_public_ips
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "ecs_service_names" {
  description = "ECS service names by logical name."
  value = merge(
    {
      api    = module.api.service_name
      worker = module.worker.service_name
      web    = module.web.service_name
    },
    { for i, m in module.beat : "beat" => m.service_name },
  )
}

output "alb_dns_name" {
  description = "DNS name of the ALB (only reachable from CloudFront)."
  value       = module.alb.alb_dns_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution id."
  value       = module.edge.distribution_id
}

output "assets_bucket_name" {
  description = "S3 bucket for banners / uploads, served under /assets/*."
  value       = module.edge.assets_bucket_name
}

output "rds_address" {
  description = "RDS primary host name."
  value       = module.rds.address
}

output "rds_replica_address" {
  description = "RDS read replica host name (null when disabled)."
  value       = module.rds.replica_address
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint."
  value       = module.redis.primary_endpoint_address
}

output "opensearch_endpoint" {
  description = "OpenSearch VPC endpoint."
  value       = module.opensearch.endpoint
}

output "app_secret_arn" {
  description = "Secrets Manager secret holding the application keys (fill in the placeholders after the first apply)."
  value       = aws_secretsmanager_secret.app.arn
}

output "alarm_topic_arn" {
  description = "SNS topic receiving CloudWatch alarms."
  value       = module.observability.sns_topic_arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard name."
  value       = module.observability.dashboard_name
}

output "deploy_role_arn" {
  description = "IAM role assumed by the GitHub Actions deploy jobs of this environment."
  value       = module.deploy_role.role_arn
}

output "github_environment_variables" {
  description = "Values to store as variables of the matching GitHub Environment (Settings > Environments). Consumed by .github/workflows/deploy.yml."
  value = {
    AWS_DEPLOY_ROLE_ARN        = module.deploy_role.role_arn
    ECS_CLUSTER                = aws_ecs_cluster.this.name
    NAME_PREFIX                = local.name_prefix
    BASE_URL                   = local.site_url
    CLOUDFRONT_DISTRIBUTION_ID = module.edge.distribution_id
  }
}
