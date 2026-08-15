output "bucket_id" {
  description = "Provisioned bucket ID."
  value       = module.storage.bucket_id
}

output "bucket_arn" {
  description = "Provisioned bucket ARN."
  value       = module.storage.bucket_arn
}
