# Alarms on the metrics the app emits through EMF (src/.../adapters/json_events.py), namespace
# InvoiceExtraction, no dimensions. tests/test_observability_infra.py checks the names.
# Missing data is not breaching: no traffic means no metric, not a failure.

resource "aws_cloudwatch_metric_alarm" "job_failed" {
  alarm_name          = "${var.prefix}-job-failed"
  alarm_description   = "A job failed on infrastructure (status failed), not a bad document. Runbook: docs/runbook.md#job-failed"
  namespace           = "InvoiceExtraction"
  metric_name         = "JobInfraFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "llm_call_errors" {
  alarm_name          = "${var.prefix}-llm-call-errors"
  alarm_description   = "Gemini calls failed (transient or rejected). Runbook: docs/runbook.md#llm-call-errors"
  namespace           = "InvoiceExtraction"
  metric_name         = "LlmCallError"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "job_duration_high" {
  alarm_name          = "${var.prefix}-job-duration-high"
  alarm_description   = "A job ran close to the worker timeout. Runbook: docs/runbook.md#job-duration-high"
  namespace           = "InvoiceExtraction"
  metric_name         = "JobDurationMs"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.worker_timeout_seconds * 1000 * 0.8
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "grounding_rate_low" {
  alarm_name          = "${var.prefix}-grounding-rate-low"
  alarm_description   = "Average Grounding Rate fell below the floor. Runbook: docs/runbook.md#grounding-rate-low"
  namespace           = "InvoiceExtraction"
  metric_name         = "GroundingRate"
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 1
  threshold           = var.grounding_rate_floor
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
