###############################################################################
# EventBridge Scheduler -> one-off ECS Fargate tasks
#
# Alternative to an always-on Celery beat for the heavy nightly batches
# (`python -m app.cli ingest ...`): the task gets its own right-sized Fargate
# capacity, does not compete with the online worker queue and costs nothing
# while idle. RunTask failures go to an SQS dead letter queue.
###############################################################################

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  task_definition_arn = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/${var.task_definition_family}"
}

resource "aws_scheduler_schedule_group" "this" {
  name = "${var.name_prefix}-batch"

  tags = var.tags
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-scheduler-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = var.tags
}

# ----------------------------------------------------------------------------
# Role assumed by EventBridge Scheduler
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid     = "RunBatchTask"
    actions = ["ecs:RunTask"]
    resources = [
      local.task_definition_arn,
      "${local.task_definition_arn}:*",
    ]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.cluster_arn]
    }
  }

  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = var.passable_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "DeadLetter"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = var.tags
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "run-ecs-tasks"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.permissions.json
}

# ----------------------------------------------------------------------------
# Schedules
# ----------------------------------------------------------------------------

resource "aws_scheduler_schedule" "this" {
  for_each = var.schedules

  name        = "${var.name_prefix}-${each.key}"
  group_name  = aws_scheduler_schedule_group.this.name
  description = each.value.description
  state       = each.value.enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = each.value.schedule_expression
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.cluster_arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = local.task_definition_arn
      launch_type         = "FARGATE"
      platform_version    = "LATEST"
      task_count          = 1

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = var.security_group_ids
        assign_public_ip = false
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name    = var.container_name
          command = each.value.command
        }
      ]
    })

    retry_policy {
      maximum_retry_attempts       = var.maximum_retry_attempts
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}
