variable "name_prefix" {
  description = "Prefix for alarm, topic and dashboard names."
  type        = string
}

variable "alarm_emails" {
  description = "E-mail addresses subscribed to the alarm SNS topic (each must confirm the subscription)."
  type        = list(string)
  default     = []
}

variable "alb_arn_suffix" {
  description = "ARN suffix of the ALB (LoadBalancer dimension)."
  type        = string
}

variable "target_groups" {
  description = "Map of logical name => { arn_suffix, p95_latency_threshold_seconds }. Keys must be static (api, web)."
  type = map(object({
    arn_suffix                    = string
    p95_latency_threshold_seconds = number
  }))
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  type        = string
}

variable "ecs_services" {
  description = "Map of logical name => ECS service name. Keys must be static."
  type        = map(string)
}

variable "rds_instance_id" {
  description = "DBInstanceIdentifier of the primary instance."
  type        = string
}

variable "rds_max_connections_threshold" {
  description = "DatabaseConnections alarm threshold. Rule of thumb: 80% of max_connections (db.t4g.small ~ 170, db.m6g.large ~ 850)."
  type        = number
  default     = 130
}

variable "rds_free_storage_threshold_gib" {
  description = "FreeStorageSpace alarm threshold in GiB."
  type        = number
  default     = 5
}

variable "redis_cluster_ids" {
  description = "ElastiCache member cluster ids (CacheClusterId dimension). Must be known at plan time."
  type        = list(string)
  default     = []
}

variable "enable_opensearch_alarms" {
  description = "Create OpenSearch cluster status / storage alarms."
  type        = bool
  default     = false
}

variable "opensearch_domain_name" {
  description = "OpenSearch domain name. Required when enable_opensearch_alarms is true."
  type        = string
  default     = null
}

variable "cpu_alarm_threshold" {
  description = "CPU utilisation (%) threshold shared by the ECS and RDS alarms."
  type        = number
  default     = 80

  validation {
    condition     = var.cpu_alarm_threshold > 0 && var.cpu_alarm_threshold <= 100
    error_message = "cpu_alarm_threshold must be within (0, 100]."
  }
}

variable "memory_alarm_threshold" {
  description = "Memory utilisation (%) threshold of the ECS alarms."
  type        = number
  default     = 85

  validation {
    condition     = var.memory_alarm_threshold > 0 && var.memory_alarm_threshold <= 100
    error_message = "memory_alarm_threshold must be within (0, 100]."
  }
}

variable "alb_5xx_threshold" {
  description = "Number of 5xx responses within 5 minutes that triggers the alarm."
  type        = number
  default     = 25
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
