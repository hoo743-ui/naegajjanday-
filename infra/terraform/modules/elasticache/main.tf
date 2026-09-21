###############################################################################
# ElastiCache for Redis 7 (replication group, cluster mode disabled)
#
# Used for: candidate/course cache, rate limiting, Idempotency-Key store (24h),
# JWT jti denylist, and as the Celery broker / result backend.
###############################################################################

locals {
  replication_group_id = "${var.name_prefix}-redis"
  port                 = 6379
  ha_enabled           = var.num_cache_clusters > 1

  # Member cluster ids are deterministic, which keeps them known at plan time
  # for the CloudWatch alarms (for_each) in the observability module.
  member_cluster_ids = [
    for i in range(var.num_cache_clusters) : format("%s-%03d", local.replication_group_id, i + 1)
  ]
}

resource "aws_elasticache_subnet_group" "this" {
  name       = local.replication_group_id
  subnet_ids = var.subnet_ids

  tags = var.tags
}

resource "aws_security_group" "this" {
  name_prefix = "${local.replication_group_id}-"
  description = "Redis access for ${var.name_prefix}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = local.replication_group_id })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  description                  = "Redis from application security group"
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  from_port                    = local.port
  to_port                      = local.port
  ip_protocol                  = "tcp"
}

resource "aws_elasticache_parameter_group" "this" {
  name        = "${local.replication_group_id}-params"
  family      = "redis7"
  description = "Redis 7 parameters for ${var.name_prefix}"

  parameter {
    name  = "maxmemory-policy"
    value = var.maxmemory_policy
  }

  tags = var.tags
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = local.replication_group_id
  description          = "Redis for ${var.name_prefix} (cache, rate limit, Celery broker)"

  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = local.port
  parameter_group_name = aws_elasticache_parameter_group.this.name

  num_cache_clusters         = var.num_cache_clusters
  automatic_failover_enabled = local.ha_enabled
  multi_az_enabled           = local.ha_enabled

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.this.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = var.transit_encryption_enabled

  snapshot_retention_limit   = var.snapshot_retention_limit
  snapshot_window            = var.snapshot_window
  maintenance_window         = var.maintenance_window
  auto_minor_version_upgrade = true
  apply_immediately          = var.apply_immediately

  tags = merge(var.tags, { Name = local.replication_group_id })
}
