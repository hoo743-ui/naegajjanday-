variable "name_prefix" {
  description = "Prefix for resource names. Also the OpenSearch domain name (3-28 chars, lowercase)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,27}$", var.name_prefix))
    error_message = "name_prefix must be 3-28 chars of lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "vpc_id" {
  description = "VPC ID."
  type        = string
}

variable "subnet_ids" {
  description = "Isolated subnet IDs. Only the first one is used unless zone awareness is on (instance_count >= 2)."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to reach the domain on 443."
  type        = list(string)
  default     = []
}

variable "engine_version" {
  description = "OpenSearch engine version."
  type        = string
  default     = "OpenSearch_2.17"

  validation {
    condition     = can(regex("^OpenSearch_[0-9]+\\.[0-9]+$", var.engine_version))
    error_message = "engine_version must look like OpenSearch_2.17."
  }
}

variable "instance_type" {
  description = "Data node instance type."
  type        = string
  default     = "t3.small.search"
}

variable "instance_count" {
  description = "Number of data nodes. An even number >= 2 enables 2-AZ zone awareness."
  type        = number
  default     = 1

  validation {
    condition     = var.instance_count == 1 || var.instance_count % 2 == 0
    error_message = "instance_count must be 1 or an even number (2-AZ zone awareness)."
  }
}

variable "dedicated_master_count" {
  description = "Number of dedicated master nodes (0 disables, 3 recommended for production)."
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 3, 5], var.dedicated_master_count)
    error_message = "dedicated_master_count must be 0, 3 or 5."
  }
}

variable "dedicated_master_type" {
  description = "Instance type of the dedicated master nodes."
  type        = string
  default     = "m6g.large.search"
}

variable "ebs_volume_size" {
  description = "gp3 volume size per data node in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.ebs_volume_size >= 10
    error_message = "ebs_volume_size must be at least 10 GiB."
  }
}

variable "master_user_name" {
  description = "Internal user database master user (fine-grained access control)."
  type        = string
  default     = "naegajjanday"
}

variable "secret_recovery_window_days" {
  description = "Recovery window of the credentials secret. 0 deletes immediately."
  type        = number
  default     = 7
}

variable "create_service_linked_role" {
  description = "Create the AWSServiceRoleForAmazonOpenSearchService role. It exists once per account: true for the first VPC domain in the account, false afterwards."
  type        = bool
  default     = false
}

variable "nori_user_dictionary" {
  description = "Optional custom nori user dictionary (TXT-DICTIONARY package). Object with the S3 bucket and key of the dictionary file. null = no package."
  type = object({
    s3_bucket = string
    s3_key    = string
  })
  default = null
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
