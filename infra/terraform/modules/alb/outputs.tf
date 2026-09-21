output "alb_arn" {
  description = "ARN of the load balancer."
  value       = aws_lb.this.arn
}

output "alb_arn_suffix" {
  description = "ARN suffix of the load balancer (CloudWatch dimension)."
  value       = aws_lb.this.arn_suffix
}

output "alb_dns_name" {
  description = "DNS name of the load balancer."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Route53 zone ID of the load balancer."
  value       = aws_lb.this.zone_id
}

output "security_group_id" {
  description = "Security group of the load balancer. Services allow ingress from it."
  value       = aws_security_group.this.id
}

output "https_listener_arn" {
  description = "ARN of the HTTPS listener."
  value       = aws_lb_listener.https.arn
}

output "certificate_arn" {
  description = "ARN of the regional certificate attached to the listener."
  value       = local.certificate_arn
}

output "origin_domain_name" {
  description = "DNS name CloudFront should use as its origin (covered by the ALB certificate)."
  value       = aws_route53_record.origin.fqdn
}

output "api_target_group_arn" {
  description = "ARN of the API target group."
  value       = aws_lb_target_group.api.arn

  # An ECS service can only register with a target group that is already
  # attached to a listener; make consumers wait for the rules.
  depends_on = [aws_lb_listener_rule.api_paths, aws_lb_listener_rule.api_hosts]
}

output "web_target_group_arn" {
  description = "ARN of the web target group."
  value       = aws_lb_target_group.web.arn

  # An ECS service can only register with a target group that is already
  # attached to a listener; make consumers wait for the rules.
  depends_on = [aws_lb_listener.https, aws_lb_listener_rule.web_verified]
}

output "api_target_group_arn_suffix" {
  description = "ARN suffix of the API target group (CloudWatch dimension)."
  value       = aws_lb_target_group.api.arn_suffix
}

output "web_target_group_arn_suffix" {
  description = "ARN suffix of the web target group (CloudWatch dimension)."
  value       = aws_lb_target_group.web.arn_suffix
}

output "api_resource_label" {
  description = "Resource label for ALBRequestCountPerTarget autoscaling of the API."
  value       = "${aws_lb.this.arn_suffix}/${aws_lb_target_group.api.arn_suffix}"
}

output "web_resource_label" {
  description = "Resource label for ALBRequestCountPerTarget autoscaling of the web service."
  value       = "${aws_lb.this.arn_suffix}/${aws_lb_target_group.web.arn_suffix}"
}
