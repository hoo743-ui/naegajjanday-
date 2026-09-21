variable "name_prefix" {
  description = "Prefix for resource names, e.g. naegajjanday-staging."
  type        = string
}

variable "service_name" {
  description = "Short service name (api, worker, beat, web). Also used as the container name and the task definition family suffix."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.service_name))
    error_message = "service_name must be 2-16 chars of lowercase letters, digits and hyphens."
  }
}

variable "cluster_arn" {
  description = "ARN of the ECS cluster."
  type        = string
}

variable "cluster_name" {
  description = "Name of the ECS cluster (used for the autoscaling resource id)."
  type        = string
}

variable "vpc_id" {
  description = "VPC the service security group is created in."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs the tasks run in."
  type        = list(string)
}

# ----------------------------------------------------------------------------
# Container
# ----------------------------------------------------------------------------

variable "container_image" {
  description = "Image URI used for the Terraform-managed task definition revision. CI registers newer revisions; the service ignores task_definition drift."
  type        = string
}

variable "container_port" {
  description = "Port the container listens on. null for workers without inbound traffic."
  type        = number
  default     = null
}

variable "command" {
  description = "Container command override. null keeps the image CMD."
  type        = list(string)
  default     = null
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512

  validation {
    condition     = contains([256, 512, 1024, 2048, 4096, 8192, 16384], var.cpu)
    error_message = "cpu must be a valid Fargate CPU value (256, 512, 1024, 2048, 4096, 8192, 16384)."
  }
}

variable "memory" {
  description = "Fargate task memory in MiB. Must be a valid combination with cpu."
  type        = number
  default     = 1024

  validation {
    condition     = var.memory >= 512 && var.memory <= 122880
    error_message = "memory must be between 512 and 122880 MiB."
  }
}

variable "cpu_architecture" {
  description = "X86_64 or ARM64. Must match the architecture the image is built for."
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be X86_64 or ARM64."
  }
}

variable "environment" {
  description = "Plain environment variables."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secrets Manager injection. Map of ENV_NAME => { arn, key }. key selects a JSON key inside the secret; null injects the whole secret string."
  type = map(object({
    arn = string
    key = optional(string)
  }))
  default = {}
}

variable "health_check_command" {
  description = "Container health check as a CMD-SHELL string. null disables the container health check."
  type        = string
  default     = null
}

variable "stop_timeout" {
  description = "Seconds ECS waits between SIGTERM and SIGKILL (max 120 on Fargate). Use 120 for Celery workers so in-flight tasks can finish."
  type        = number
  default     = 30

  validation {
    condition     = var.stop_timeout >= 2 && var.stop_timeout <= 120
    error_message = "stop_timeout must be between 2 and 120 seconds."
  }
}

variable "ephemeral_storage_gib" {
  description = "Ephemeral storage in GiB (21-200). null keeps the 20 GiB default."
  type        = number
  default     = null
}

# ----------------------------------------------------------------------------
# Service / deployment
# ----------------------------------------------------------------------------

variable "desired_count" {
  description = "Initial desired task count (afterwards owned by autoscaling / CI)."
  type        = number
  default     = 1
}

variable "deployment_minimum_healthy_percent" {
  description = "Lower bound of healthy tasks during a rolling deployment. Use 0 for singletons (celery beat)."
  type        = number
  default     = 100
}

variable "deployment_maximum_percent" {
  description = "Upper bound of tasks during a rolling deployment. Use 100 for singletons (celery beat)."
  type        = number
  default     = 200
}

variable "enable_execute_command" {
  description = "Enable ECS Exec (SSM session into a running task)."
  type        = bool
  default     = false
}

variable "use_fargate_spot" {
  description = "Run on a FARGATE + FARGATE_SPOT capacity provider mix. Intended for interruptible workers, not for the API."
  type        = bool
  default     = false
}

variable "on_demand_base" {
  description = "Number of tasks always placed on on-demand FARGATE when use_fargate_spot is true."
  type        = number
  default     = 1
}

variable "on_demand_weight" {
  description = "Relative weight of on-demand FARGATE above the base when use_fargate_spot is true."
  type        = number
  default     = 1
}

variable "spot_weight" {
  description = "Relative weight of FARGATE_SPOT above the base when use_fargate_spot is true."
  type        = number
  default     = 3
}

# ----------------------------------------------------------------------------
# Load balancer
# ----------------------------------------------------------------------------

variable "attach_load_balancer" {
  description = "Register tasks in target_group_arn. A plain bool (instead of a null check) keeps count known at plan time."
  type        = bool
  default     = false
}

variable "target_group_arn" {
  description = "Target group ARN. Required when attach_load_balancer is true."
  type        = string
  default     = null
}

variable "health_check_grace_period_seconds" {
  description = "Seconds the scheduler ignores ALB health checks after task start."
  type        = number
  default     = 60
}

variable "ingress_security_group_ids" {
  description = "Security groups allowed to reach container_port (normally the ALB security group)."
  type        = list(string)
  default     = []
}

# ----------------------------------------------------------------------------
# Autoscaling
# ----------------------------------------------------------------------------

variable "enable_autoscaling" {
  description = "Create an Application Auto Scaling target and policies."
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum task count."
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum task count."
  type        = number
  default     = 4

  validation {
    condition     = var.max_capacity >= 1
    error_message = "max_capacity must be at least 1."
  }
}

variable "cpu_target_percent" {
  description = "Target average CPU utilisation for target tracking."
  type        = number
  default     = 60

  validation {
    condition     = var.cpu_target_percent > 0 && var.cpu_target_percent <= 100
    error_message = "cpu_target_percent must be within (0, 100]."
  }
}

variable "enable_request_count_scaling" {
  description = "Add an ALBRequestCountPerTarget target tracking policy. Requires alb_resource_label."
  type        = bool
  default     = false
}

variable "alb_resource_label" {
  description = "<alb-arn-suffix>/<target-group-arn-suffix>, required when enable_request_count_scaling is true."
  type        = string
  default     = null
}

variable "request_count_target" {
  description = "Target requests per task per minute."
  type        = number
  default     = 600
}

variable "scale_in_cooldown" {
  description = "Seconds to wait after a scale-in before another one."
  type        = number
  default     = 300
}

variable "scale_out_cooldown" {
  description = "Seconds to wait after a scale-out before another one."
  type        = number
  default     = 60
}

# ----------------------------------------------------------------------------
# IAM / logging
# ----------------------------------------------------------------------------

variable "attach_task_role_policy" {
  description = "Attach task_role_policy_json to the task role. A plain bool keeps count known at plan time."
  type        = bool
  default     = false
}

variable "task_role_policy_json" {
  description = "IAM policy JSON granting the application its AWS permissions (S3 assets, etc.)."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the service log group."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
