variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "cluster_arn" {
  description = "ARN of the ECS cluster the one-off tasks run in."
  type        = string
}

variable "task_definition_family" {
  description = "Task definition family to run (normally the worker family). The schedule targets the family without a revision so every run uses the latest ACTIVE revision that CI registered."
  type        = string
}

variable "container_name" {
  description = "Container whose command is overridden."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the tasks."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups for the tasks (normally the worker security group, which already has data store access)."
  type        = list(string)
}

variable "passable_role_arns" {
  description = "Task role and execution role ARNs of the task definition."
  type        = list(string)
}

variable "timezone" {
  description = "IANA time zone the cron expressions are evaluated in."
  type        = string
  default     = "Asia/Seoul"
}

variable "schedules" {
  description = "Map of schedule name => { schedule_expression, command, enabled, description }."
  type = map(object({
    schedule_expression = string
    command             = list(string)
    enabled             = optional(bool, true)
    description         = optional(string, "")
  }))

  validation {
    condition     = alltrue([for s in values(var.schedules) : can(regex("^(cron|rate|at)\\(.+\\)$", s.schedule_expression))])
    error_message = "schedule_expression must be a cron(...), rate(...) or at(...) expression."
  }

  validation {
    condition     = alltrue([for s in values(var.schedules) : length(s.command) > 0])
    error_message = "Every schedule needs a non-empty command."
  }
}

variable "maximum_retry_attempts" {
  description = "How often EventBridge Scheduler retries a failed RunTask call (not a failed task)."
  type        = number
  default     = 2
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
