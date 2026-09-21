output "distribution_id" {
  description = "ID of the CloudFront distribution (used for cache invalidations)."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "ARN of the CloudFront distribution."
  value       = aws_cloudfront_distribution.this.arn
}

output "distribution_domain_name" {
  description = "cloudfront.net domain name of the distribution."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "assets_bucket_name" {
  description = "Name of the private assets bucket."
  value       = aws_s3_bucket.assets.bucket
}

output "assets_bucket_arn" {
  description = "ARN of the private assets bucket."
  value       = aws_s3_bucket.assets.arn
}

output "web_acl_arn" {
  description = "ARN of the WAFv2 web ACL."
  value       = aws_wafv2_web_acl.this.arn
}

output "admin_ipv4_ip_set_arn" {
  description = "ARN of the admin IPv4 allowlist IP set."
  value       = aws_wafv2_ip_set.admin_ipv4.arn
}
