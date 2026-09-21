###############################################################################
# Reusable Fargate service
#
# Deployment model: ECS rolling update with deployment circuit breaker and
# automatic rollback. Terraform owns the *shape* of the task definition (cpu,
# memory, env, secrets, roles). CI (scripts/ci/ecs-deploy.sh) clones the latest
# revision, swaps the image tag and updates the service - therefore the service
# ignores drift on task_definition and desired_count.
###############################################################################

data "aws_region" "current" {}

locals {
  full_name = "${var.name_prefix}-${var.service_name}"

  environment = [
    for k in sort(keys(var.environment)) : { name = k, value = var.environment[k] }
  ]

  secrets = [
    for k in sort(keys(var.secrets)) : {
      name      = k
      valueFrom = var.secrets[k].key == null ? var.secrets[k].arn : "${var.secrets[k].arn}:${var.secrets[k].key}::"
    }
  ]

  secret_arns = distinct([for s in values(var.secrets) : s.arn])

  port_mappings = var.container_port == null ? [] : [
    {
      containerPort = var.container_port
      hostPort      = var.container_port
      protocol      = "tcp"
    }
  ]

  health_check = var.health_check_command == null ? null : {
    command     = ["CMD-SHELL", var.health_check_command]
    interval    = 30
    timeout     = 5
    retries     = 3
    startPeriod = 30
  }

  # Optional keys are dropped when null so the rendered JSON never contains
  # "command": null (which causes perpetual diffs).
  container_optional = {
    command     = var.command
    healthCheck = local.health_check
  }

  container_definition = merge(
    {
      name         = var.service_name
      image        = var.container_image
      essential    = true
      portMappings = local.port_mappings
      environment  = local.environment
      secrets      = local.secrets
      stopTimeout  = var.stop_timeout
      linuxParameters = {
        initProcessEnabled = true
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.this.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = var.service_name
        }
      }
    },
    { for k, v in local.container_optional : k => v if v != null },
  )
}

# ----------------------------------------------------------------------------
# Logs
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name_prefix}/${var.service_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# ----------------------------------------------------------------------------
# IAM: execution role (pull image, write logs, read secrets) and task role
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.full_name}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  count = length(var.secrets) > 0 ? 1 : 0

  statement {
    sid       = "ReadInjectedSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  count = length(var.secrets) > 0 ? 1 : 0

  name   = "read-injected-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets[0].json
}

resource "aws_iam_role" "task" {
  name               = "${local.full_name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

resource "aws_iam_role_policy" "task_app" {
  count = var.attach_task_role_policy ? 1 : 0

  name   = "application"
  role   = aws_iam_role.task.id
  policy = var.task_role_policy_json
}

data "aws_iam_policy_document" "task_exec_command" {
  count = var.enable_execute_command ? 1 : 0

  statement {
    sid = "EcsExec"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "task_exec_command" {
  count = var.enable_execute_command ? 1 : 0

  name   = "ecs-exec"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_exec_command[0].json
}

# ----------------------------------------------------------------------------
# Security group
# ----------------------------------------------------------------------------

resource "aws_security_group" "this" {
  name_prefix = "${local.full_name}-"
  description = "ECS service ${local.full_name}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = local.full_name })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "from_lb" {
  count = var.container_port == null ? 0 : length(var.ingress_security_group_ids)

  security_group_id            = aws_security_group.this.id
  description                  = "Container port from load balancer"
  referenced_security_group_id = var.ingress_security_group_ids[count.index]
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
}

# Tasks call external APIs (Kakao, Naver, TourAPI, LLM) through NAT, so egress
# is open. Data stores restrict ingress to this security group instead.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.this.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# ----------------------------------------------------------------------------
# Task definition
# ----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "this" {
  family                   = local.full_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.container_definition])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }

  dynamic "ephemeral_storage" {
    for_each = var.ephemeral_storage_gib == null ? [] : [var.ephemeral_storage_gib]

    content {
      size_in_gib = ephemeral_storage.value
    }
  }

  tags = var.tags
}

# ----------------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------------

resource "aws_ecs_service" "this" {
  name            = local.full_name
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count

  platform_version       = "LATEST"
  enable_execute_command = var.enable_execute_command
  propagate_tags         = "SERVICE"

  deployment_minimum_healthy_percent = var.deployment_minimum_healthy_percent
  deployment_maximum_percent         = var.deployment_maximum_percent
  health_check_grace_period_seconds  = var.attach_load_balancer ? var.health_check_grace_period_seconds : null

  deployment_controller {
    type = "ECS"
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # launch_type must stay unset when a capacity provider strategy is used.
  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [
      { provider = "FARGATE", base = var.on_demand_base, weight = var.on_demand_weight },
      { provider = "FARGATE_SPOT", base = 0, weight = var.spot_weight },
      ] : [
      { provider = "FARGATE", base = 0, weight = 1 },
    ]

    content {
      capacity_provider = capacity_provider_strategy.value.provider
      base              = capacity_provider_strategy.value.base
      weight            = capacity_provider_strategy.value.weight
    }
  }

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.this.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.attach_load_balancer ? [1] : []

    content {
      target_group_arn = var.target_group_arn
      container_name   = var.service_name
      container_port   = var.container_port
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [task_definition, desired_count]

    precondition {
      condition     = !var.attach_load_balancer || (var.target_group_arn != null && var.container_port != null)
      error_message = "attach_load_balancer requires target_group_arn and container_port."
    }
  }
}

# ----------------------------------------------------------------------------
# Autoscaling: CPU target tracking + optional ALB request count per target
# ----------------------------------------------------------------------------

resource "aws_appautoscaling_target" "this" {
  count = var.enable_autoscaling ? 1 : 0

  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.this.name}"
  min_capacity       = var.min_capacity
  max_capacity       = var.max_capacity
}

resource "aws_appautoscaling_policy" "cpu" {
  count = var.enable_autoscaling ? 1 : 0

  name               = "${local.full_name}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.this[0].service_namespace
  scalable_dimension = aws_appautoscaling_target.this[0].scalable_dimension
  resource_id        = aws_appautoscaling_target.this[0].resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.cpu_target_percent
    scale_in_cooldown  = var.scale_in_cooldown
    scale_out_cooldown = var.scale_out_cooldown

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "requests" {
  count = var.enable_autoscaling && var.enable_request_count_scaling ? 1 : 0

  name               = "${local.full_name}-alb-requests"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.this[0].service_namespace
  scalable_dimension = aws_appautoscaling_target.this[0].scalable_dimension
  resource_id        = aws_appautoscaling_target.this[0].resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.request_count_target
    scale_in_cooldown  = var.scale_in_cooldown
    scale_out_cooldown = var.scale_out_cooldown

    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = var.alb_resource_label
    }
  }

  lifecycle {
    precondition {
      condition     = var.alb_resource_label != null
      error_message = "enable_request_count_scaling requires alb_resource_label."
    }
  }
}
