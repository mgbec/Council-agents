# ---------- IAM ----------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Submit Lambda role (DynamoDB + SQS)
resource "aws_iam_role" "submit_lambda" {
  name               = "${var.project_name}-submit-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "submit_basic" {
  role       = aws_iam_role.submit_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "submit_dynamo_sqs" {
  name = "dynamo-sqs"
  role = aws_iam_role.submit_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.requests.arn
      },
      {
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.council.arn
      },
    ]
  })
}

# Worker Lambda role (DynamoDB + AgentCore + SQS)
resource "aws_iam_role" "worker_lambda" {
  name               = "${var.project_name}-worker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_basic" {
  role       = aws_iam_role.worker_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "worker_permissions" {
  name = "worker-permissions"
  role = aws_iam_role.worker_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["dynamodb:UpdateItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.requests.arn
      },
      {
        Action   = ["bedrock-agentcore:InvokeAgentRuntime"]
        Effect   = "Allow"
        Resource = ["${var.agent_runtime_arn}", "${var.agent_runtime_arn}/*"]
      },
      {
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.council.arn
      },
    ]
  })
}

# ---------- DynamoDB ----------

resource "aws_dynamodb_table" "requests" {
  name         = "${var.project_name}-requests"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "requestId"

  attribute {
    name = "requestId"
    type = "S"
  }

  ttl {
    attribute_name = "createdAt"
    enabled        = false # Enable and set TTL if you want auto-cleanup
  }
}

# ---------- SQS ----------

resource "aws_sqs_queue" "council" {
  name                       = "${var.project_name}-council-queue"
  visibility_timeout_seconds = 360 # Must be >= worker Lambda timeout
  message_retention_seconds  = 3600
}

# ---------- Submit Lambda ----------

data "archive_file" "submit" {
  type        = "zip"
  source_file = "${path.module}/lambda/submit.py"
  output_path = "${path.module}/lambda/submit.zip"
}

resource "aws_lambda_function" "submit" {
  function_name    = "${var.project_name}-submit"
  role             = aws_iam_role.submit_lambda.arn
  handler          = "submit.lambda_handler"
  runtime          = "python3.13"
  timeout          = 10
  memory_size      = 128
  filename         = data.archive_file.submit.output_path
  source_code_hash = data.archive_file.submit.output_base64sha256

  environment {
    variables = {
      TABLE_NAME           = aws_dynamodb_table.requests.name
      QUEUE_URL            = aws_sqs_queue.council.url
      ALLOWED_ORIGIN       = aws_cloudfront_distribution.frontend.domain_name
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
      COGNITO_REGION       = data.aws_region.current.name
    }
  }
}

# ---------- Worker Lambda ----------

data "archive_file" "worker" {
  type        = "zip"
  source_file = "${path.module}/lambda/worker.py"
  output_path = "${path.module}/lambda/worker.zip"
}

resource "aws_lambda_function" "worker" {
  function_name    = "${var.project_name}-worker"
  role             = aws_iam_role.worker_lambda.arn
  handler          = "worker.lambda_handler"
  runtime          = "python3.13"
  timeout          = 300
  memory_size      = 256
  filename         = data.archive_file.worker.output_path
  source_code_hash = data.archive_file.worker.output_base64sha256

  environment {
    variables = {
      AGENT_RUNTIME_ARN = var.agent_runtime_arn
      TABLE_NAME        = aws_dynamodb_table.requests.name
      AGENTCORE_REGION  = "us-west-2"
    }
  }
}

# SQS trigger for worker
resource "aws_lambda_event_source_mapping" "sqs_worker" {
  event_source_arn = aws_sqs_queue.council.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1
}
