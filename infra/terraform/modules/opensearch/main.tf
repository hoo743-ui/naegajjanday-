###############################################################################
# Amazon OpenSearch Service domain inside the VPC
#
# Korean analysis (nori):
#   - The analysis-nori plugin is bundled with Amazon OpenSearch Service. Nothing
#     has to be installed; index settings can reference `nori_tokenizer`,
#     `nori_part_of_speech` and `nori_readingform` directly (docs/02-erd.md 5).
#   - A custom *user dictionary* (brand names, 신조어, place names such as
#     "성수연방") is delivered as an OpenSearch "package" of type TXT-DICTIONARY:
#     upload the file to S3, set var.nori_user_dictionary and reference it in the
#     tokenizer as  "user_dictionary": "analyzers/<package-id>".
#
# CLIENT COMPATIBILITY (action required in apps/api):
#   apps/api currently depends on `elasticsearch[async]>=8.15,<9`. That client
#   performs a product check and raises UnsupportedProductError against Amazon
#   OpenSearch Service. Before pointing ES_URL at this domain, switch the search
#   adapter to `opensearch-py` (AsyncOpenSearch; the query DSL used by the app -
#   nori, geo_distance, edge-ngram - is identical), or replace this module with
#   Elastic Cloud. Local dev keeps using Elasticsearch 8 from docker-compose.
###############################################################################

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  domain_name    = var.name_prefix
  zone_awareness = var.instance_count >= 2
  subnet_ids     = local.zone_awareness ? slice(var.subnet_ids, 0, 2) : slice(var.subnet_ids, 0, 1)
  domain_arn     = "arn:aws:es:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:domain/${local.domain_name}"
}

resource "aws_iam_service_linked_role" "opensearch" {
  count = var.create_service_linked_role ? 1 : 0

  aws_service_name = "opensearchservice.amazonaws.com"
}

resource "aws_security_group" "this" {
  name_prefix = "${var.name_prefix}-search-"
  description = "OpenSearch access for ${var.name_prefix}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name_prefix}-search" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  description                  = "HTTPS from application security group"
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

# ----------------------------------------------------------------------------
# Master user for fine-grained access control (internal user database)
# ----------------------------------------------------------------------------

resource "random_password" "master" {
  length           = 32
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
  override_special = "-_" # URL-safe: the password is embedded in the url key below
}

resource "aws_secretsmanager_secret" "credentials" {
  name                    = "${var.name_prefix}/opensearch/credentials"
  description             = "Master user of the ${local.domain_name} OpenSearch domain"
  recovery_window_in_days = var.secret_recovery_window_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "credentials" {
  secret_id = aws_secretsmanager_secret.credentials.id
  secret_string = jsonencode({
    username = var.master_user_name
    password = random_password.master.result
    endpoint = "https://${aws_opensearch_domain.this.endpoint}:443"
    # apps/api only knows ES_URL (+ ES_API_KEY); basic auth is carried in the URL.
    url = "https://${var.master_user_name}:${random_password.master.result}@${aws_opensearch_domain.this.endpoint}:443"
  })
}

# ----------------------------------------------------------------------------
# Domain
# ----------------------------------------------------------------------------

data "aws_iam_policy_document" "access" {
  # Network access is restricted by the security group; request-level access is
  # enforced by fine-grained access control (basic auth with the master user).
  statement {
    effect    = "Allow"
    actions   = ["es:ESHttp*"]
    resources = ["${local.domain_arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }
}

resource "aws_opensearch_domain" "this" {
  domain_name    = local.domain_name
  engine_version = var.engine_version

  cluster_config {
    instance_type  = var.instance_type
    instance_count = var.instance_count

    zone_awareness_enabled = local.zone_awareness

    dynamic "zone_awareness_config" {
      for_each = local.zone_awareness ? [1] : []

      content {
        availability_zone_count = 2
      }
    }

    dedicated_master_enabled = var.dedicated_master_count > 0
    dedicated_master_count   = var.dedicated_master_count > 0 ? var.dedicated_master_count : null
    dedicated_master_type    = var.dedicated_master_count > 0 ? var.dedicated_master_type : null
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.ebs_volume_size
  }

  vpc_options {
    subnet_ids         = local.subnet_ids
    security_group_ids = [aws_security_group.this.id]
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled                        = true
    anonymous_auth_enabled         = false
    internal_user_database_enabled = true

    master_user_options {
      master_user_name     = var.master_user_name
      master_user_password = random_password.master.result
    }
  }

  software_update_options {
    auto_software_update_enabled = true
  }

  access_policies = data.aws_iam_policy_document.access.json

  tags = merge(var.tags, { Name = local.domain_name })

  depends_on = [aws_iam_service_linked_role.opensearch]
}

# ----------------------------------------------------------------------------
# Optional nori user dictionary package
# ----------------------------------------------------------------------------

resource "aws_opensearch_package" "nori_user_dictionary" {
  count = var.nori_user_dictionary == null ? 0 : 1

  package_name = "${var.name_prefix}-nori-userdict"
  package_type = "TXT-DICTIONARY"

  package_source {
    s3_bucket_name = var.nori_user_dictionary.s3_bucket
    s3_key         = var.nori_user_dictionary.s3_key
  }
}

resource "aws_opensearch_package_association" "nori_user_dictionary" {
  count = var.nori_user_dictionary == null ? 0 : 1

  package_id  = aws_opensearch_package.nori_user_dictionary[0].id
  domain_name = aws_opensearch_domain.this.domain_name
}
