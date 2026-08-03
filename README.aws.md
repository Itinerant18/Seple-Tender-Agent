# AWS Deployment Guide for SEPLE Tender Platform

This directory contains the Terraform configuration to deploy the SEPLE Tender Platform to AWS.

## Architecture

- **ECS Fargate**: Runs the `tender-api` (FastAPI) and `hermes-agent` (Agent UI).
- **EventBridge + ECS Task**: Runs the `tender-scanner` on a cron schedule (`00:30 UTC`).
- **RDS PostgreSQL**: Hosts the main `tenders` database.
- **EFS (Elastic File System)**: Provides persistent storage for Playwright browser sessions (avoiding bot detection) and Seple T Agent state.
- **ALB (Application Load Balancer)**: Routes traffic based on host headers to the API or the Dashboard.
- **Secrets Manager**: Securely stores API keys and credentials.

## Prerequisites

1. Install [Terraform](https://developer.hashicorp.com/terraform/downloads).
2. Install [AWS CLI](https://aws.amazon.com/cli/).
3. Configure AWS CLI with appropriate credentials (`aws configure`).
4. Ensure Docker is running.

## Deployment Steps

### 1. Initialize and Apply Terraform

Navigate to the `aws-terraform` directory:

```bash
cd aws-terraform
terraform init
terraform apply -var="db_password=Seple#123!"
```

*(Note: In production, do not pass passwords via CLI. Use a `terraform.tfvars` file or environment variables like `TF_VAR_db_password`)*

This process takes 10-15 minutes (RDS creation is the slowest part). Once complete, take note of the outputs (e.g., ECR repository URLs, ALB DNS name) which you can view in the AWS Console.

### 2. Update Secrets in AWS Secrets Manager

Terraform creates a secret named `seple-tender-prod-secrets` in AWS Secrets Manager with placeholder values.
Go to the AWS Console -> Secrets Manager, find this secret, click **Retrieve secret value** -> **Edit**, and fill in your actual API keys and credentials:

- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY` (if used)
- `TENDER_TIGER_EMAIL` / `TENDER_TIGER_PASSWORD`
- `TENDER247_EMAIL` / `TENDER247_PASSWORD`
- `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` / `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`
- `HERMES_DASHBOARD_BASIC_AUTH_SECRET` (generate a random string)

### 3. Build and Push Docker Images to ECR

Use the provided script to build your local Docker images and push them to the new Amazon ECR repositories.

From the repository root, run:

```bash
chmod +x scripts/deploy-aws.sh
./scripts/deploy-aws.sh <AWS_REGION> <AWS_ACCOUNT_ID>
```

Example: `./scripts/deploy-aws.sh ap-southeast-1 123456789012`

### 4. Domain Routing (DNS)

Terraform provisions an Application Load Balancer (ALB). Find its DNS name in the EC2 Console under Load Balancers.
Create CNAME records in your DNS provider:

- `api.yourdomain.com` -> ALB DNS Name
- `agent.yourdomain.com` -> ALB DNS Name

The ALB listener rules are configured to route based on the host header.

### 5. Start the Services

Once the images are pushed to ECR:

1. Go to the ECS Console.
2. Find the `seple-tender-prod-cluster`.
3. The services `seple-tender-prod-api-svc` and `seple-tender-prod-agent-svc` should automatically pull the images and start running.
4. For the scanner, EventBridge will trigger it automatically at 00:30 UTC. You can also manually trigger the `seple-tender-prod-scanner` task definition via the ECS console to test it immediately.

## Chokepoint Invariant

This architecture ensures that the agent gateway (`hermes-agent`) remains the single entrypoint and orchestrator for all agentic interactions, adhering to the project's chokepoint invariant. Persistent state across horizontal scale-outs is managed by EFS, ensuring context is not fragmented.
