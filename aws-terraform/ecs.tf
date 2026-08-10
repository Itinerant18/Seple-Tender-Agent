# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "ecs_execution" {
  name = "${local.name_prefix}-ecs-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow Execution Role to read secrets
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${local.name_prefix}-ecs-exec-secrets-policy"
  role = aws_iam_role.ecs_execution.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["secretsmanager:GetSecretValue"]
      Effect   = "Allow"
      Resource = aws_secretsmanager_secret.tender_secrets.arn
    }]
  })
}

# IAM Role for ECS Tasks (Application)
resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

# ECR Repositories (To push your built images)
resource "aws_ecr_repository" "api" {
  name = "${local.name_prefix}-api"
}

resource "aws_ecr_repository" "agent" {
  name = "${local.name_prefix}-agent"
}

resource "aws_ecr_repository" "scanner" {
  name = "${local.name_prefix}-scanner"
}

resource "aws_ecr_repository" "searxng" {
  name = "${local.name_prefix}-searxng"
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}-api"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/ecs/${local.name_prefix}-agent"
  retention_in_days = 7
}

# ------------- API Service -------------
resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "tender-api"
    image     = "${aws_ecr_repository.api.repository_url}:latest"
    essential = true
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [
      { name = "DATABASE_URL", value = "postgresql://postgres:${urlencode(var.db_password)}@${aws_db_instance.main.endpoint}/tenders" }
    ]
    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:OPENAI_API_KEY::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "tender-api"
    container_port   = 8000
  }
}

# ------------- Agent Service -------------
resource "aws_ecs_task_definition" "agent" {
  family                   = "${local.name_prefix}-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  volume {
    name = "hermes_data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.main.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.hermes_data.id
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "hermes-agent"
    image     = "${aws_ecr_repository.agent.repository_url}:latest"
    essential = true
    command   = ["gateway", "run"]
    portMappings = [{
      containerPort = 9119
      protocol      = "tcp"
    }]
    environment = [
      { name = "TENDER_API_URL", value = "http://${aws_lb.main.dns_name}" },
      { name = "HERMES_DASHBOARD", value = "1" },
      { name = "HERMES_DASHBOARD_PORT", value = "9119" }
    ]
    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:OPENAI_API_KEY::" },
      { name = "HERMES_DASHBOARD_BASIC_AUTH_USERNAME", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:HERMES_DASHBOARD_BASIC_AUTH_USERNAME::" },
      { name = "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:HERMES_DASHBOARD_BASIC_AUTH_PASSWORD::" },
      { name = "HERMES_DASHBOARD_BASIC_AUTH_SECRET", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:HERMES_DASHBOARD_BASIC_AUTH_SECRET::" },
      { name = "HERMES_DASHBOARD_TENDER_USERNAME", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:HERMES_DASHBOARD_TENDER_USERNAME::" },
      { name = "HERMES_DASHBOARD_TENDER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:HERMES_DASHBOARD_TENDER_PASSWORD::" },
      { name = "TEAMS_WEBHOOK_URL", valueFrom = "${aws_secretsmanager_secret.tender_secrets.arn}:TEAMS_WEBHOOK_URL::" }
    ]
    mountPoints = [{
      sourceVolume  = "hermes_data"
      containerPath = "/opt/data"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.agent.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "agent"
      }
    }
  }])
}

resource "aws_ecs_service" "agent" {
  name            = "${local.name_prefix}-agent-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # The Hermes gateway does a lot of s6 init (skills sync, chromium check)
  # before it binds :9119 — without a grace period the ALB marks the task
  # unhealthy and kills it mid-boot.
  health_check_grace_period_seconds = 180

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.agent.arn
    container_name   = "hermes-agent"
    container_port   = 9119
  }
}
