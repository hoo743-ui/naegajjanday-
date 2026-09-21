output "ecr_repository_urls" {
  description = "Map of repository name => URL."
  value       = module.ecr.repository_urls
}

output "ecr_repository_arns" {
  description = "Map of repository name => ARN."
  value       = module.ecr.repository_arns
}

output "build_role_arn" {
  description = "Store as the repository-level GitHub Actions variable AWS_BUILD_ROLE_ARN."
  value       = module.build_role.role_arn
}

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider."
  value       = module.build_role.oidc_provider_arn
}
