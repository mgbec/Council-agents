variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as prefix for resource naming"
  type        = string
  default     = "llm-council"
}

variable "agent_runtime_arn" {
  description = "ARN of the deployed AgentCore Runtime (from `agentcore status`)"
  type        = string
}

variable "cognito_callback_urls" {
  description = "Allowed callback URLs for Cognito (update after CloudFront is created)"
  type        = list(string)
  default     = ["http://localhost:5173/callback"]
}

variable "cognito_logout_urls" {
  description = "Allowed logout URLs for Cognito"
  type        = list(string)
  default     = ["http://localhost:5173"]
}
