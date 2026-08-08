resource "aws_cloudwatch_log_group" "scanner" {
  name              = "/ecs/${local.name_prefix}-scanner"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "scanner" {
  family                   = "${local.name_prefix}-scanner"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 2048
  memory                   = 4096 # Playwright scrapers + SearXNG sidecar
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  volume {
    name = "seple_sessions"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.main.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.seple_sessions.id
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "tender-scanner"
    image     = "${aws_ecr_repository.scanner.repository_url}:latest"
    essential = true
    # Run once instead of relying on internal scheduler
    command = ["python", "-m", "scheduler.run_once"]
    environment = [
      { name = "DATABASE_URL", value = "postgresql://postgres:${var.db_password}@${aws_db_instance.main.endpoint}/tenders" },
      # SearXNG runs as a sidecar in this task — reachable over localhost.
      { name = "SEARXNG_URL", value = "http://localhost:8080" }
    ]
    dependsOn = [{ containerName = "searxng", condition = "START" }]
    # Portal logins + scrape/LLM tool keys + notification channels. Each
    # notifier no-ops if its env is absent, so unset keys are harmless.
    secrets = [
      { name = "TENDER_TIGER_EMAIL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TENDER_TIGER_EMAIL::" },
      { name = "TENDER_TIGER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TENDER_TIGER_PASSWORD::" },
      { name = "TENDER247_EMAIL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TENDER247_EMAIL::" },
      { name = "TENDER247_PASSWORD", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TENDER247_PASSWORD::" },
      { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:OPENAI_API_KEY::" },
      { name = "LLM_MODEL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:LLM_MODEL::" },
      { name = "BRAVE_API_KEY", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:BRAVE_API_KEY::" },
      { name = "APIFY_API_TOKEN", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:APIFY_API_TOKEN::" },
      { name = "CONTEXT_DEV_API_KEY", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:CONTEXT_DEV_API_KEY::" },
      { name = "ZYTE_API", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:ZYTE_API::" },
      { name = "SLACK_WEBHOOK_URL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SLACK_WEBHOOK_URL::" },
      { name = "TEAMS_WEBHOOK_URL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TEAMS_WEBHOOK_URL::" },
      { name = "SMTP_SERVER", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SMTP_SERVER::" },
      { name = "SMTP_PORT", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SMTP_PORT::" },
      { name = "SMTP_USER", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SMTP_USER::" },
      { name = "SMTP_PASS", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SMTP_PASS::" },
      { name = "SENDER_EMAIL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:SENDER_EMAIL::" },
      { name = "RECIPIENT_EMAILS", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:RECIPIENT_EMAILS::" }
    ]
    mountPoints = [{
      sourceVolume  = "seple_sessions"
      containerPath = "/root/.seple"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.scanner.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "scanner"
      }
    }
    },
    {
      # Free self-hosted search for web_discovery, alongside Brave. Only alive
      # for the duration of the daily scan task, so cost is negligible.
      name         = "searxng"
      image        = "${aws_ecr_repository.searxng.repository_url}:latest"
      essential    = false
      portMappings = [{ containerPort = 8080 }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.scanner.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "searxng"
        }
      }
  }])
}

# EventBridge Rule to trigger scanner daily at 00:30 UTC
resource "aws_cloudwatch_event_rule" "scanner_schedule" {
  name                = "${local.name_prefix}-scanner-schedule"
  description         = "Trigger Tender Scanner daily at 00:30 UTC"
  schedule_expression = "cron(30 0 * * ? *)"
}

# IAM Role for EventBridge to run ECS Task
resource "aws_iam_role" "events_ecs" {
  name = "${local.name_prefix}-events-ecs-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "events_ecs_run_task" {
  name = "${local.name_prefix}-events-ecs-policy"
  role = aws_iam_role.events_ecs.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ecs:RunTask"
      Resource = aws_ecs_task_definition.scanner.arn
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
    }]
  })
}

resource "aws_cloudwatch_event_target" "scanner_ecs_task" {
  rule      = aws_cloudwatch_event_rule.scanner_schedule.name
  target_id = "TenderScannerTask"
  arn       = aws_ecs_cluster.main.arn
  role_arn  = aws_iam_role.events_ecs.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.scanner.arn
    launch_type         = "FARGATE"
    network_configuration {
      subnets         = aws_subnet.private[*].id
      security_groups = [aws_security_group.ecs.id]
    }
  }
}
