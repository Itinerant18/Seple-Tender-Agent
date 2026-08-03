resource "aws_acm_certificate" "cert" {
  domain_name               = var.base_domain
  subject_alternative_names = ["*.${var.base_domain}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${local.name_prefix}-cert"
  }
}
