output "role_arn" {
  description = "ARN of the role. Store it as a GitHub Actions variable (AWS_BUILD_ROLE_ARN / AWS_DEPLOY_ROLE_ARN)."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Name of the role."
  value       = aws_iam_role.this.name
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider (created or looked up)."
  value       = local.oidc_provider_arn
}
