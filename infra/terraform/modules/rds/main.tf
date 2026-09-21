###############################################################################
# RDS for PostgreSQL 16
#
# PostGIS: RDS ships the PostGIS 3.4 binaries for PostgreSQL 16 but does not
# enable them. The first Alembic migration must run, as the master user
# (member of rds_superuser):
#     CREATE EXTENSION IF NOT EXISTS postgis;
#     CREATE EXTENSION IF NOT EXISTS pg_trgm;
#     CREATE EXTENSION IF NOT EXISTS vector;   -- optional, user_preference.taste_vector
# No parameter group change is needed for those extensions.
###############################################################################

locals {
  identifier    = "${var.name_prefix}-pg"
  major_version = split(".", var.engine_version)[0]
  port          = 5432
  replica_class = coalesce(var.replica_instance_class, var.instance_class)
  monitoring_on = var.monitoring_interval > 0
  base_parameters = [
    { name = "rds.force_ssl", value = "1", apply_method = "pending-reboot" },
    { name = "shared_preload_libraries", value = "pg_stat_statements", apply_method = "pending-reboot" },
    { name = "log_min_duration_statement", value = "500", apply_method = "immediate" },
    { name = "log_lock_waits", value = "1", apply_method = "immediate" },
    { name = "idle_in_transaction_session_timeout", value = "60000", apply_method = "immediate" },
  ]
}

# ----------------------------------------------------------------------------
# Networking
# ----------------------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name       = local.identifier
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = local.identifier })
}

resource "aws_security_group" "this" {
  name_prefix = "${local.identifier}-"
  description = "PostgreSQL access for ${var.name_prefix}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = local.identifier })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  description                  = "PostgreSQL from application security group"
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  from_port                    = local.port
  to_port                      = local.port
  ip_protocol                  = "tcp"
}

# ----------------------------------------------------------------------------
# Parameter group
# ----------------------------------------------------------------------------

resource "aws_db_parameter_group" "this" {
  name_prefix = "${local.identifier}-"
  family      = "postgres${local.major_version}"
  description = "PostgreSQL ${local.major_version} parameters for ${var.name_prefix}"

  dynamic "parameter" {
    for_each = concat(local.base_parameters, var.extra_parameters)

    content {
      name         = parameter.value.name
      value        = parameter.value.value
      apply_method = parameter.value.apply_method
    }
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

# ----------------------------------------------------------------------------
# Credentials
#
# The password is generated here and stored in Secrets Manager together with a
# ready-to-use DSN (key "url"), because apps/api reads a single DATABASE_URL.
# Trade-off: the value is present in the (encrypted, access-restricted) state.
# RDS-managed rotation (manage_master_user_password) was deliberately not used:
# ECS injects secrets only at task start, so a rotation would break new
# connections of running tasks until they are restarted.
# ----------------------------------------------------------------------------

resource "random_password" "master" {
  length  = 32
  special = false # keeps the value safe to embed in a DSN without URL-encoding
}

resource "aws_secretsmanager_secret" "credentials" {
  name                    = "${var.name_prefix}/rds/credentials"
  description             = "Master credentials of ${local.identifier}"
  recovery_window_in_days = var.secret_recovery_window_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "credentials" {
  secret_id = aws_secretsmanager_secret.credentials.id
  secret_string = jsonencode({
    engine   = "postgres"
    username = var.master_username
    password = random_password.master.result
    host     = aws_db_instance.this.address
    port     = local.port
    dbname   = var.db_name
    url      = "${var.dsn_scheme}://${var.master_username}:${random_password.master.result}@${aws_db_instance.this.address}:${local.port}/${var.db_name}${var.dsn_query == "" ? "" : "?${var.dsn_query}"}"
  })
}

# ----------------------------------------------------------------------------
# Enhanced monitoring role
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "monitoring_assume" {
  count = local.monitoring_on ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  count = local.monitoring_on ? 1 : 0

  name_prefix        = "${var.name_prefix}-rds-mon-"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume[0].json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  count = local.monitoring_on ? 1 : 0

  role       = aws_iam_role.monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ----------------------------------------------------------------------------
# Primary instance
# ----------------------------------------------------------------------------

resource "aws_db_instance" "this" {
  identifier = local.identifier

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.master_username
  port     = local.port

  password = random_password.master.result

  storage_type          = "gp3"
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.this.name
  ca_cert_identifier     = "rds-ca-rsa2048-g1"

  backup_retention_period  = var.backup_retention_period
  backup_window            = var.backup_window
  maintenance_window       = var.maintenance_window
  copy_tags_to_snapshot    = true
  delete_automated_backups = false

  auto_minor_version_upgrade  = true
  allow_major_version_upgrade = false
  apply_immediately           = var.apply_immediately

  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_enabled ? var.performance_insights_retention_period : null
  performance_insights_kms_key_id       = var.performance_insights_enabled ? var.kms_key_arn : null

  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = local.monitoring_on ? aws_iam_role.monitoring[0].arn : null

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.identifier}-final"

  tags = merge(var.tags, { Name = local.identifier })

  depends_on = [aws_iam_role_policy_attachment.monitoring]
}

# ----------------------------------------------------------------------------
# Optional read replica
# ----------------------------------------------------------------------------

resource "aws_db_instance" "replica" {
  count = var.create_read_replica ? 1 : 0

  identifier          = "${local.identifier}-replica"
  replicate_source_db = aws_db_instance.this.identifier
  instance_class      = local.replica_class

  # Encryption settings are inherited from the source instance for in-region replicas.
  storage_type          = "gp3"
  max_allocated_storage = var.max_allocated_storage

  multi_az               = false
  vpc_security_group_ids = [aws_security_group.this.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.this.name
  ca_cert_identifier     = "rds-ca-rsa2048-g1"

  backup_retention_period    = 0
  maintenance_window         = var.maintenance_window
  auto_minor_version_upgrade = true
  apply_immediately          = var.apply_immediately

  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_enabled ? var.performance_insights_retention_period : null
  performance_insights_kms_key_id       = var.performance_insights_enabled ? var.kms_key_arn : null

  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = local.monitoring_on ? aws_iam_role.monitoring[0].arn : null

  deletion_protection = var.deletion_protection
  skip_final_snapshot = true

  tags = merge(var.tags, { Name = "${local.identifier}-replica" })
}
