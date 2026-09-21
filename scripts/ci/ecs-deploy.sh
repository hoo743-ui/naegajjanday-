#!/usr/bin/env bash
# ECS rolling-deploy helper used by .github/workflows/deploy.yml.
# Requires: aws cli v2, jq (both preinstalled on GitHub ubuntu runners).
#
#   ecs-deploy.sh current  <cluster> <service>
#       -> prints the task definition ARN the service currently runs
#   ecs-deploy.sh register <family> <container> <image>
#       -> clones the latest ACTIVE revision of <family> with a new image,
#          prints the new task definition ARN
#   ecs-deploy.sh run      <cluster> <service> <taskdef-arn> <container> <cmd...>
#       -> runs a one-off task (network config copied from <service>), waits,
#          prints its logs, fails when the container exit code is not 0
#   ecs-deploy.sh deploy   <cluster> <service> <taskdef-arn> [timeout-seconds]
#       -> updates the service and waits until the rollout COMPLETED.
#          Fails when the deployment circuit breaker rolled back (a plain
#          `aws ecs wait services-stable` would report success in that case).
#   ecs-deploy.sh exists   <cluster> <service>
#       -> exit 0 when the service is ACTIVE, 1 otherwise
set -euo pipefail

log() { echo "[ecs-deploy] $*" >&2; }

cmd_exists() {
  local cluster=$1 service=$2 status
  status=$(aws ecs describe-services --cluster "$cluster" --services "$service" \
    --query 'services[0].status' --output text 2>/dev/null || echo "MISSING")
  [[ "$status" == "ACTIVE" ]]
}

cmd_current() {
  local cluster=$1 service=$2
  aws ecs describe-services --cluster "$cluster" --services "$service" \
    --query 'services[0].taskDefinition' --output text
}

cmd_register() {
  local family=$1 container=$2 image=$3 current new
  current=$(aws ecs describe-task-definition --task-definition "$family" --query 'taskDefinition' --output json)

  if ! jq -e --arg c "$container" '.containerDefinitions | any(.name == $c)' <<<"$current" >/dev/null; then
    log "container '$container' not found in task definition family '$family'"
    exit 1
  fi

  new=$(jq --arg c "$container" --arg img "$image" '
      .containerDefinitions |= map(if .name == $c then .image = $img else . end)
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
            .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)
    ' <<<"$current")

  aws ecs register-task-definition --cli-input-json "$new" \
    --query 'taskDefinition.taskDefinitionArn' --output text
}

cmd_run() {
  local cluster=$1 service=$2 taskdef=$3 container=$4
  shift 4
  local netconf overrides task_arn exit_code stopped_reason task_id log_group log_prefix

  netconf=$(aws ecs describe-services --cluster "$cluster" --services "$service" \
    --query 'services[0].networkConfiguration' --output json)
  overrides=$(jq -cn --arg c "$container" '{containerOverrides: [{name: $c, command: $ARGS.positional}]}' --args "$@")

  log "running one-off task on $taskdef: $*"
  task_arn=$(aws ecs run-task --cluster "$cluster" --task-definition "$taskdef" \
    --launch-type FARGATE --count 1 --started-by "github-actions" \
    --network-configuration "$netconf" --overrides "$overrides" \
    --query 'tasks[0].taskArn' --output text)

  if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
    log "run-task did not return a task ARN"
    exit 1
  fi
  log "task: $task_arn"

  # The built-in waiter gives up after 10 minutes; loop for long migrations.
  local attempts=0
  until aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn" 2>/dev/null; do
    attempts=$((attempts + 1))
    if ((attempts >= 3)); then
      log "task did not stop within 30 minutes, stopping it"
      aws ecs stop-task --cluster "$cluster" --task "$task_arn" --reason "deploy timeout" >/dev/null
      exit 1
    fi
  done

  # Print the task output (best effort).
  task_id=${task_arn##*/}
  log_group=$(aws ecs describe-task-definition --task-definition "$taskdef" \
    --query "taskDefinition.containerDefinitions[?name=='$container'] | [0].logConfiguration.options.\"awslogs-group\"" --output text)
  log_prefix=$(aws ecs describe-task-definition --task-definition "$taskdef" \
    --query "taskDefinition.containerDefinitions[?name=='$container'] | [0].logConfiguration.options.\"awslogs-stream-prefix\"" --output text)
  aws logs get-log-events --log-group-name "$log_group" \
    --log-stream-name "$log_prefix/$container/$task_id" --start-from-head \
    --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' >&2 || log "could not read task logs"

  exit_code=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
    --query "tasks[0].containers[?name=='$container'] | [0].exitCode" --output text)
  stopped_reason=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
    --query 'tasks[0].stoppedReason' --output text)

  if [[ "$exit_code" != "0" ]]; then
    log "one-off task failed: exitCode=$exit_code reason=$stopped_reason"
    exit 1
  fi
  log "one-off task succeeded"
}

cmd_deploy() {
  local cluster=$1 service=$2 taskdef=$3 timeout=${4:-1200}
  local deadline state failed running desired

  log "updating $service -> $taskdef"
  aws ecs update-service --cluster "$cluster" --service "$service" \
    --task-definition "$taskdef" --query 'service.serviceArn' --output text >/dev/null

  deadline=$((SECONDS + timeout))
  while ((SECONDS < deadline)); do
    # Look at the deployment of OUR task definition, not just "PRIMARY": after a
    # circuit breaker rollback the old revision becomes PRIMARY again.
    read -r state failed running desired < <(aws ecs describe-services --cluster "$cluster" --services "$service" \
      --query "services[0].deployments[?taskDefinition=='$taskdef'] | [0].[rolloutState, failedTasks, runningCount, desiredCount]" \
      --output text)

    log "$service rollout=$state running=$running/$desired failed=$failed"
    case "$state" in
      COMPLETED) return 0 ;;
      FAILED)
        log "deployment FAILED - the circuit breaker rolled $service back"
        return 1
        ;;
      None)
        log "deployment of $taskdef disappeared (rolled back)"
        return 1
        ;;
    esac
    sleep 15
  done

  log "timed out after ${timeout}s waiting for $service"
  return 1
}

main() {
  local sub=${1:-}
  shift || true
  case "$sub" in
    exists) cmd_exists "$@" ;;
    current) cmd_current "$@" ;;
    register) cmd_register "$@" ;;
    run) cmd_run "$@" ;;
    deploy) cmd_deploy "$@" ;;
    *)
      sed -n '2,20p' "$0" >&2
      exit 2
      ;;
  esac
}

main "$@"
