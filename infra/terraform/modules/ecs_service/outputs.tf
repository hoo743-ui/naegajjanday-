output "service_name" {
  description = "Name of the ECS service."
  value       = aws_ecs_service.this.name
}

output "service_arn" {
  description = "ARN of the ECS service."
  value       = aws_ecs_service.this.id
}

output "container_name" {
  description = "Name of the container inside the task definition."
  value       = var.service_name
}

output "task_definition_family" {
  description = "Task definition family. CI registers new revisions in this family."
  value       = aws_ecs_task_definition.this.family
}

output "task_definition_arn" {
  description = "ARN of the Terraform-managed task definition revision."
  value       = aws_ecs_task_definition.this.arn
}

output "task_role_arn" {
  description = "ARN of the task role (application permissions)."
  value       = aws_iam_role.task.arn
}

output "execution_role_arn" {
  description = "ARN of the task execution role."
  value       = aws_iam_role.execution.arn
}

output "security_group_id" {
  description = "Security group attached to the tasks. Add it to data store allowlists."
  value       = aws_security_group.this.id
}

output "log_group_name" {
  description = "CloudWatch log group name."
  value       = aws_cloudwatch_log_group.this.name
}

output "log_group_arn" {
  description = "CloudWatch log group ARN."
  value       = aws_cloudwatch_log_group.this.arn
}
