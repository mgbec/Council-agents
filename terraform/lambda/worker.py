"""Worker Lambda: triggered by SQS, calls AgentCore, writes result to DynamoDB."""

import json
import os
import boto3

AGENTCORE_REGION = os.environ.get("AGENTCORE_REGION", "us-west-2")
agentcore = boto3.client("bedrock-agentcore", region_name=AGENTCORE_REGION)
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
TABLE_NAME = os.environ["TABLE_NAME"]


def lambda_handler(event, context):
    for record in event.get("Records", []):
        msg = json.loads(record["body"])
        request_id = msg["requestId"]
        prompt = msg["prompt"]
        session_id = msg["sessionId"]

        table = dynamodb.Table(TABLE_NAME)

        try:
            # Update status to PROCESSING
            table.update_item(
                Key={"requestId": request_id},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": "PROCESSING"},
            )

            print(f"Invoking AgentCore for {request_id}: {prompt[:100]}...")

            response = agentcore.invoke_agent_runtime(
                agentRuntimeArn=AGENT_RUNTIME_ARN,
                qualifier="DEFAULT",
                runtimeSessionId=session_id,
                payload=json.dumps({"prompt": prompt}).encode(),
            )

            result = json.loads(response["response"].read())
            print(f"AgentCore returned for {request_id}")

            # Store result
            table.update_item(
                Key={"requestId": request_id},
                UpdateExpression="SET #s = :s, #r = :r",
                ExpressionAttributeNames={"#s": "status", "#r": "result"},
                ExpressionAttributeValues={":s": "COMPLETE", ":r": json.dumps(result)},
            )

        except Exception as e:
            print(f"Error processing {request_id}: {type(e).__name__}: {e}")
            table.update_item(
                Key={"requestId": request_id},
                UpdateExpression="SET #s = :s, #e = :e",
                ExpressionAttributeNames={"#s": "status", "#e": "error"},
                ExpressionAttributeValues={":s": "FAILED", ":e": str(e)},
            )
