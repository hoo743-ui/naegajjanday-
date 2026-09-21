###############################################################################
# PRODUCTION - HA across two AZs, deletion protection, larger instances.
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
  environment = "prod"

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
  extra_aliases   = var.extra_aliases
  route53_zone_id = var.route53_zone_id

  # --- network: NAT gateway per AZ + interface endpoints ------------------------
  vpc_cidr                   = "10.10.0.0/16"
  single_nat_gateway         = false
  enable_interface_endpoints = true

  # --- application -------------------------------------------------------------
  api_image = "${local.ecr_registry}/${var.project}/api:${var.api_image_tag}"
  web_image = "${local.ecr_registry}/${var.project}/web:${var.web_image_tag}"

  service_sizes = {
    api    = { cpu = 1024, memory = 2048, min_count = 2, max_count = 10 }
    worker = { cpu = 1024, memory = 2048, min_count = 2, max_count = 8 }
    beat   = { cpu = 256, memory = 512, min_count = 1, max_count = 1 }
    web    = { cpu = 512, memory = 1024, min_count = 2, max_count = 8 }
  }

  worker_use_spot        = true
  enable_beat            = true  # sub-hourly periodic tasks; nightly batches still use EventBridge Scheduler
  enable_execute_command = false # turn on temporarily for incident debugging

  extra_api_environment = var.extra_api_environment

  # --- data stores ---------------------------------------------------------------
  rds_instance_class              = "db.m6g.large"
  rds_allocated_storage           = 100
  rds_max_allocated_storage       = 500
  rds_multi_az                    = true
  rds_backup_retention_period     = 14
  rds_create_read_replica         = true # admin analytics / heavy reads
  rds_replica_instance_class      = "db.t4g.medium"
  rds_connections_alarm_threshold = 680

  redis_node_type          = "cache.m6g.large"
  redis_num_cache_clusters = 2 # primary + replica, automatic failover, Multi-AZ

  opensearch_instance_type              = "m6g.large.search"
  opensearch_instance_count             = 2 # zone aware across two AZs
  opensearch_volume_size                = 50
  opensearch_dedicated_master_count     = 0 # set to 3 once the index grows beyond a few GB
  opensearch_create_service_linked_role = var.opensearch_create_service_linked_role

  # --- edge / security -------------------------------------------------------------
  cloudfront_price_class   = "PriceClass_200"
  waf_rate_limit           = 2000
  waf_generate_rate_limit  = 100
  admin_allowed_ipv4_cidrs = var.admin_allowed_ipv4_cidrs
  admin_allowed_ipv6_cidrs = var.admin_allowed_ipv6_cidrs
  protect_from_deletion    = true

  # --- operations --------------------------------------------------------------------
  log_retention_days      = 90
  alarm_emails            = var.alarm_emails
  github_repository       = var.github_repository
  github_environment_name = "production"
  ecr_repository_arns     = ["${local.ecr_arn_base}/api", "${local.ecr_arn_base}/web"]
}
