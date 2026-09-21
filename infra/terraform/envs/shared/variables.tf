variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "ap-northeast-2"
}

variable "project" {
  description = "Project slug. Also the ECR namespace (naegajjanday/api, naegajjanday/web)."
  type        = string
  default     = "naegajjanday"
}

variable "github_repository" {
  description = "GitHub repository in owner/name form."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "deploy_branch" {
  description = "Branch whose pushes may build and push images."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if the account already has one for token.actions.githubusercontent.com."
  type        = bool
  default     = true
}

variable "ecr_keep_last_images" {
  description = "Images kept per ECR repository."
  type        = number
  default     = 50
}
