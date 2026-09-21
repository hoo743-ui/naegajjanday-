variable "namespace" {
  description = "Repository namespace (prefix before the slash), e.g. naegajjanday."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.namespace))
    error_message = "namespace must be lowercase letters, digits and hyphens."
  }
}

variable "repository_names" {
  description = "Repository names below the namespace. The api image is shared by the api, worker and beat services."
  type        = list(string)
  default     = ["api", "web"]
}

variable "keep_last_images" {
  description = "Number of images kept per repository. Must comfortably exceed the number of deploys you may want to roll back."
  type        = number
  default     = 50

  validation {
    condition     = var.keep_last_images >= 5
    error_message = "keep_last_images must be at least 5."
  }
}

variable "untagged_expiry_days" {
  description = "Days after which untagged images expire."
  type        = number
  default     = 7
}

variable "force_delete" {
  description = "Allow deleting repositories that still contain images."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
