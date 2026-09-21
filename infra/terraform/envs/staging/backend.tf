# Partial backend configuration: the concrete bucket / key / table live in
# backend.hcl because backend blocks cannot use variables.
#
#   terraform init -backend-config=backend.hcl
#
# CI only validates: terraform init -backend=false
terraform {
  backend "s3" {}
}
