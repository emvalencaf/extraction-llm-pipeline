locals {
  widget_width = 12

  # App metrics are EMF in InvoiceExtraction, no dimensions.
  dashboard_widgets = [
    {
      title   = "Jobs"
      metrics = [["InvoiceExtraction", "JobSucceeded"], ["InvoiceExtraction", "JobFailed"]]
      stat    = "Sum"
    },
    {
      title   = "Job duration (ms)"
      metrics = [["InvoiceExtraction", "JobDurationMs"]]
      stat    = "Maximum"
    },
    {
      title = "Gemini calls: errors and latency"
      metrics = [
        ["InvoiceExtraction", "LlmCallError"],
        ["InvoiceExtraction", "LlmLatencyMs", { stat = "Average", yAxis = "right" }],
      ]
      stat = "Sum"
    },
    {
      title   = "Tokens"
      metrics = [["InvoiceExtraction", "LlmInputTokens"], ["InvoiceExtraction", "LlmOutputTokens"]]
      stat    = "Sum"
    },
    {
      title   = "Grounding Rate"
      metrics = [["InvoiceExtraction", "GroundingRate"]]
      stat    = "Average"
    },
    {
      title = "Queues: DLQ depth and oldest message age"
      metrics = [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name],
        ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", var.jobs_queue_name, { yAxis = "right" }],
      ]
      stat = "Maximum"
    },
    {
      title = "Lambda errors"
      metrics = [
        ["AWS/Lambda", "Errors", "FunctionName", var.worker_function_name],
        ["AWS/Lambda", "Errors", "FunctionName", var.api_function_name],
      ]
      stat = "Sum"
    },
  ]
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.prefix}-overview"

  dashboard_body = jsonencode({
    widgets = [
      for i, w in local.dashboard_widgets : {
        type   = "metric"
        x      = (i % 2) * local.widget_width
        y      = floor(i / 2) * 6
        width  = local.widget_width
        height = 6
        properties = {
          title   = w.title
          region  = var.region
          view    = "timeSeries"
          stat    = w.stat
          period  = 300
          metrics = w.metrics
        }
      }
    ]
  })
}
