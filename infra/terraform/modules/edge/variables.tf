variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "domain_name" {
  description = "Primary domain (e.g. naegajjanday.com or staging.naegajjanday.com). The CloudFront certificate covers it plus *.domain_name."
  type        = string
}

variable "aliases" {
  description = "All host names served by the distribution (must be domain_name or one level below it). A and AAAA records are created for each."
  type        = list(string)

  validation {
    condition     = length(var.aliases) >= 1
    error_message = "At least one alias is required."
  }
}

variable "route53_zone_id" {
  description = "Public hosted zone for the alias records and ACM validation."
  type        = string
}

variable "create_certificate_validation_records" {
  description = "Create the ACM DNS validation records. Set false when another module (alb) already manages the identical records for the same names."
  type        = bool
  default     = true
}

variable "origin_domain_name" {
  description = "DNS name of the ALB origin (must be covered by the ALB certificate)."
  type        = string
}

variable "origin_verify_enabled" {
  description = "Send the shared secret header to the ALB origin."
  type        = bool
  default     = true
}

variable "origin_verify_header_name" {
  description = "Name of the shared secret header."
  type        = string
  default     = "X-Origin-Verify"
}

variable "origin_verify_header_value" {
  description = "Value of the shared secret header."
  type        = string
  default     = null
  sensitive   = true
}

variable "origin_read_timeout" {
  description = "Seconds CloudFront waits for the next packet from the origin. SSE endpoints must emit a heartbeat comment more often than this (recommended every 15s). Values above 60 need a CloudFront quota increase."
  type        = number
  default     = 60

  validation {
    condition     = var.origin_read_timeout >= 1 && var.origin_read_timeout <= 180
    error_message = "origin_read_timeout must be between 1 and 180 seconds."
  }
}

variable "api_path_pattern" {
  description = "Path pattern of the API behaviour (never cached, never compressed so SSE is not buffered)."
  type        = string
  default     = "/v1/*"
}

variable "assets_path_pattern" {
  description = "Path pattern served from the S3 assets bucket. Objects must be stored under the same prefix (assets/...)."
  type        = string
  default     = "/assets/*"
}

variable "assets_cors_allowed_origins" {
  description = "Origins allowed to PUT to the assets bucket with presigned URLs (POST /v1/admin/uploads/presign)."
  type        = list(string)
  default     = []
}

variable "price_class" {
  description = "CloudFront price class. PriceClass_200 includes the Seoul edge locations."
  type        = string
  default     = "PriceClass_200"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200 or PriceClass_All."
  }
}

# ----------------------------------------------------------------------------
# WAF
# ----------------------------------------------------------------------------

variable "waf_rate_limit" {
  description = "Requests per 5 minutes per IP before the generic rate-based rule blocks. The API spec allows 300 reads/minute = 1500 / 5 min; fine-grained quotas are enforced in the API with Redis."
  type        = number
  default     = 2000

  validation {
    condition     = var.waf_rate_limit >= 100
    error_message = "waf_rate_limit must be at least 100."
  }
}

variable "waf_generate_rate_limit" {
  description = "POST /v1/courses/generate requests per 5 minutes per IP. Coarse outer guard for the expensive optimiser endpoint (the API enforces 10/h anonymous, 60/h logged-in)."
  type        = number
  default     = 100

  validation {
    condition     = var.waf_generate_rate_limit >= 10
    error_message = "waf_generate_rate_limit must be at least 10 (WAF minimum)."
  }
}

variable "admin_allowed_ipv4_cidrs" {
  description = "IPv4 CIDRs allowed to reach /admin and /v1/admin. Empty list = nobody (secure default)."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for c in var.admin_allowed_ipv4_cidrs : can(cidrhost(c, 0)) && !strcontains(c, ":")])
    error_message = "admin_allowed_ipv4_cidrs must contain valid IPv4 CIDR blocks such as 203.0.113.10/32."
  }
}

variable "admin_allowed_ipv6_cidrs" {
  description = "IPv6 CIDRs allowed to reach /admin and /v1/admin."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for c in var.admin_allowed_ipv6_cidrs : can(cidrhost(c, 0)) && strcontains(c, ":")])
    error_message = "admin_allowed_ipv6_cidrs must contain valid IPv6 CIDR blocks."
  }
}

variable "admin_path_prefixes" {
  description = "Lower-case URI prefixes protected by the admin IP allowlist."
  type        = list(string)
  default     = ["/admin", "/v1/admin"]

  validation {
    condition     = length(var.admin_path_prefixes) >= 2
    error_message = "At least two prefixes are required (a WAF OR statement needs two or more nested statements)."
  }
}

variable "enable_waf_logging" {
  description = "Send WAF logs to a CloudWatch log group in us-east-1."
  type        = bool
  default     = true
}

variable "waf_log_retention_days" {
  description = "Retention of the WAF log group."
  type        = number
  default     = 30
}

variable "force_destroy_assets_bucket" {
  description = "Allow destroying the assets bucket while it still contains objects (staging only)."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
