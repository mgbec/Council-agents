"""Lambda proxy: receives authenticated requests and forwards to AgentCore Runtime."""

import json
import os
import boto3

client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "us-east-1"))
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": f"https://{ALLOWED_ORIGIN}",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("prompt", "")

        # Isolate sessions per authenticated user
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        user_sub = claims.get("sub", "anonymous")
        session_id = body.get("session_id", f"web-{user_sub[:32]}-default")

        # AgentCore requires session IDs of at least 33 characters
        session_id = session_id.ljust(33, "0")

        response = client.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            qualifier="DEFAULT",
            runtimeSessionId=session_id,
            payload=json.dumps({"prompt": prompt}).encode(),
        )

        result = json.loads(response["payload"].read())
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps(result)}

    except Exception as e:
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
