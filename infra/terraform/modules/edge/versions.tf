terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 6.0"

      # CloudFront certificates and CLOUDFRONT-scoped WAF resources must live in
      # us-east-1. The caller passes that provider as aws.us_east_1.
      configuration_aliases = [aws.us_east_1]
    }
  }
}
