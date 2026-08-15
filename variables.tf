variable "region" {
  description = "AWS region in which to provision the bucket."
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "resource_name" {
  description = "Logical resource name used to construct the S3 bucket name."
  type        = string
}

variable "owner" {
  description = "Owning engineering team."
  type        = string
}

variable "tags" {
  description = "Additional tags for cost allocation and operations."
  type        = map(string)
  default     = {}
}

variable "versioning_enabled" {
  description = "Whether S3 versioning is enabled."
  type        = bool
  default     = true
}

variable "noncurrent_version_expiration_days" {
  description = "Retention period for noncurrent object versions."
  type        = number
  default     = 90
}

variable "encryption_algorithm" {
  description = "S3 server-side encryption algorithm."
  type        = string
  default     = "AES256"
}

variable "kms_key_arn" {
  description = "Optional customer-managed KMS key ARN."
  type        = string
  default     = null
}
