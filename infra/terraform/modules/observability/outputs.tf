output "sns_topic_arn" {
  description = "ARN of the alarm SNS topic. Subscribe Slack (AWS Chatbot) or PagerDuty here."
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard."
  value       = aws_cloudwatch_dashboard.this.dashboard_name
}
