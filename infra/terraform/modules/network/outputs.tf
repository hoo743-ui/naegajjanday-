output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "availability_zones" {
  description = "Availability zones used by the subnets."
  value       = local.azs
}

output "public_subnet_ids" {
  description = "Public subnet IDs (ALB, NAT)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (ECS tasks)."
  value       = aws_subnet.private[*].id
}

output "database_subnet_ids" {
  description = "Isolated subnet IDs (RDS, ElastiCache, OpenSearch)."
  value       = aws_subnet.database[*].id
}

output "nat_gateway_public_ips" {
  description = "Elastic IPs of the NAT gateways. Give these to third-party APIs that require an egress IP allowlist."
  value       = aws_eip.nat[*].public_ip
}

output "s3_gateway_endpoint_id" {
  description = "ID of the S3 gateway endpoint."
  value       = aws_vpc_endpoint.s3.id
}
