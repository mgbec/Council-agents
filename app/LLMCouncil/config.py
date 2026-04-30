"""Configuration for the LLM Council on Bedrock AgentCore."""

import os

# AWS Region for Bedrock
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Council members - Bedrock model identifiers
# Enable these in your AWS Bedrock console under Model Access
COUNCIL_MODELS = [
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.meta.llama4-maverick-17b-instruct-v1:0",
    "mistral.mistral-large-2402-v1:0",
]

# Chairman model - synthesizes the final response
CHAIRMAN_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Friendly display names for models
MODEL_DISPLAY_NAMES = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "Claude Sonnet 4.5",
    "us.meta.llama4-maverick-17b-instruct-v1:0": "Llama 4 Maverick",
    "mistral.mistral-large-2402-v1:0": "Mistral Large",
}

# AgentCore Memory ID (set after running setup_memory.py, or leave None to skip)
MEMORY_ID = os.getenv("MEMORY_ID")
