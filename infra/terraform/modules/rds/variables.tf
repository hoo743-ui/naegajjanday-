variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID."
  type        = string
}

variable "subnet_ids" {
  description = "Isolated database subnet IDs (at least two AZs)."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "A DB subnet group needs subnets in at least two availability zones."
  }
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on the PostgreSQL port (ECS services)."
  type        = list(string)
  default     = []
}

variable "engine_version" {
  description = "PostgreSQL version. A major-only value (16) lets RDS pick and auto-upgrade the minor version."
  type        = string
  default     = "16"

  validation {
    condition     = can(regex("^16(\\.[0-9]+)?$", var.engine_version))
    error_message = "engine_version must be PostgreSQL 16 or 16.x (docs/02-erd.md targets PostgreSQL 16 + PostGIS 3.4)."
  }
}

variable "instance_class" {
  description = "Instance class of the primary."
  type        = string
  default     = "db.t4g.small"
}

variable "allocated_storage" {
  description = "Initial gp3 storage in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.allocated_storage >= 20
    error_message = "allocated_storage must be at least 20 GiB."
  }
}

variable "max_allocated_storage" {
  description = "Upper limit for storage autoscaling in GiB."
  type        = number
  default     = 100
}

variable "multi_az" {
  description = "Deploy a synchronous standby in a second AZ."
  type        = bool
  default     = false
}

variable "db_name" {
  description = "Name of the initial database."
  type        = string
  default     = "naegajjanday"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.db_name))
    error_message = "db_name must start with a letter and contain only lowercase letters, digits and underscores."
  }
}

variable "master_username" {
  description = "Master user name. This user holds rds_superuser and is the one that can CREATE EXTENSION postgis."
  type        = string
  default     = "naegajjanday"
}

variable "dsn_scheme" {
  description = "SQLAlchemy URL scheme stored in the secret's url key. apps/api uses asyncpg (DATABASE_URL)."
  type        = string
  default     = "postgresql+asyncpg"
}

variable "dsn_query" {
  description = "Query string appended to the DSN. rds.force_ssl=1 is set, so asyncpg needs ssl=require (psycopg would use sslmode=require)."
  type        = string
  default     = "ssl=require"
}

variable "secret_recovery_window_days" {
  description = "Recovery window of the credentials secret. 0 deletes immediately (handy for staging re-creates)."
  type        = number
  default     = 7

  validation {
    condition     = var.secret_recovery_window_days == 0 || (var.secret_recovery_window_days >= 7 && var.secret_recovery_window_days <= 30)
    error_message = "secret_recovery_window_days must be 0 or between 7 and 30."
  }
}

variable "backup_retention_period" {
  description = "Days automated backups are kept. Must be >= 1 when a read replica is created."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_period >= 1 && var.backup_retention_period <= 35
    error_message = "backup_retention_period must be between 1 and 35 days."
  }
}

variable "backup_window" {
  description = "Daily backup window in UTC. 17:00-18:00 UTC = 02:00-03:00 KST, before the nightly ingestion."
  type        = string
  default     = "17:00-18:00"
}

variable "maintenance_window" {
  description = "Weekly maintenance window in UTC. sun:19:00 UTC = Mon 04:00 KST."
  type        = string
  default     = "sun:19:00-sun:20:00"
}

variable "deletion_protection" {
  description = "Protect the instance from deletion."
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot on destroy (staging only)."
  type        = bool
  default     = false
}

variable "apply_immediately" {
  description = "Apply modifications immediately instead of in the next maintenance window."
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights."
  type        = bool
  default     = true
}

variable "performance_insights_retention_period" {
  description = "Performance Insights retention in days. 7 is free."
  type        = number
  default     = 7

  validation {
    condition     = var.performance_insights_retention_period == 7 || var.performance_insights_retention_period == 731 || (var.performance_insights_retention_period % 31 == 0 && var.performance_insights_retention_period <= 713)
    error_message = "performance_insights_retention_period must be 7, 731 or a multiple of 31 up to 713."
  }
}

variable "monitoring_interval" {
  description = "Enhanced monitoring interval in seconds. 0 disables it."
  type        = number
  default     = 60

  validation {
    condition     = contains([0, 1, 5, 10, 15, 30, 60], var.monitoring_interval)
    error_message = "monitoring_interval must be one of 0, 1, 5, 10, 15, 30, 60."
  }
}

variable "create_read_replica" {
  description = "Create one asynchronous read replica (analytics / admin dashboards)."
  type        = bool
  default     = false
}

variable "replica_instance_class" {
  description = "Instance class of the read replica. null = same as the primary."
  type        = string
  default     = null
}

variable "extra_parameters" {
  description = "Additional DB parameter group entries."
  type = list(object({
    name         = string
    value        = string
    apply_method = optional(string, "pending-reboot")
  }))
  default = []
}

variable "kms_key_arn" {
  description = "KMS key for storage and Performance Insights encryption. null = AWS managed keys."
  type        = string
  default     = null
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
