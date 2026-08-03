terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-1" # Using Singapore as from render.yaml
}

variable "project_name" {
  type    = string
  default = "seple-tender"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "db_password" {
  type        = string
  description = "Password for the RDS PostgreSQL database"
  sensitive   = true
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

variable "base_domain" {
  type    = string
  default = "seple.in"
}
