variable "aws_region" {
  description = "AWS region of the environment."
  type        = string
  default     = "ap-northeast-2"
}

variable "project" {
  description = "Project slug."
  type        = string
  default     = "naegajjanday"
}

variable "domain_name" {
  description = "Domain of this environment, e.g. naegajjanday.com. The API is served on api.<domain_name> and on <domain_name>/v1."
  type        = string
}

variable "route53_zone_id" {
  description = "ID of the public hosted zone that contains domain_name."
  type        = string

  validation {
    condition     = can(regex("^Z[A-Z0-9]+$", var.route53_zone_id))
    error_message = "route53_zone_id must look like Z0123456789ABCDEFGHIJ."
  }
}

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to deploy."
  type        = string
}

variable "api_image_tag" {
  description = "Tag of the api image used for the Terraform-registered task definitions. CI deploys newer tags afterwards; only matters for the very first apply."
  type        = string
  default     = "bootstrap"
}

variable "web_image_tag" {
  description = "Tag of the web image used for the Terraform-registered task definition."
  type        = string
  default     = "bootstrap"
}

variable "admin_allowed_ipv4_cidrs" {
  description = "IPv4 CIDRs allowed to reach /admin and /v1/admin through the WAF."
  type        = list(string)
  default     = []
}

variable "admin_allowed_ipv6_cidrs" {
  description = "IPv6 CIDRs allowed to reach /admin and /v1/admin through the WAF."
  type        = list(string)
  default     = []
}

variable "alarm_emails" {
  description = "E-mail recipients of CloudWatch alarms."
  type        = list(string)
  default     = []
}

variable "extra_api_environment" {
  description = "Additional plain environment variables for api / worker (LLM_PROVIDER, TRAVEL_TIME_PROVIDER, ...)."
  type        = map(string)
  default     = {}
}

variable "opensearch_create_service_linked_role" {
  description = "true only for the first VPC OpenSearch domain in the AWS account. Staging normally created it already."
  type        = bool
  default     = false
}

variable "extra_aliases" {
  description = "Additional host names one label below domain_name, e.g. www.naegajjanday.com."
  type        = list(string)
  default     = []
}
