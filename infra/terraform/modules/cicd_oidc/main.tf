###############################################################################
# GitHub Actions -> AWS through OIDC (no long-lived access keys)
#
# Two role flavours are built from this module:
#   build  (envs/shared)        : ECR push, trusted for ref:refs/heads/main
#   deploy (envs/staging|prod)  : ECS deploy, trusted for environment:<name>
#                                 -> the prod role can only be assumed by a job
#                                    that passed the GitHub Environment approval.
###############################################################################

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  oidc_url          = "https://token.actions.githubusercontent.com"
  oidc_provider_arn = var.create_oidc_provider ? one(aws_iam_openid_connect_provider.github[*].arn) : one(data.aws_iam_openid_connect_provider.github[*].arn)

  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  has_ecr = length(var.ecr_repository_arns) > 0
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = local.oidc_url
  client_id_list = ["sts.amazonaws.com"]

  # AWS validates GitHub's certificate chain against its own trust store and
  # ignores these values, but older provider versions still require the field.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]

  tags = var.tags
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1

  url = local.oidc_url
}

# ----------------------------------------------------------------------------
# Trust policy
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for s in var.allowed_subjects : "repo:${var.github_repository}:${s}"]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = var.role_name
  description          = "Assumed by GitHub Actions of ${var.github_repository} through OIDC"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = var.max_session_duration

  tags = var.tags
}

# ----------------------------------------------------------------------------
# Permissions
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "permissions" {
  # GetAuthorizationToken does not support resource-level permissions.
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = local.has_ecr ? [1] : []

    content {
      sid = "EcrRead"
      actions = [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:GetDownloadUrlForLayer",
      ]
      resources = var.ecr_repository_arns
    }
  }

  dynamic "statement" {
    for_each = local.has_ecr && var.allow_ecr_push ? [1] : []

    content {
      sid = "EcrPush"
      actions = [
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart",
      ]
      resources = var.ecr_repository_arns
    }
  }

  # Register/Describe task definition do not support resource-level permissions.
  dynamic "statement" {
    for_each = var.enable_ecs_deploy ? [1] : []

    content {
      sid = "EcsTaskDefinitions"
      actions = [
        "ecs:DescribeTaskDefinition",
        "ecs:ListTaskDefinitions",
        "ecs:RegisterTaskDefinition",
      ]
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = var.enable_ecs_deploy ? [1] : []

    content {
      sid = "EcsServices"
      actions = [
        "ecs:DescribeServices",
        "ecs:UpdateService",
      ]
      resources = ["arn:aws:ecs:${local.region}:${local.account_id}:service/${var.ecs_cluster_name}/*"]
    }
  }

  dynamic "statement" {
    for_each = var.enable_ecs_deploy && length(var.task_definition_families) > 0 ? [1] : []

    content {
      sid     = "EcsRunOneOffTasks"
      actions = ["ecs:RunTask"]
      resources = [
        for f in var.task_definition_families : "arn:aws:ecs:${local.region}:${local.account_id}:task-definition/${f}:*"
      ]

      condition {
        test     = "ArnEquals"
        variable = "ecs:cluster"
        values   = [var.ecs_cluster_arn]
      }
    }
  }

  dynamic "statement" {
    for_each = var.enable_ecs_deploy ? [1] : []

    content {
      sid = "EcsTasks"
      actions = [
        "ecs:DescribeTasks",
        "ecs:StopTask",
      ]
      resources = ["arn:aws:ecs:${local.region}:${local.account_id}:task/${var.ecs_cluster_name}/*"]
    }
  }

  dynamic "statement" {
    for_each = var.enable_ecs_deploy && length(var.passable_role_arns) > 0 ? [1] : []

    content {
      sid       = "PassTaskRoles"
      actions   = ["iam:PassRole"]
      resources = var.passable_role_arns

      condition {
        test     = "StringEquals"
        variable = "iam:PassedToService"
        values   = ["ecs-tasks.amazonaws.com"]
      }
    }
  }

  dynamic "statement" {
    for_each = length(var.log_group_arns) > 0 ? [1] : []

    content {
      sid = "ReadTaskLogs"
      actions = [
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
      ]
      resources = [for arn in var.log_group_arns : "${arn}:*"]
    }
  }

  dynamic "statement" {
    for_each = length(var.cloudfront_distribution_arns) > 0 ? [1] : []

    content {
      sid       = "InvalidateCdn"
      actions   = ["cloudfront:CreateInvalidation"]
      resources = var.cloudfront_distribution_arns
    }
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "github-actions"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json

  lifecycle {
    precondition {
      condition     = !var.enable_ecs_deploy || (var.ecs_cluster_arn != null && var.ecs_cluster_name != null)
      error_message = "enable_ecs_deploy requires ecs_cluster_arn and ecs_cluster_name."
    }
  }
}
