"""Submit Lambda: accepts request, stores in DynamoDB, sends to SQS."""

import json
import os
import time
import uuid
import urllib.request
import boto3

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
TABLE_NAME = os.environ["TABLE_NAME"]
QUEUE_URL = os.environ["QUEUE_URL"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_REGION = os.environ.get("COGNITO_REGION", "us-east-1")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": f"https://{ALLOWED_ORIGIN}",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
}

_jwks_cache = {}


def _get_jwks():
    if _jwks_cache.get("keys"):
        return _jwks_cache["keys"]
    url = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    _jwks_cache["keys"] = {k["kid"]: k for k in data["keys"]}
    return _jwks_cache["keys"]


def _base64url_decode(s):
    import base64
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _validate_jwt(token):
    if not token or not COGNITO_USER_POOL_ID:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header = json.loads(_base64url_decode(parts[0]))
        payload = json.loads(_base64url_decode(parts[1]))
        if payload.get("exp", 0) < time.time():
            return None
        expected_issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        if payload.get("iss") != expected_issuer:
            return None
        if COGNITO_CLIENT_ID:
            if payload.get("aud") != COGNITO_CLIENT_ID and payload.get("client_id") != COGNITO_CLIENT_ID:
                return None
        kid = header.get("kid")
        jwks = _get_jwks()
        if kid not in jwks:
            _jwks_cache.clear()
            jwks = _get_jwks()
            if kid not in jwks:
                return None
        return payload
    except Exception as e:
        print(f"JWT error: {e}")
        return None


def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # Validate JWT from Cognito authorizer claims or raw header
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims")
    if not claims:
        auth = (event.get("headers") or {}).get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else auth
        claims = _validate_jwt(token)
    if not claims:
        return {"statusCode": 401, "headers": CORS_HEADERS, "body": json.dumps({"error": "Unauthorized"})}

    user_sub = claims.get("sub", "anonymous")

    # Handle GET /council/{id} — poll for result
    path = event.get("path", "") or event.get("resource", "")
    path_params = event.get("pathParameters") or {}

    if method == "GET" and path_params.get("requestId"):
        request_id = path_params["requestId"]
        table = dynamodb.Table(TABLE_NAME)
        item = table.get_item(Key={"requestId": request_id}).get("Item")
        if not item:
            return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": "Not found"})}
        # Only allow users to see their own requests
        if item.get("userSub") != user_sub:
            return {"statusCode": 403, "headers": CORS_HEADERS, "body": json.dumps({"error": "Forbidden"})}
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"status": item["status"], "result": item.get("result")}),
        }

    # Handle POST /council — submit new request
    if method == "POST":
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("prompt", "")
        if not prompt:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"error": "prompt required"})}

        request_id = str(uuid.uuid4())
        session_id = body.get("session_id", f"web-{user_sub[:32]}-default").ljust(33, "0")

        # Store pending request
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item={
            "requestId": request_id,
            "userSub": user_sub,
            "prompt": prompt,
            "sessionId": session_id,
            "status": "PENDING",
            "createdAt": int(time.time()),
        })

        # Send to SQS for async processing
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps({
                "requestId": request_id,
                "prompt": prompt,
                "sessionId": session_id,
            }),
        )

        return {
            "statusCode": 202,
            "headers": CORS_HEADERS,
            "body": json.dumps({"requestId": request_id, "status": "PENDING"}),
        }

    return {"statusCode": 405, "headers": CORS_HEADERS, "body": json.dumps({"error": "Method not allowed"})}
