###############################################################################
# Account-level resources shared by staging and prod
#   - ECR repositories (build once, promote the same image)
#   - GitHub OIDC provider (only one per account may exist)
#   - "build" role: GitHub Actions on main may push images, nothing else
#
# Apply order: bootstrap -> shared -> staging -> prod
###############################################################################

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = "shared"
      ManagedBy   = "terraform"
      Repository  = var.github_repository
    }
  }
}

module "ecr" {
  source = "../../modules/ecr"

  namespace        = var.project
  repository_names = ["api", "web"]
  keep_last_images = var.ecr_keep_last_images
}

module "build_role" {
  source = "../../modules/cicd_oidc"

  role_name            = "${var.project}-github-build"
  create_oidc_provider = var.create_github_oidc_provider
  github_repository    = var.github_repository

  # The build job has no GitHub Environment, so its subject is the branch ref.
  allowed_subjects = ["ref:refs/heads/${var.deploy_branch}"]

  ecr_repository_arns = values(module.ecr.repository_arns)
  allow_ecr_push      = true
}
