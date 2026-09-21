variable "name_prefix" {
  description = "Prefix for resource names. The replication group id is <name_prefix>-redis (max 40 chars)."
  type        = string

  validation {
    condition     = length(var.name_prefix) <= 34
    error_message = "name_prefix must be 34 characters or fewer."
  }
}

variable "vpc_id" {
  description = "VPC ID."
  type        = string
}

variable "subnet_ids" {
  description = "Isolated subnet IDs for the cache subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on the Redis port."
  type        = list(string)
  default     = []
}

variable "engine_version" {
  description = "Redis OSS engine version (7.x)."
  type        = string
  default     = "7.1"

  validation {
    condition     = can(regex("^7\\.[0-9]+$", var.engine_version))
    error_message = "engine_version must be a Redis 7.x version such as 7.1."
  }
}

variable "node_type" {
  description = "Cache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "num_cache_clusters" {
  description = "Number of nodes (1 primary + N-1 replicas). >= 2 enables automatic failover and Multi-AZ."
  type        = number
  default     = 1

  validation {
    condition     = var.num_cache_clusters >= 1 && var.num_cache_clusters <= 6
    error_message = "num_cache_clusters must be between 1 and 6."
  }
}

variable "maxmemory_policy" {
  description = "Eviction policy. volatile-lru only evicts keys with a TTL (cache, rate limit, idempotency keys) and never Celery broker messages, which share this Redis."
  type        = string
  default     = "volatile-lru"

  validation {
    condition     = contains(["volatile-lru", "volatile-lfu", "volatile-ttl", "volatile-random", "allkeys-lru", "allkeys-lfu", "allkeys-random", "noeviction"], var.maxmemory_policy)
    error_message = "maxmemory_policy must be a valid Redis eviction policy."
  }
}

variable "transit_encryption_enabled" {
  description = "Enable TLS in transit. Clients must then use rediss:// URLs."
  type        = bool
  default     = true
}

variable "snapshot_retention_limit" {
  description = "Days to keep daily snapshots. 0 disables snapshots."
  type        = number
  default     = 1
}

variable "snapshot_window" {
  description = "Daily snapshot window in UTC."
  type        = string
  default     = "18:00-19:00"
}

variable "maintenance_window" {
  description = "Weekly maintenance window in UTC."
  type        = string
  default     = "sun:20:00-sun:21:00"
}

variable "apply_immediately" {
  description = "Apply modifications immediately instead of in the next maintenance window."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
