# Create the Secret in AWS Secrets Manager
resource "aws_secretsmanager_secret" "tender_secrets" {
  name        = "${local.name_prefix}-secrets"
  description = "Secrets for the SEPLE tender platform (API Keys, Dashboard Auth, etc.)"
  
  # Ensure the secret is not deleted immediately on destroy to allow fast recreation if needed, 
  # or change to 0 if you want immediate deletion in dev/staging.
  recovery_window_in_days = 0 
}

# We define the JSON structure so Terraform knows what keys exist,
# but the actual values should be populated manually in the AWS Console
# or via a secure CI/CD pipeline.
resource "aws_secretsmanager_secret_version" "tender_secrets_initial" {
  secret_id = aws_secretsmanager_secret.tender_secrets.id
  secret_string = jsonencode({
    OPENAI_API_KEY                       = "placeholder"
    OPENROUTER_API_KEY                   = "placeholder"
    ANTHROPIC_API_KEY                    = "placeholder"
    TENDER_TIGER_EMAIL                   = "placeholder"
    TENDER_TIGER_PASSWORD                = "placeholder"
    TENDER247_EMAIL                      = "placeholder"
    TENDER247_PASSWORD                   = "placeholder"
    HERMES_DASHBOARD_BASIC_AUTH_USERNAME = "admin"
    HERMES_DASHBOARD_BASIC_AUTH_PASSWORD = "changeme"
    HERMES_DASHBOARD_BASIC_AUTH_SECRET   = "random-secret-key-here"
    HERMES_DASHBOARD_TENDER_USERNAME     = "tender_user"
    HERMES_DASHBOARD_TENDER_PASSWORD     = "tender_pass"
    TEAMS_WEBHOOK_URL                    = "placeholder"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
