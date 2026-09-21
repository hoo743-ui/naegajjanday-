variable "name_prefix" {
  description = "Prefix for all resource names, e.g. naegajjanday-staging."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3-24 chars of lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC. Subnets are carved out as /(prefix+4) blocks, so the prefix must be /20 or larger."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && tonumber(split("/", var.vpc_cidr)[1]) <= 20
    error_message = "vpc_cidr must be a valid IPv4 CIDR with a prefix length of /20 or larger (e.g. 10.20.0.0/16)."
  }
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "single_nat_gateway" {
  description = "true = one shared NAT gateway (cheap, staging). false = one NAT gateway per AZ (HA, prod)."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Create interface VPC endpoints (ECR, CloudWatch Logs, Secrets Manager). The S3 gateway endpoint is always created because it is free."
  type        = bool
  default     = true
}

variable "interface_endpoint_services" {
  description = "Short service names for interface endpoints (com.amazonaws.<region>.<name>)."
  type        = list(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "secretsmanager"]
}

variable "enable_flow_logs" {
  description = "Send VPC flow logs to CloudWatch Logs."
  type        = bool
  default     = true
}

variable "flow_logs_retention_days" {
  description = "Retention of the VPC flow log group."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.flow_logs_retention_days)
    error_message = "flow_logs_retention_days must be a retention value supported by CloudWatch Logs."
  }
}

variable "tags" {
  description = "Extra tags merged onto every resource (common tags come from the provider default_tags)."
  type        = map(string)
  default     = {}
}
