# infra/terraform

AWS `ap-northeast-2`, Terraform >= 1.7, AWS provider `~> 5.60`.

```
Route53 -> CloudFront (+WAFv2) -> ALB -> ECS Fargate  web (Next.js :3000) | api (FastAPI :8000)
                     \-> S3 assets (OAC)       |-> RDS PostgreSQL 16 (+PostGIS)   [isolated subnets]
                                               |-> ElastiCache Redis 7
                                               |-> OpenSearch (nori)
EventBridge Scheduler -> one-off Fargate tasks  `python -m app.cli ingest --provider ... --all`
GitHub Actions --OIDC--> build role (ECR push) / deploy role per environment (ECS deploy)
```

## Layout

| Path | Purpose |
|---|---|
| `bootstrap/` | S3 state bucket + DynamoDB lock table. Local state, applied once per account. |
| `envs/shared/` | ECR repos (`naegajjanday/api`, `naegajjanday/web`), GitHub OIDC provider, **build** role. |
| `envs/staging/`, `envs/prod/` | One call of `modules/stack` each, differing only in sizes and toggles. |
| `modules/stack/` | Wires every building block into one environment. |
| `modules/{network,alb,edge,ecs_service,rds,elasticache,opensearch,observability,cicd_oidc,ecr,scheduled_tasks}` | Building blocks. |

## Apply order

```bash
cd bootstrap     && terraform init && terraform apply           # once
# put the bucket name into envs/*/backend.hcl
cd envs/shared   && terraform init -backend-config=backend.hcl && terraform apply
cd envs/staging  && cp terraform.tfvars.example terraform.tfvars && terraform init -backend-config=backend.hcl && terraform apply
cd envs/prod     && ... same
```

After the first apply of an environment:

1. Fill the placeholder keys of the secret `<prefix>/app/config` (output `app_secret_arn`). OAuth / provider keys start empty, `JWT_SECRET` and `WEBHOOK_SECRET` start as random values.
2. Copy the output `github_environment_variables` into the GitHub Environment (`staging` / `production`) variables, and `build_role_arn` of `envs/shared` into the repository variable `AWS_BUILD_ROLE_ARN`.
3. Push an image: the Terraform-registered task definitions point at the tag `bootstrap`, which does not exist. Services stay at 0 running tasks until the first run of `.github/workflows/deploy.yml`.

## staging vs prod

| | staging | prod |
|---|---|---|
| NAT | 1 shared | 1 per AZ |
| Interface endpoints (ECR, Logs, Secrets) | off (S3 gateway only) | on |
| api / web tasks | 1-2 | 2-10 / 2-8 |
| workers | 1-2, Fargate Spot mix | 2-8, Fargate Spot mix (1 on-demand base) |
| Celery beat service | off | on |
| RDS | db.t4g.small, single AZ, 3 d backups | db.m6g.large, Multi-AZ, 14 d backups, read replica |
| Redis | cache.t4g.micro x1 | cache.m6g.large x2, automatic failover |
| OpenSearch | t3.small.search x1 | m6g.large.search x2, zone aware |
| Deletion protection / final snapshot | off | on |

## Decisions worth knowing

- **Deployments are ECS rolling updates** with the deployment circuit breaker and automatic rollback (`modules/ecs_service`). No CodeDeploy. Terraform owns the shape of a task definition; CI clones the latest revision with a new image tag, so services ignore `task_definition` / `desired_count` drift. After changing env vars or secrets in Terraform, run the deploy workflow so the services pick up the new revision.
- **Runtime contract with `apps/api`** (`app/core/config.py`): `DATABASE_URL` and `ES_URL` are injected from Secrets Manager JSON keys (`url`), everything else in `<prefix>/app/config` is injected key by key. `APP_ENV` is `staging` or `production`.
- **Redis eviction policy is `volatile-lru`**, because the Celery broker shares the instance with the cache: only keys with a TTL may be evicted.
- **SSE**: ALB idle timeout is 300 s, the CloudFront `/v1/*` behaviour is uncached and uncompressed. CloudFront closes an origin connection that is silent for 60 s, so SSE endpoints must send a heartbeat comment (`: ping`) every ~15 s.
- **WAF** is CLOUDFRONT-scoped (us-east-1). The ALB only accepts CloudFront (managed prefix list + secret `X-Origin-Verify` header), so the WAF cannot be bypassed. `/admin` and `/v1/admin` are blocked unless the source IP is in `admin_allowed_ipv4_cidrs` / `..._ipv6_cidrs`; an empty list blocks everyone.
- **OpenSearch vs the Elasticsearch client**: `apps/api` depends on `elasticsearch[async] 8.x`, whose product check rejects Amazon OpenSearch Service. Switch the search adapter to `opensearch-py` before relying on `modules/opensearch` (see the header of `modules/opensearch/main.tf`). nori itself is bundled with the service; a custom user dictionary is attached through `nori_user_dictionary`.
- **PostGIS** is enabled by the first migration (`CREATE EXTENSION IF NOT EXISTS postgis`), run as the master user. No parameter group change is required.
- The GitHub OIDC provider exists once per account: `envs/shared` creates it, the environments look it up (`create_github_oidc_provider = false`).

## Validation

```bash
terraform fmt -check -recursive
for d in bootstrap envs/shared envs/staging envs/prod; do (cd $d && terraform init -backend=false && terraform validate); done
tflint --recursive --config "$(pwd)/.tflint.hcl"
```
