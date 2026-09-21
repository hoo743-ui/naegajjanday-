###############################################################################
# One complete environment of 내가짠데이.
#
# envs/staging and envs/prod call this module with different sizes and
# toggles; all wiring between the building-block modules lives here so both
# environments stay structurally identical.
#
#   Route53 -> CloudFront (+WAF) -> ALB -> ECS Fargate (web | api)
#                                           |-> RDS PostgreSQL 16 (+PostGIS)
#                                           |-> ElastiCache Redis 7
#                                           |-> OpenSearch (nori)
#   EventBridge Scheduler -> one-off Fargate tasks (nightly ingestion)
###############################################################################

locals {
  name_prefix = "${var.project}-${var.environment}"

  api_host = "${var.api_subdomain}.${var.domain_name}"
  aliases  = distinct(concat([var.domain_name, local.api_host], var.extra_aliases))
  site_url = "https://${var.domain_name}"

  # apps/api Settings.app_env accepts local | test | staging | production.
  app_env = var.environment == "prod" ? "production" : "staging"

  secret_recovery_window_days = var.protect_from_deletion ? 30 : 0

  api_port = 8000
  web_port = 3000
}

###############################################################################
# Network
###############################################################################

module "network" {
  source = "../network"

  name_prefix                = local.name_prefix
  vpc_cidr                   = var.vpc_cidr
  az_count                   = 2
  single_nat_gateway         = var.single_nat_gateway
  enable_interface_endpoints = var.enable_interface_endpoints
}

###############################################################################
# Load balancer + edge
###############################################################################

# Shared secret between CloudFront and the ALB so the WAF cannot be bypassed
# through another CloudFront distribution.
resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

module "alb" {
  source = "../alb"

  name_prefix       = local.name_prefix
  vpc_id            = module.network.vpc_id
  vpc_cidr_block    = module.network.vpc_cidr_block
  public_subnet_ids = module.network.public_subnet_ids

  domain_name     = var.domain_name
  route53_zone_id = var.route53_zone_id

  idle_timeout               = var.alb_idle_timeout
  restrict_to_cloudfront     = true
  origin_verify_enabled      = true
  origin_verify_header_value = random_password.origin_verify.result

  api_port       = local.api_port
  web_port       = local.web_port
  api_host_names = [local.api_host]

  enable_deletion_protection = var.protect_from_deletion
}

module "edge" {
  source = "../edge"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix     = local.name_prefix
  domain_name     = var.domain_name
  aliases         = local.aliases
  route53_zone_id = var.route53_zone_id

  # The alb module already owns the (identical) ACM validation CNAMEs.
  create_certificate_validation_records = false

  origin_domain_name         = module.alb.origin_domain_name
  origin_verify_enabled      = true
  origin_verify_header_value = random_password.origin_verify.result

  price_class                 = var.cloudfront_price_class
  assets_cors_allowed_origins = [for a in local.aliases : "https://${a}"]
  force_destroy_assets_bucket = !var.protect_from_deletion

  waf_rate_limit           = var.waf_rate_limit
  waf_generate_rate_limit  = var.waf_generate_rate_limit
  admin_allowed_ipv4_cidrs = var.admin_allowed_ipv4_cidrs
  admin_allowed_ipv6_cidrs = var.admin_allowed_ipv6_cidrs
}

###############################################################################
# Data stores
###############################################################################

locals {
  # Security groups of everything that talks to the data stores. The list
  # length is known at plan time, which the count-based ingress rules need.
  data_client_security_group_ids = concat(
    [module.api.security_group_id, module.worker.security_group_id],
    module.beat[*].security_group_id,
  )
}

module "rds" {
  source = "../rds"

  name_prefix                = local.name_prefix
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.database_subnet_ids
  allowed_security_group_ids = local.data_client_security_group_ids

  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  max_allocated_storage   = var.rds_max_allocated_storage
  multi_az                = var.rds_multi_az
  backup_retention_period = var.rds_backup_retention_period
  create_read_replica     = var.rds_create_read_replica
  replica_instance_class  = var.rds_replica_instance_class

  deletion_protection         = var.protect_from_deletion
  skip_final_snapshot         = !var.protect_from_deletion
  apply_immediately           = !var.protect_from_deletion
  secret_recovery_window_days = local.secret_recovery_window_days
}

module "redis" {
  source = "../elasticache"

  name_prefix                = local.name_prefix
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.database_subnet_ids
  allowed_security_group_ids = local.data_client_security_group_ids

  node_type          = var.redis_node_type
  num_cache_clusters = var.redis_num_cache_clusters
  apply_immediately  = !var.protect_from_deletion
}

module "opensearch" {
  source = "../opensearch"

  name_prefix                = local.name_prefix
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.database_subnet_ids
  allowed_security_group_ids = local.data_client_security_group_ids

  instance_type              = var.opensearch_instance_type
  instance_count             = var.opensearch_instance_count
  ebs_volume_size            = var.opensearch_volume_size
  dedicated_master_count     = var.opensearch_dedicated_master_count
  create_service_linked_role = var.opensearch_create_service_linked_role

  secret_recovery_window_days = local.secret_recovery_window_days
}

###############################################################################
# Application secret (placeholders - real values are set out of band)
###############################################################################

resource "random_password" "generated_secret" {
  for_each = toset(var.generated_secret_keys)

  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name_prefix}/app/config"
  description             = "Application secrets of ${local.name_prefix} (JSON object, one key per environment variable)"
  recovery_window_in_days = local.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id

  secret_string = jsonencode(merge(
    { for k in var.app_secret_keys : k => "" },
    { for k in var.generated_secret_keys : k => random_password.generated_secret[k].result },
  ))

  # Values are maintained by humans (console / CLI) after the first apply.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

###############################################################################
# ECS cluster
###############################################################################

resource "aws_ecs_cluster" "this" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

###############################################################################
# Runtime configuration shared by api / worker / beat
###############################################################################

locals {
  redis_base = "${module.redis.url_scheme}://${module.redis.primary_endpoint_address}:${module.redis.port}"
  # Celery refuses rediss:// URLs without an explicit ssl_cert_reqs.
  celery_tls_suffix = module.redis.url_scheme == "rediss" ? "?ssl_cert_reqs=required" : ""

  api_environment = merge(
    {
      APP_ENV               = local.app_env
      LOG_LEVEL             = "INFO"
      LOG_JSON              = "true"
      TIMEZONE              = "Asia/Seoul"
      PUBLIC_BASE_URL       = "https://${local.api_host}"
      WEB_BASE_URL          = local.site_url
      CORS_ORIGINS          = join(",", [for a in local.aliases : "https://${a}"])
      COOKIE_SECURE         = "true"
      REDIS_URL             = "${local.redis_base}/0"
      CELERY_BROKER_URL     = "${local.redis_base}/1${local.celery_tls_suffix}"
      CELERY_RESULT_BACKEND = "${local.redis_base}/2${local.celery_tls_suffix}"
      S3_ASSETS_BUCKET      = module.edge.assets_bucket_name
      ASSETS_BASE_URL       = "${local.site_url}/assets"
    },
    var.extra_api_environment,
  )

  api_secrets = merge(
    {
      DATABASE_URL = { arn = module.rds.credentials_secret_arn, key = "url" }
      ES_URL       = { arn = module.opensearch.credentials_secret_arn, key = "url" }
    },
    { for k in concat(var.app_secret_keys, var.generated_secret_keys) : k => { arn = aws_secretsmanager_secret.app.arn, key = k } },
  )

  web_environment = merge(
    {
      NODE_ENV = "production"
      PORT     = tostring(local.web_port)
      # Next.js standalone binds to $HOSTNAME, which ECS sets to the container id.
      HOSTNAME = "0.0.0.0"
    },
    var.extra_web_environment,
  )
}

data "aws_iam_policy_document" "app_task" {
  statement {
    sid = "AssetsObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${module.edge.assets_bucket_arn}/*"]
  }

  statement {
    sid       = "AssetsList"
    actions   = ["s3:ListBucket"]
    resources = [module.edge.assets_bucket_arn]
  }
}

###############################################################################
# Services
###############################################################################

module "api" {
  source = "../ecs_service"

  name_prefix  = local.name_prefix
  service_name = "api"
  cluster_arn  = aws_ecs_cluster.this.arn
  cluster_name = aws_ecs_cluster.this.name
  vpc_id       = module.network.vpc_id
  subnet_ids   = module.network.private_subnet_ids

  container_image = var.api_image
  container_port  = local.api_port
  command         = var.api_command
  cpu             = var.service_sizes["api"].cpu
  memory          = var.service_sizes["api"].memory
  environment     = local.api_environment
  secrets         = local.api_secrets

  health_check_command = "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${local.api_port}/healthz', timeout=3)\" || exit 1"
  stop_timeout         = 60

  attach_load_balancer       = true
  target_group_arn           = module.alb.api_target_group_arn
  ingress_security_group_ids = [module.alb.security_group_id]

  desired_count                = var.service_sizes["api"].min_count
  min_capacity                 = var.service_sizes["api"].min_count
  max_capacity                 = var.service_sizes["api"].max_count
  cpu_target_percent           = 60
  enable_request_count_scaling = true
  alb_resource_label           = module.alb.api_resource_label
  request_count_target         = 600

  attach_task_role_policy = true
  task_role_policy_json   = data.aws_iam_policy_document.app_task.json
  enable_execute_command  = var.enable_execute_command
  log_retention_days      = var.log_retention_days

  depends_on = [aws_ecs_cluster_capacity_providers.this]
}

module "worker" {
  source = "../ecs_service"

  name_prefix  = local.name_prefix
  service_name = "worker"
  cluster_arn  = aws_ecs_cluster.this.arn
  cluster_name = aws_ecs_cluster.this.name
  vpc_id       = module.network.vpc_id
  subnet_ids   = module.network.private_subnet_ids

  container_image = var.api_image
  command         = ["celery", "-A", var.celery_app, "worker", "--loglevel=INFO", "--concurrency=${var.worker_concurrency}"]
  cpu             = var.service_sizes["worker"].cpu
  memory          = var.service_sizes["worker"].memory
  environment     = local.api_environment
  secrets         = local.api_secrets

  # SIGTERM -> warm shutdown; Fargate (and Spot interruptions) allow at most 120s.
  stop_timeout = 120

  use_fargate_spot = var.worker_use_spot
  on_demand_base   = 1
  on_demand_weight = 1
  spot_weight      = 3

  desired_count      = var.service_sizes["worker"].min_count
  min_capacity       = var.service_sizes["worker"].min_count
  max_capacity       = var.service_sizes["worker"].max_count
  cpu_target_percent = 70

  attach_task_role_policy = true
  task_role_policy_json   = data.aws_iam_policy_document.app_task.json
  enable_execute_command  = var.enable_execute_command
  log_retention_days      = var.log_retention_days

  depends_on = [aws_ecs_cluster_capacity_providers.this]
}

module "beat" {
  source = "../ecs_service"
  count  = var.enable_beat ? 1 : 0

  name_prefix  = local.name_prefix
  service_name = "beat"
  cluster_arn  = aws_ecs_cluster.this.arn
  cluster_name = aws_ecs_cluster.this.name
  vpc_id       = module.network.vpc_id
  subnet_ids   = module.network.private_subnet_ids

  container_image = var.api_image
  command         = ["celery", "-A", var.celery_app, "beat", "--loglevel=INFO"]
  cpu             = var.service_sizes["beat"].cpu
  memory          = var.service_sizes["beat"].memory
  environment     = local.api_environment
  secrets         = local.api_secrets

  # Beat must be a singleton: stop the old task before starting the new one.
  desired_count                      = 1
  enable_autoscaling                 = false
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  log_retention_days = var.log_retention_days

  depends_on = [aws_ecs_cluster_capacity_providers.this]
}

module "web" {
  source = "../ecs_service"

  name_prefix  = local.name_prefix
  service_name = "web"
  cluster_arn  = aws_ecs_cluster.this.arn
  cluster_name = aws_ecs_cluster.this.name
  vpc_id       = module.network.vpc_id
  subnet_ids   = module.network.private_subnet_ids

  container_image = var.web_image
  container_port  = local.web_port
  cpu             = var.service_sizes["web"].cpu
  memory          = var.service_sizes["web"].memory
  environment     = local.web_environment

  attach_load_balancer       = true
  target_group_arn           = module.alb.web_target_group_arn
  ingress_security_group_ids = [module.alb.security_group_id]

  desired_count                = var.service_sizes["web"].min_count
  min_capacity                 = var.service_sizes["web"].min_count
  max_capacity                 = var.service_sizes["web"].max_count
  cpu_target_percent           = 60
  enable_request_count_scaling = true
  alb_resource_label           = module.alb.web_resource_label
  request_count_target         = 1000

  log_retention_days = var.log_retention_days

  depends_on = [aws_ecs_cluster_capacity_providers.this]
}

###############################################################################
# Nightly batch ingestion (EventBridge Scheduler -> one-off Fargate tasks)
###############################################################################

module "scheduled_tasks" {
  source = "../scheduled_tasks"

  name_prefix            = local.name_prefix
  cluster_arn            = aws_ecs_cluster.this.arn
  task_definition_family = module.worker.task_definition_family
  container_name         = module.worker.container_name
  subnet_ids             = module.network.private_subnet_ids
  security_group_ids     = [module.worker.security_group_id]
  passable_role_arns     = [module.worker.task_role_arn, module.worker.execution_role_arn]
  schedules              = var.scheduled_tasks
}

###############################################################################
# Observability
###############################################################################

module "observability" {
  source = "../observability"

  name_prefix  = local.name_prefix
  alarm_emails = var.alarm_emails

  alb_arn_suffix = module.alb.alb_arn_suffix
  target_groups = {
    api = {
      arn_suffix                    = module.alb.api_target_group_arn_suffix
      p95_latency_threshold_seconds = 1.5
    }
    web = {
      arn_suffix                    = module.alb.web_target_group_arn_suffix
      p95_latency_threshold_seconds = 2
    }
  }

  ecs_cluster_name = aws_ecs_cluster.this.name
  ecs_services = merge(
    {
      api    = module.api.service_name
      worker = module.worker.service_name
      web    = module.web.service_name
    },
    { for i, m in module.beat : "beat" => m.service_name },
  )

  rds_instance_id               = module.rds.instance_id
  rds_max_connections_threshold = var.rds_connections_alarm_threshold
  redis_cluster_ids             = module.redis.member_cluster_ids

  enable_opensearch_alarms = true
  opensearch_domain_name   = module.opensearch.domain_name
}

###############################################################################
# GitHub Actions deploy role (OIDC)
###############################################################################

module "deploy_role" {
  source = "../cicd_oidc"

  role_name            = "${local.name_prefix}-github-deploy"
  create_oidc_provider = var.create_github_oidc_provider
  github_repository    = var.github_repository
  allowed_subjects     = ["environment:${var.github_environment_name}"]

  ecr_repository_arns = var.ecr_repository_arns
  allow_ecr_push      = false

  enable_ecs_deploy = true
  ecs_cluster_arn   = aws_ecs_cluster.this.arn
  ecs_cluster_name  = aws_ecs_cluster.this.name

  # The migration runs as a one-off task of the api family.
  task_definition_families = [module.api.task_definition_family]

  passable_role_arns = concat(
    [
      module.api.task_role_arn, module.api.execution_role_arn,
      module.worker.task_role_arn, module.worker.execution_role_arn,
      module.web.task_role_arn, module.web.execution_role_arn,
    ],
    flatten([for m in module.beat : [m.task_role_arn, m.execution_role_arn]]),
  )

  log_group_arns               = [module.api.log_group_arn]
  cloudfront_distribution_arns = [module.edge.distribution_arn]
}
