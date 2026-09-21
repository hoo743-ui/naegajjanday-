###############################################################################
# Identity
###############################################################################

variable "project" {
  description = "Project slug used in resource names and tags."
  type        = string
  default     = "naegajjanday"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,15}$", var.project))
    error_message = "project must be 3-16 lowercase alphanumeric characters."
  }
}

variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be staging or prod."
  }
}

###############################################################################
# DNS
###############################################################################

variable "domain_name" {
  description = "Primary domain of this environment (naegajjanday.com / staging.naegajjanday.com)."
  type        = string

  validation {
    condition     = can(regex("^([a-z0-9-]+\\.)+[a-z]{2,}$", var.domain_name))
    error_message = "domain_name must be a lowercase DNS name."
  }
}

variable "api_subdomain" {
  description = "Label of the API host below domain_name (api -> api.naegajjanday.com, the Base URL in docs/03-api-spec.md)."
  type        = string
  default     = "api"
}

variable "extra_aliases" {
  description = "Additional host names served by CloudFront. Must be exactly one label below domain_name (covered by the wildcard certificate), e.g. www.naegajjanday.com."
  type        = list(string)
  default     = []
}

variable "route53_zone_id" {
  description = "ID of the public Route53 hosted zone that contains domain_name."
  type        = string
}

###############################################################################
# Network
###############################################################################

variable "vpc_cidr" {
  description = "VPC CIDR. Use distinct ranges per environment so the VPCs can be peered later."
  type        = string
}

variable "single_nat_gateway" {
  description = "true = one NAT gateway (staging). false = one per AZ (prod)."
  type        = bool
}

variable "enable_interface_endpoints" {
  description = "Create the ECR / Logs / Secrets Manager interface endpoints."
  type        = bool
  default     = true
}

###############################################################################
# Application
###############################################################################

variable "api_image" {
  description = "Image URI for the api, worker and beat task definitions that Terraform registers. CI registers newer revisions afterwards."
  type        = string
}

variable "web_image" {
  description = "Image URI for the web task definition that Terraform registers."
  type        = string
}

variable "service_sizes" {
  description = "Fargate sizing per service. Required keys: api, worker, beat, web."
  type = map(object({
    cpu       = number
    memory    = number
    min_count = number
    max_count = number
  }))

  validation {
    condition     = alltrue([for k in ["api", "worker", "beat", "web"] : contains(keys(var.service_sizes), k)])
    error_message = "service_sizes must contain the keys api, worker, beat and web."
  }
}

variable "api_command" {
  description = "Command of the API container."
  type        = list(string)
  default     = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
}

variable "celery_app" {
  description = "Celery application path passed to `celery -A`."
  type        = string
  default     = "app.workers.celery_app"
}

variable "worker_concurrency" {
  description = "Celery worker process count per task."
  type        = number
  default     = 2
}

variable "worker_use_spot" {
  description = "Run Celery workers on a FARGATE / FARGATE_SPOT mix. Tasks must be idempotent and use acks_late."
  type        = bool
  default     = true
}

variable "enable_beat" {
  description = "Run an always-on Celery beat service for sub-hourly periodic tasks. Nightly batch ingestion always runs through EventBridge Scheduler (scheduled_tasks)."
  type        = bool
  default     = false
}

variable "enable_execute_command" {
  description = "Enable ECS Exec on the api and worker services."
  type        = bool
  default     = false
}

variable "extra_api_environment" {
  description = "Additional plain environment variables for api / worker / beat (e.g. LLM_PROVIDER, TRAVEL_TIME_PROVIDER)."
  type        = map(string)
  default     = {}
}

variable "extra_web_environment" {
  description = "Additional runtime environment variables for web. NEXT_PUBLIC_* values are baked in at image build time, not here."
  type        = map(string)
  default     = {}
}

variable "app_secret_keys" {
  description = "Keys of the application secret (one Secrets Manager secret holding a JSON object). Each key is injected as an environment variable of the same name and starts as an empty placeholder: set the real value in the console / CLI. Add new keys to the secret BEFORE adding them here, otherwise tasks fail to start."
  type        = list(string)
  default = [
    "KAKAO_CLIENT_ID",
    "KAKAO_CLIENT_SECRET",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "ANTHROPIC_API_KEY",
    "KAKAO_REST_API_KEY",
    "NAVER_SEARCH_CLIENT_ID",
    "NAVER_SEARCH_CLIENT_SECRET",
    "TOURAPI_SERVICE_KEY",
    "DATA_GO_KR_SERVICE_KEY",
  ]
}

variable "generated_secret_keys" {
  description = "Keys of the application secret whose initial value is a random 64 character string instead of an empty placeholder (signing keys must never be empty or guessable)."
  type        = list(string)
  default     = ["JWT_SECRET", "WEBHOOK_SECRET"]
}

variable "scheduled_tasks" {
  description = "Nightly / periodic one-off ECS tasks (EventBridge Scheduler, Asia/Seoul). Commands run in the worker task definition."
  type = map(object({
    schedule_expression = string
    command             = list(string)
    enabled             = optional(bool, true)
    description         = optional(string, "")
  }))
  default = {
    ingest-tourapi = {
      schedule_expression = "cron(0 3 * * ? *)"
      command             = ["python", "-m", "app.cli", "ingest", "--provider", "tourapi", "--all"]
      description         = "Nightly TourAPI ingestion (attractions, festivals, culture) for all active regions"
    }
    ingest-kakao = {
      schedule_expression = "cron(0 4 * * ? *)"
      command             = ["python", "-m", "app.cli", "ingest", "--provider", "kakao", "--all"]
      description         = "Nightly Kakao Local ingestion for all active regions"
    }
    ingest-file = {
      schedule_expression = "cron(0 5 ? * SUN *)"
      command             = ["python", "-m", "app.cli", "ingest", "--provider", "file", "--all"]
      description         = "Weekly re-import of curated seed / admin CSV files"
      enabled             = false
    }
  }
}

###############################################################################
# Data stores
###############################################################################

variable "rds_instance_class" {
  description = "RDS instance class."
  type        = string
}

variable "rds_allocated_storage" {
  description = "Initial RDS storage in GiB."
  type        = number
  default     = 20
}

variable "rds_max_allocated_storage" {
  description = "RDS storage autoscaling limit in GiB."
  type        = number
  default     = 100
}

variable "rds_multi_az" {
  description = "Multi-AZ RDS deployment."
  type        = bool
}

variable "rds_backup_retention_period" {
  description = "Days of automated RDS backups."
  type        = number
  default     = 7
}

variable "rds_create_read_replica" {
  description = "Create an RDS read replica."
  type        = bool
  default     = false
}

variable "rds_replica_instance_class" {
  description = "Instance class of the read replica (null = same as primary)."
  type        = string
  default     = null
}

variable "rds_connections_alarm_threshold" {
  description = "DatabaseConnections alarm threshold (about 80% of max_connections of the instance class)."
  type        = number
  default     = 130
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis nodes (>= 2 enables automatic failover)."
  type        = number
  default     = 1
}

variable "opensearch_instance_type" {
  description = "OpenSearch data node instance type."
  type        = string
}

variable "opensearch_instance_count" {
  description = "Number of OpenSearch data nodes (1 or an even number)."
  type        = number
  default     = 1
}

variable "opensearch_volume_size" {
  description = "OpenSearch gp3 volume size per node in GiB."
  type        = number
  default     = 20
}

variable "opensearch_dedicated_master_count" {
  description = "Dedicated master nodes (0, 3 or 5)."
  type        = number
  default     = 0
}

variable "opensearch_create_service_linked_role" {
  description = "Create the OpenSearch service-linked role (only once per AWS account)."
  type        = bool
  default     = false
}

###############################################################################
# Edge / security
###############################################################################

variable "alb_idle_timeout" {
  description = "ALB idle timeout in seconds (raised for SSE)."
  type        = number
  default     = 300
}

variable "cloudfront_price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_200"
}

variable "waf_rate_limit" {
  description = "Global WAF rate limit per IP per 5 minutes."
  type        = number
  default     = 2000
}

variable "waf_generate_rate_limit" {
  description = "WAF rate limit for POST /v1/courses/generate per IP per 5 minutes."
  type        = number
  default     = 100
}

variable "admin_allowed_ipv4_cidrs" {
  description = "IPv4 CIDRs allowed to reach /admin and /v1/admin (office, VPN). Empty = admin is unreachable."
  type        = list(string)
  default     = []
}

variable "admin_allowed_ipv6_cidrs" {
  description = "IPv6 CIDRs allowed to reach /admin and /v1/admin."
  type        = list(string)
  default     = []
}

variable "protect_from_deletion" {
  description = "Production safety switch: ALB + RDS deletion protection, final RDS snapshot, 30 day secret recovery window, non-destroyable assets bucket."
  type        = bool
}

###############################################################################
# Operations
###############################################################################

variable "log_retention_days" {
  description = "CloudWatch Logs retention for ECS services."
  type        = number
  default     = 30
}

variable "alarm_emails" {
  description = "E-mail recipients of CloudWatch alarms."
  type        = list(string)
  default     = []
}

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to assume the deploy role."
  type        = string
}

variable "github_environment_name" {
  description = "GitHub Environment whose jobs may assume the deploy role (staging / production)."
  type        = string
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider in this stack. Leave false when envs/shared already created it in the same AWS account."
  type        = bool
  default     = false
}

variable "ecr_repository_arns" {
  description = "ECR repositories the deploy role may read (to verify an image exists before deploying)."
  type        = list(string)
  default     = []
}
