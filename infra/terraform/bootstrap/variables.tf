variable "aws_region" {
  description = "Region of the state bucket and lock table."
  type        = string
  default     = "ap-northeast-2"
}

variable "project" {
  description = "Project slug, used as the prefix of the bucket and table names."
  type        = string
  default     = "naegajjanday"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,15}$", var.project))
    error_message = "project must be 3-16 lowercase alphanumeric characters."
  }
}
