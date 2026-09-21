variable "name_prefix" {
  description = "Prefix for resource names. ALB and target group names are limited to 32 chars, so keep this <= 24."
  type        = string

  validation {
    condition     = length(var.name_prefix) <= 24
    error_message = "name_prefix must be 24 characters or fewer (ALB / target group name limit is 32)."
  }
}

variable "vpc_id" {
  description = "VPC ID."
  type        = string
}

variable "vpc_cidr_block" {
  description = "VPC CIDR. ALB egress is limited to it."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the ALB (at least two AZs)."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 2
    error_message = "An ALB needs subnets in at least two availability zones."
  }
}

variable "domain_name" {
  description = "Primary domain served by this environment (e.g. staging.naegajjanday.com). The certificate covers it plus *.domain_name."
  type        = string
}

variable "route53_zone_id" {
  description = "Public hosted zone used for ACM DNS validation and the origin record."
  type        = string
}

variable "certificate_arn" {
  description = "Existing regional ACM certificate ARN. null = create and DNS-validate one for domain_name and *.domain_name."
  type        = string
  default     = null
}

variable "origin_subdomain" {
  description = "Label of the record that points at the ALB (origin.<domain_name>). CloudFront uses it as the origin host so TLS validation succeeds."
  type        = string
  default     = "origin"
}

variable "idle_timeout" {
  description = "ALB idle timeout in seconds. Raised from the 60s default so SSE streams (/v1/courses/{id}/narrative, chat) are not cut between tokens."
  type        = number
  default     = 300

  validation {
    condition     = var.idle_timeout >= 60 && var.idle_timeout <= 4000
    error_message = "idle_timeout must be between 60 and 4000 seconds."
  }
}

variable "restrict_to_cloudfront" {
  description = "Only accept traffic from the CloudFront origin-facing managed prefix list. Set false to expose the ALB directly (no CDN)."
  type        = bool
  default     = true
}

variable "origin_verify_enabled" {
  description = "Require a shared secret header (added by CloudFront) on every forwarded request, so other CloudFront distributions cannot bypass the WAF."
  type        = bool
  default     = true
}

variable "origin_verify_header_name" {
  description = "Name of the shared secret header."
  type        = string
  default     = "X-Origin-Verify"
}

variable "origin_verify_header_value" {
  description = "Value of the shared secret header. Required when origin_verify_enabled is true."
  type        = string
  default     = null
  sensitive   = true
}

variable "api_port" {
  description = "Container port of the API service."
  type        = number
  default     = 8000
}

variable "web_port" {
  description = "Container port of the web service."
  type        = number
  default     = 3000
}

variable "api_health_check_path" {
  description = "ALB health check path for the API (docs/03-api-spec.md: /readyz checks DB, Redis, ES)."
  type        = string
  default     = "/readyz"
}

variable "web_health_check_path" {
  description = "ALB health check path for the web service (any 2xx/3xx counts as healthy). Point it at a cheap route handler once the web app has one."
  type        = string
  default     = "/"
}

variable "api_path_patterns" {
  description = "Path patterns routed to the API target group. Everything else goes to web."
  type        = list(string)
  default     = ["/v1/*", "/healthz", "/readyz"]

  validation {
    condition     = length(var.api_path_patterns) >= 1 && length(var.api_path_patterns) <= 4
    error_message = "Between 1 and 4 API path patterns are supported (ALB allows 5 condition values per rule, one is reserved for the origin header)."
  }
}

variable "api_host_names" {
  description = "Host names that route entirely to the API (e.g. api.naegajjanday.com). Empty list disables host-based routing."
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.api_host_names) <= 4
    error_message = "At most 4 API host names are supported."
  }
}

variable "blocked_path_patterns" {
  description = "Paths answered with 404 at the ALB. /metrics is internal-only per the API spec."
  type        = list(string)
  default     = ["/metrics", "/metrics/*"]

  validation {
    condition     = length(var.blocked_path_patterns) >= 1 && length(var.blocked_path_patterns) <= 5
    error_message = "Between 1 and 5 blocked path patterns are supported."
  }
}

variable "deregistration_delay" {
  description = "Seconds the ALB keeps draining a deregistering target. Should cover a typical SSE stream."
  type        = number
  default     = 60
}

variable "ssl_policy" {
  description = "TLS security policy of the HTTPS listener."
  type        = string
  default     = "ELBSecurityPolicy-TLS13-1-2-2021-06"
}

variable "enable_deletion_protection" {
  description = "Protect the ALB from accidental deletion."
  type        = bool
  default     = false
}

variable "access_logs_bucket" {
  description = "S3 bucket for ALB access logs. null disables access logging. The bucket policy must allow the regional ELB log delivery account."
  type        = string
  default     = null
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
