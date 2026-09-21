output "site_url" {
  description = "Public URL of the web app."
  value       = module.stack.site_url
}

output "api_base_url" {
  description = "Public base URL of the API."
  value       = module.stack.api_base_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = module.stack.ecs_cluster_name
}

output "ecs_service_names" {
  description = "ECS service names by logical name."
  value       = module.stack.ecs_service_names
}

output "nat_gateway_public_ips" {
  description = "Egress IPs (third-party API allowlists)."
  value       = module.stack.nat_gateway_public_ips
}

output "app_secret_arn" {
  description = "Secrets Manager secret to fill in after the first apply."
  value       = module.stack.app_secret_arn
}

output "assets_bucket_name" {
  description = "S3 assets bucket."
  value       = module.stack.assets_bucket_name
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.stack.dashboard_name
}

output "deploy_role_arn" {
  description = "IAM role assumed by the GitHub Actions deploy job."
  value       = module.stack.deploy_role_arn
}

output "github_environment_variables" {
  description = "Copy these into the GitHub Environment variables."
  value       = module.stack.github_environment_variables
}
