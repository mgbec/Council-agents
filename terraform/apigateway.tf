# ---------- API Gateway: HTTPS endpoint with Cognito auth ----------

resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-api"
  description = "LLM Council API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# Cognito authorizer
resource "aws_api_gateway_authorizer" "cognito" {
  name            = "cognito-auth"
  rest_api_id     = aws_api_gateway_rest_api.main.id
  type            = "COGNITO_USER_POOLS"
  identity_source = "method.request.header.Authorization"
  provider_arns   = [aws_cognito_user_pool.main.arn]
}

# /council resource
resource "aws_api_gateway_resource" "council" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "council"
}

# POST /council — submit a new request
resource "aws_api_gateway_method" "council_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.council.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "council_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.council.id
  http_method             = aws_api_gateway_method.council_post.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.submit.invoke_arn
}

# OPTIONS /council — CORS preflight
resource "aws_api_gateway_method" "council_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.council.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "council_options" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.council.id
  http_method             = aws_api_gateway_method.council_options.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.submit.invoke_arn
}

# /council/{requestId} resource — for polling results
resource "aws_api_gateway_resource" "council_request" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.council.id
  path_part   = "{requestId}"
}

# GET /council/{requestId} — poll for result
resource "aws_api_gateway_method" "council_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.council_request.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id

  request_parameters = {
    "method.request.path.requestId" = true
  }
}

resource "aws_api_gateway_integration" "council_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.council_request.id
  http_method             = aws_api_gateway_method.council_get.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.submit.invoke_arn
}

# OPTIONS /council/{requestId} — CORS preflight
resource "aws_api_gateway_method" "council_request_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.council_request.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "council_request_options" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.council_request.id
  http_method             = aws_api_gateway_method.council_request_options.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.submit.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# Deploy
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  depends_on = [
    aws_api_gateway_integration.council_post,
    aws_api_gateway_integration.council_options,
    aws_api_gateway_integration.council_get,
    aws_api_gateway_integration.council_request_options,
  ]

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.council.id,
      aws_api_gateway_resource.council_request.id,
      aws_api_gateway_method.council_post.id,
      aws_api_gateway_method.council_get.id,
      aws_api_gateway_integration.council_post.id,
      aws_api_gateway_integration.council_get.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = "prod"
}
