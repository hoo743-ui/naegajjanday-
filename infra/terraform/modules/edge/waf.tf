###############################################################################
# AWS WAFv2 web ACL (scope CLOUDFRONT -> us-east-1)
#
# Priority order
#    0  admin-ip-allowlist     BLOCK /admin + /v1/admin unless source IP is allowlisted
#    1  AmazonIpReputationList managed
#    2  rate-limit-generate    POST /v1/courses/generate per IP
#    3  rate-limit-global      all requests per IP
#   10  CommonRuleSet          managed (SizeRestrictions_BODY -> count, see below)
#   11  KnownBadInputs         managed
#   12  SQLiRuleSet            managed
###############################################################################

locals {
  managed_rule_groups = [
    {
      name            = "AWSManagedRulesAmazonIpReputationList"
      priority        = 1
      count_overrides = []
    },
    {
      name     = "AWSManagedRulesCommonRuleSet"
      priority = 10
      # The 8 KB body limit would block POST /v1/admin/places/import (CSV/JSON
      # upload) and large chat payloads. Count instead of block.
      count_overrides = ["SizeRestrictions_BODY"]
    },
    {
      name            = "AWSManagedRulesKnownBadInputsRuleSet"
      priority        = 11
      count_overrides = []
    },
    {
      name            = "AWSManagedRulesSQLiRuleSet"
      priority        = 12
      count_overrides = []
    },
  ]
}

resource "aws_wafv2_ip_set" "admin_ipv4" {
  provider = aws.us_east_1

  name               = "${var.name_prefix}-admin-ipv4"
  description        = "IPv4 addresses allowed to reach the admin console and admin API"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV4"
  addresses          = var.admin_allowed_ipv4_cidrs

  tags = var.tags
}

resource "aws_wafv2_ip_set" "admin_ipv6" {
  provider = aws.us_east_1

  name               = "${var.name_prefix}-admin-ipv6"
  description        = "IPv6 addresses allowed to reach the admin console and admin API"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV6"
  addresses          = var.admin_allowed_ipv6_cidrs

  tags = var.tags
}

resource "aws_wafv2_web_acl" "this" {
  provider = aws.us_east_1

  name        = "${var.name_prefix}-edge"
  description = "Edge protection for ${var.name_prefix}"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # --------------------------------------------------------------------------
  # 0. Admin IP allowlist: (uri starts with /admin OR /v1/admin)
  #                        AND NOT ipv4 allowlist AND NOT ipv6 allowlist -> BLOCK
  # --------------------------------------------------------------------------
  rule {
    name     = "admin-ip-allowlist"
    priority = 0

    action {
      block {}
    }

    statement {
      and_statement {
        statement {
          or_statement {
            dynamic "statement" {
              for_each = var.admin_path_prefixes
              iterator = prefix

              content {
                byte_match_statement {
                  positional_constraint = "STARTS_WITH"
                  search_string         = prefix.value

                  field_to_match {
                    uri_path {}
                  }

                  text_transformation {
                    priority = 0
                    type     = "URL_DECODE"
                  }

                  text_transformation {
                    priority = 1
                    type     = "LOWERCASE"
                  }
                }
              }
            }
          }
        }

        statement {
          not_statement {
            statement {
              ip_set_reference_statement {
                arn = aws_wafv2_ip_set.admin_ipv4.arn
              }
            }
          }
        }

        statement {
          not_statement {
            statement {
              ip_set_reference_statement {
                arn = aws_wafv2_ip_set.admin_ipv6.arn
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-admin-ip-allowlist"
      sampled_requests_enabled   = true
    }
  }

  # --------------------------------------------------------------------------
  # 2. Rate limit for the expensive optimiser endpoint
  # --------------------------------------------------------------------------
  rule {
    name     = "rate-limit-generate"
    priority = 2

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_generate_rate_limit
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300

        scope_down_statement {
          and_statement {
            statement {
              byte_match_statement {
                positional_constraint = "STARTS_WITH"
                search_string         = "/v1/courses/generate"

                field_to_match {
                  uri_path {}
                }

                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }

            statement {
              byte_match_statement {
                positional_constraint = "EXACTLY"
                search_string         = "POST"

                field_to_match {
                  method {}
                }

                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-limit-generate"
      sampled_requests_enabled   = true
    }
  }

  # --------------------------------------------------------------------------
  # 3. Global per-IP rate limit
  # --------------------------------------------------------------------------
  rule {
    name     = "rate-limit-global"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-rate-limit-global"
      sampled_requests_enabled   = true
    }
  }

  # --------------------------------------------------------------------------
  # AWS managed rule groups
  # --------------------------------------------------------------------------
  dynamic "rule" {
    for_each = local.managed_rule_groups

    content {
      name     = rule.value.name
      priority = rule.value.priority

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          name        = rule.value.name
          vendor_name = "AWS"

          dynamic "rule_action_override" {
            for_each = rule.value.count_overrides

            content {
              name = rule_action_override.value

              action_to_use {
                count {}
              }
            }
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.name_prefix}-${rule.value.name}"
        sampled_requests_enabled   = true
      }
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-edge"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}

# ----------------------------------------------------------------------------
# Logging (log group name must start with aws-waf-logs-)
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "waf" {
  count    = var.enable_waf_logging ? 1 : 0
  provider = aws.us_east_1

  name              = "aws-waf-logs-${var.name_prefix}-edge"
  retention_in_days = var.waf_log_retention_days

  tags = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  count    = var.enable_waf_logging ? 1 : 0
  provider = aws.us_east_1

  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}
