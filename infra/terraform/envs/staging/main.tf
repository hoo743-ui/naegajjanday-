###############################################################################
# STAGING - small, cheap, disposable. Same topology as prod.
###############################################################################

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}

# CloudFront certificates and CLOUDFRONT-scoped WAF live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.tags
  }
}

data "aws_caller_identity" "current" {}

locals {
  environment = "staging"

  tags = {
    Project     = var.project
    Environment = local.environment
    ManagedBy   = "terraform"
    Repository  = var.github_repository
  }

  # Repositories are created by envs/shared in the same account.
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  ecr_arn_base = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project}"
}

module "stack" {
  source = "../../modules/stack"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  project     = var.project
  environment = local.environment

  domain_name     = var.domain_name
  route53_zone_id = var.route53_zone_id

  # --- network: one NAT gateway, no interface endpoints (cost) ---------------
  vpc_cidr                   = "10.20.0.0/16"
  single_nat_gateway         = true
  enable_interface_endpoints = false

  # --- application -------------------------------------------------------------
  api_image = "${local.ecr_registry}/${var.project}/api:${var.api_image_tag}"
  web_image = "${local.ecr_registry}/${var.project}/web:${var.web_image_tag}"

  service_sizes = {
    api    = { cpu = 512, memory = 1024, min_count = 1, max_count = 2 }
    worker = { cpu = 512, memory = 1024, min_count = 1, max_count = 2 }
    beat   = { cpu = 256, memory = 512, min_count = 1, max_count = 1 }
    web    = { cpu = 256, memory = 512, min_count = 1, max_count = 2 }
  }

  worker_use_spot        = true
  enable_beat            = false # nightly batches run through EventBridge Scheduler
  enable_execute_command = true  # debugging convenience on staging only

  extra_api_environment = var.extra_api_environment

  # --- data stores ---------------------------------------------------------------
  rds_instance_class              = "db.t4g.small"
  rds_allocated_storage           = 20
  rds_max_allocated_storage       = 50
  rds_multi_az                    = false
  rds_backup_retention_period     = 3
  rds_create_read_replica         = false
  rds_connections_alarm_threshold = 130

  redis_node_type          = "cache.t4g.micro"
  redis_num_cache_clusters = 1

  opensearch_instance_type              = "t3.small.search"
  opensearch_instance_count             = 1
  opensearch_volume_size                = 20
  opensearch_create_service_linked_role = var.opensearch_create_service_linked_role

  # --- edge / security -------------------------------------------------------------
  cloudfront_price_class   = "PriceClass_200"
  waf_rate_limit           = 2000
  waf_generate_rate_limit  = 100
  admin_allowed_ipv4_cidrs = var.admin_allowed_ipv4_cidrs
  admin_allowed_ipv6_cidrs = var.admin_allowed_ipv6_cidrs
  protect_from_deletion    = false

  # --- operations --------------------------------------------------------------------
  log_retention_days      = 14
  alarm_emails            = var.alarm_emails
  github_repository       = var.github_repository
  github_environment_name = "staging"
  ecr_repository_arns     = ["${local.ecr_arn_base}/api", "${local.ecr_arn_base}/web"]
}
