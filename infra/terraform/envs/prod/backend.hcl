# TODO: replace <ACCOUNT_ID> with the output "state_bucket_name" of infra/terraform/bootstrap.
bucket         = "naegajjanday-tfstate-<ACCOUNT_ID>"
key            = "envs/prod/terraform.tfstate"
region         = "ap-northeast-2"
dynamodb_table = "naegajjanday-tfstate-lock"
encrypt        = true
