variable "role_name" {
  description = "Name of the IAM role GitHub Actions assumes."
  type        = string

  validation {
    condition     = length(var.role_name) <= 64
    error_message = "IAM role names are limited to 64 characters."
  }
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Only ONE provider per URL can exist in an AWS account, so exactly one stack per account sets this to true (envs/shared); the others look it up."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "GitHub repository in owner/name form."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "allowed_subjects" {
  description = "Allowed OIDC subject suffixes after repo:<owner>/<name>: . Jobs bound to a GitHub Environment present environment:<name>; other jobs present ref:refs/heads/<branch>."
  type        = list(string)

  validation {
    condition     = length(var.allowed_subjects) > 0 && alltrue([for s in var.allowed_subjects : !strcontains(s, "*")])
    error_message = "allowed_subjects must be non-empty and must not contain wildcards."
  }
}

variable "max_session_duration" {
  description = "Maximum session duration of the role in seconds."
  type        = number
  default     = 3600
}

# ----------------------------------------------------------------------------
# ECR
# ----------------------------------------------------------------------------

variable "ecr_repository_arns" {
  description = "ECR repositories this role may access."
  type        = list(string)
  default     = []
}

variable "allow_ecr_push" {
  description = "Allow pushing images to ecr_repository_arns (build role). false = pull/describe only."
  type        = bool
  default     = false
}

# ----------------------------------------------------------------------------
# ECS deploy
# ----------------------------------------------------------------------------

variable "enable_ecs_deploy" {
  description = "Grant the permissions needed by scripts/ci/ecs-deploy.sh (register task definitions, run one-off tasks, update services)."
  type        = bool
  default     = false
}

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster. Required when enable_ecs_deploy is true."
  type        = string
  default     = null
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster. Required when enable_ecs_deploy is true."
  type        = string
  default     = null
}

variable "task_definition_families" {
  description = "Task definition families the role may run as one-off tasks (database migration)."
  type        = list(string)
  default     = []
}

variable "passable_role_arns" {
  description = "Task and execution role ARNs the deploy role may pass to ECS."
  type        = list(string)
  default     = []
}

variable "log_group_arns" {
  description = "Log groups whose events the role may read (to print migration output in the workflow log)."
  type        = list(string)
  default     = []
}

variable "cloudfront_distribution_arns" {
  description = "CloudFront distributions the role may invalidate after a web deploy."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
