output "acm_certificate_validation_records" {
  description = "The DNS CNAME records to add to your DNS provider to validate the ACM certificate"
  value = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }
}
