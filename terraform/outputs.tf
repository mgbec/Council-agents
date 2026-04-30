output "cloudfront_url" {
  description = "Frontend URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "api_endpoint" {
  description = "API Gateway endpoint (29s timeout — use function_url for long queries)"
  value       = "${aws_api_gateway_stage.prod.invoke_url}/council"
}

output "function_url" {
  description = "Lambda Function URL (no timeout limit — use this for the frontend)"
  value       = aws_lambda_function_url.proxy.function_url
}

output "s3_bucket" {
  description = "S3 bucket for frontend assets — run: aws s3 sync dist/ s3://<bucket>/"
  value       = aws_s3_bucket.frontend.id
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID (for frontend config)"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito App Client ID (for frontend config)"
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_domain" {
  description = "Cognito hosted UI domain"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.name}.amazoncognito.com"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}
