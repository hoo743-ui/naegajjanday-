###############################################################################
# Application Load Balancer
#   - HTTPS only, ACM certificate (DNS validated)
#   - idle timeout raised for SSE
#   - path routing: /v1/*, /healthz, /readyz -> api ; everything else -> web
#   - optional CloudFront-only lock down (prefix list + shared secret header)
###############################################################################

locals {
  create_certificate = var.certificate_arn == null
  certificate_arn    = local.create_certificate ? aws_acm_certificate_validation.this[0].certificate_arn : var.certificate_arn
  origin_domain_name = "${var.origin_subdomain}.${var.domain_name}"
}

# ----------------------------------------------------------------------------
# Certificate (regional, for the ALB listener)
# ----------------------------------------------------------------------------

resource "aws_acm_certificate" "this" {
  count = local.create_certificate ? 1 : 0

  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = local.create_certificate ? {
    for dvo in aws_acm_certificate.this[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]

  # The apex and the wildcard share one validation record.
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count = local.create_certificate ? 1 : 0

  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [for r in aws_route53_record.certificate_validation : r.fqdn]
}

# ----------------------------------------------------------------------------
# Security group
# ----------------------------------------------------------------------------

data "aws_ec2_managed_prefix_list" "cloudfront" {
  count = var.restrict_to_cloudfront ? 1 : 0

  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "this" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Public ALB of ${var.name_prefix}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

# NOTE: the CloudFront prefix list counts as ~55 rules against the default
# quota of 60 rules per security group, so only 443 is opened in that mode.
resource "aws_vpc_security_group_ingress_rule" "https_cloudfront" {
  count = var.restrict_to_cloudfront ? 1 : 0

  security_group_id = aws_security_group.this.id
  description       = "HTTPS from CloudFront origin-facing ranges"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront[0].id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "https_public" {
  count = var.restrict_to_cloudfront ? 0 : 1

  security_group_id = aws_security_group.this.id
  description       = "HTTPS from the internet"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "http_public" {
  count = var.restrict_to_cloudfront ? 0 : 1

  security_group_id = aws_security_group.this.id
  description       = "HTTP from the internet (redirected to HTTPS)"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "to_vpc" {
  security_group_id = aws_security_group.this.id
  description       = "To targets inside the VPC"
  cidr_ipv4         = var.vpc_cidr_block
  ip_protocol       = "-1"
}

# ----------------------------------------------------------------------------
# Load balancer
# ----------------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  internal           = false
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.this.id]

  idle_timeout               = var.idle_timeout
  drop_invalid_header_fields = true
  enable_deletion_protection = var.enable_deletion_protection

  dynamic "access_logs" {
    for_each = var.access_logs_bucket == null ? [] : [var.access_logs_bucket]

    content {
      bucket  = access_logs.value
      prefix  = "alb/${var.name_prefix}"
      enabled = true
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

resource "aws_route53_record" "origin" {
  zone_id = var.route53_zone_id
  name    = local.origin_domain_name
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

# ----------------------------------------------------------------------------
# Target groups (Fargate awsvpc -> target_type ip)
# ----------------------------------------------------------------------------

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  vpc_id      = var.vpc_id
  port        = var.api_port
  protocol    = "HTTP"
  target_type = "ip"

  deregistration_delay = var.deregistration_delay

  # SSE keeps connections open for a long time; least outstanding requests
  # spreads those better than round robin.
  load_balancing_algorithm_type = "least_outstanding_requests"

  health_check {
    path                = var.api_health_check_path
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-api" })
}

resource "aws_lb_target_group" "web" {
  name        = "${var.name_prefix}-web"
  vpc_id      = var.vpc_id
  port        = var.web_port
  protocol    = "HTTP"
  target_type = "ip"

  deregistration_delay = 30

  health_check {
    path                = var.web_health_check_path
    matcher             = "200-399"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-web" })
}

# ----------------------------------------------------------------------------
# Listeners and rules
# ----------------------------------------------------------------------------

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = var.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = var.ssl_policy
  certificate_arn   = local.certificate_arn

  # With origin verification on, anything that reaches the default action did
  # not carry the shared secret header -> 403. Otherwise default = web.
  dynamic "default_action" {
    for_each = var.origin_verify_enabled ? [1] : []

    content {
      type = "fixed-response"

      fixed_response {
        content_type = "text/plain"
        message_body = "Forbidden"
        status_code  = "403"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.origin_verify_enabled ? [] : [1]

    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.web.arn
    }
  }

  tags = var.tags

  lifecycle {
    precondition {
      condition     = !var.origin_verify_enabled || var.origin_verify_header_value != null
      error_message = "origin_verify_header_value is required when origin_verify_enabled is true."
    }
  }
}

# /metrics is Prometheus-internal (docs/03-api-spec.md section 8): never expose it.
resource "aws_lb_listener_rule" "blocked" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 1

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = var.blocked_path_patterns
    }
  }

  tags = var.tags
}

resource "aws_lb_listener_rule" "api_paths" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = var.api_path_patterns
    }
  }

  dynamic "condition" {
    for_each = var.origin_verify_enabled ? [1] : []

    content {
      http_header {
        http_header_name = var.origin_verify_header_name
        values           = [var.origin_verify_header_value]
      }
    }
  }

  tags = var.tags
}

resource "aws_lb_listener_rule" "api_hosts" {
  count = length(var.api_host_names) > 0 ? 1 : 0

  listener_arn = aws_lb_listener.https.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    host_header {
      values = var.api_host_names
    }
  }

  dynamic "condition" {
    for_each = var.origin_verify_enabled ? [1] : []

    content {
      http_header {
        http_header_name = var.origin_verify_header_name
        values           = [var.origin_verify_header_value]
      }
    }
  }

  tags = var.tags
}

# Catch-all to web, only needed when the default action is the 403 guard.
resource "aws_lb_listener_rule" "web_verified" {
  count = var.origin_verify_enabled ? 1 : 0

  listener_arn = aws_lb_listener.https.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }

  condition {
    http_header {
      http_header_name = var.origin_verify_header_name
      values           = [var.origin_verify_header_value]
    }
  }

  tags = var.tags
}
