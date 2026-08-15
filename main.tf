provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Application = "internal-platform-storage"
      Repository  = "principal-devops-assessment"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "${var.resource_name}-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

module "storage" {
  source = "../../modules/s3-storage"

  bucket_name                        = local.bucket_name
  environment                        = var.environment
  owner                              = var.owner
  tags                               = var.tags
  versioning_enabled                 = var.versioning_enabled
  noncurrent_version_expiration_days = var.noncurrent_version_expiration_days
  encryption_algorithm               = var.encryption_algorithm
  kms_key_arn                        = var.kms_key_arn
}
