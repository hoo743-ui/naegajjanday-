output "schedule_group_name" {
  description = "Name of the EventBridge Scheduler group."
  value       = aws_scheduler_schedule_group.this.name
}

output "schedule_arns" {
  description = "Map of schedule name => ARN."
  value       = { for k, s in aws_scheduler_schedule.this : k => s.arn }
}

output "scheduler_role_arn" {
  description = "ARN of the role EventBridge Scheduler assumes."
  value       = aws_iam_role.scheduler.arn
}

output "dead_letter_queue_arn" {
  description = "ARN of the SQS queue receiving failed invocations."
  value       = aws_sqs_queue.dlq.arn
}
