# ---------- Lambda: Proxy to AgentCore Runtime ----------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_agentcore" {
  statement {
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [var.agent_runtime_arn]
  }
}

resource "aws_iam_role_policy" "lambda_agentcore" {
  name   = "agentcore-invoke"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_agentcore.json
}

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/lambda_function.py"
  output_path = "${path.module}/lambda/lambda_function.zip"
}

resource "aws_lambda_function" "proxy" {
  function_name    = "${var.project_name}-proxy"
  role             = aws_iam_role.lambda.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  timeout          = 120
  memory_size      = 256
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      AGENT_RUNTIME_ARN  = var.agent_runtime_arn
      ALLOWED_ORIGIN     = aws_cloudfront_distribution.frontend.domain_name
      AGENTCORE_REGION   = "us-west-2"
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
      COGNITO_REGION       = data.aws_region.current.name
    }
  }
}

# Lambda Function URL — bypasses API Gateway's 29-second timeout
# The council takes 30-90 seconds, which exceeds API Gateway limits
resource "aws_lambda_function_url" "proxy" {
  function_name      = aws_lambda_function.proxy.function_name
  authorization_type = "NONE" # Auth handled by Cognito token validation in the frontend
  cors {
    allow_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}"]
    allow_methods = ["*"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }
}
