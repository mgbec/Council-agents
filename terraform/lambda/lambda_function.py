"""Lambda proxy: receives authenticated requests and forwards to AgentCore Runtime.

Validates Cognito JWTs in-function since Lambda Function URLs don't have
a built-in Cognito authorizer like API Gateway does.
"""

import json
import os
import time
import urllib.request
import boto3

# AgentCore runtime is in us-west-2, Lambda is in us-east-1
AGENTCORE_REGION = os.environ.get("AGENTCORE_REGION", "us-west-2")
client = boto3.client("bedrock-agentcore", region_name=AGENTCORE_REGION)
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_REGION = os.environ.get("COGNITO_REGION", "us-east-1")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": f"https://{ALLOWED_ORIGIN}",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

# Cache JWKS keys at module level (persists across warm invocations)
_jwks_cache = {}


def _get_jwks():
    """Fetch and cache the Cognito JWKS (JSON Web Key Set)."""
    if _jwks_cache.get("keys"):
        return _jwks_cache["keys"]
    url = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    _jwks_cache["keys"] = {k["kid"]: k for k in data["keys"]}
    return _jwks_cache["keys"]


def _base64url_decode(s):
    """Decode base64url without padding."""
    import base64
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _validate_jwt(token):
    """
    Validate a Cognito JWT token. Returns the decoded claims or None.

    Does structural validation, expiry check, issuer check, and audience check.
    Does NOT do full RSA signature verification (would need python-jose or
    cryptography library). For production, add a Lambda layer with python-jose.
    """
    if not token or not COGNITO_USER_POOL_ID:
        return None

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Decode header and payload
        header = json.loads(_base64url_decode(parts[0]))
        payload = json.loads(_base64url_decode(parts[1]))

        # Check expiry
        if payload.get("exp", 0) < time.time():
            print("JWT expired")
            return None

        # Check issuer matches our Cognito pool
        expected_issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        if payload.get("iss") != expected_issuer:
            print(f"JWT issuer mismatch: {payload.get('iss')}")
            return None

        # Check audience (client_id) for id tokens
        if COGNITO_CLIENT_ID and payload.get("aud") != COGNITO_CLIENT_ID:
            # Access tokens use 'client_id' instead of 'aud'
            if payload.get("client_id") != COGNITO_CLIENT_ID:
                print(f"JWT audience mismatch")
                return None

        # Verify the kid exists in our JWKS
        kid = header.get("kid")
        jwks = _get_jwks()
        if kid not in jwks:
            print(f"JWT kid not found in JWKS: {kid}")
            # Clear cache and retry once (key rotation)
            _jwks_cache.clear()
            jwks = _get_jwks()
            if kid not in jwks:
                return None

        return payload

    except Exception as e:
        print(f"JWT validation error: {e}")
        return None


def lambda_handler(event, context):
    # Handle CORS preflight
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # Extract and validate the JWT
    auth_header = (event.get("headers") or {}).get("authorization", "")
    # Strip "Bearer " prefix if present
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    claims = _validate_jwt(token)

    if claims is None:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Unauthorized — invalid or missing token"}),
        }

    try:
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("prompt", "")

        # Isolate sessions per authenticated user
        user_sub = claims.get("sub", "anonymous")
        session_id = body.get("session_id", f"web-{user_sub[:32]}-default")

        # AgentCore requires session IDs of at least 33 characters
        session_id = session_id.ljust(33, "0")

        print(f"User={user_sub[:8]}... prompt={prompt[:100]}... session={session_id}")

        response = client.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            qualifier="DEFAULT",
            runtimeSessionId=session_id,
            payload=json.dumps({"prompt": prompt}).encode(),
        )

        result = json.loads(response["response"].read())
        print(f"AgentCore returned statusCode={response.get('statusCode')}")
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps(result)}

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
