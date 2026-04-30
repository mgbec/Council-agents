# LLM Council on Amazon Bedrock AgentCore

A reimplementation of [Karpathy's LLM Council](https://github.com/karpathy/llm-council) using Amazon Bedrock AgentCore primitives.

Instead of OpenRouter + FastAPI + JSON files, this version uses:

- **Amazon Bedrock** for multi-model access (Claude, Llama, Mistral, etc.)
- **AgentCore Runtime** for serverless hosting with session management
- **AgentCore Memory** for conversation persistence across sessions
- **Strands Agents** for orchestration

## Architecture

```
User Query
    ↓
AgentCore Runtime (Strands Agent)
    ↓
Stage 1: Parallel Bedrock model invocations → individual responses
    ↓
Stage 2: Anonymized peer ranking via Bedrock → evaluations + aggregate scores
    ↓
Stage 3: Chairman synthesis via Bedrock → final answer
    ↓
AgentCore Memory (conversation stored)
    ↓
Response returned to user
```

## Project Structure

This project spans three directories in the workspace:

```
llm-council/                      ← Original Karpathy project (reference only)
│   FastAPI + React + OpenRouter
│   Not modified — kept for comparison
│
llm-council-agentcore/            ← Agent source code, docs, and infra (this README)
│   ├── main.py                   ← AgentCore Runtime entry point
│   ├── council.py                ← 3-stage council orchestration logic
│   ├── bedrock_client.py         ← Bedrock Converse API client (replaces OpenRouter)
│   ├── config.py                 ← Model list, region, display names
│   ├── memory_integration.py     ← AgentCore Memory adapter (replaces JSON storage)
│   ├── setup_memory.py           ← One-time script to create a Memory resource
│   ├── requirements.txt          ← Python dependencies
│   ├── USERGUIDE.md              ← End-user documentation
│   └── terraform/                ← Infrastructure for the frontend
│       ├── main.tf               ← S3 + CloudFront
│       ├── cognito.tf            ← User authentication
│       ├── apigateway.tf         ← REST API with Cognito authorizer
│       ├── lambda.tf             ← Proxy function to AgentCore
│       ├── lambda/
│       │   └── lambda_function.py
│       ├── variables.tf
│       └── outputs.tf
│
LLMCouncil/                       ← AgentCore CLI project (run agentcore commands here)
    ├── agentcore/
    │   └── agentcore.json        ← CLI config — defines the agent, build type, etc.
    └── app/
        └── LLMCouncil/           ← Copy agent .py files here before deploying
```

**How they relate:** The `llm-council-agentcore/` directory contains the
source code and documentation. To deploy, copy the `.py` files and
`requirements.txt` into `LLMCouncil/app/LLMCouncil/` (the `codeLocation`
in `agentcore.json`), then run `agentcore deploy` from the `LLMCouncil/`
directory.

## Prerequisites

- AWS account with Bedrock model access enabled for your chosen models
- Python 3.10+
- AWS CLI configured (`aws configure`)
- `npm install -g @aws/agentcore` (provides the `agentcore` CLI)

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `config.py` to customize your council models. Models must be enabled
in your AWS Bedrock console under Model Access.

```python
COUNCIL_MODELS = [
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.meta.llama4-maverick-17b-instruct-v1:0",
    "mistral.mistral-large-2411-v1:0",
]
CHAIRMAN_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"
```

## Running Locally

```bash
# Start the agent as a local HTTP server on port 8080
python main.py

# Test it from another terminal
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the tradeoffs of microservices vs monoliths?"}'

# Or run in interactive terminal mode (no server)
python main.py --interactive
```

## Deploying to AgentCore Runtime

Deployment uses the `agentcore` CLI, which handles all the AWS infrastructure
for you. Here's what happens at each step:

**Important:** All `agentcore` CLI commands must be run from the directory
that contains the `agentcore/` folder (where `agentcore/agentcore.json` lives).
If you get "no agentcore project found", you're in the wrong directory.

### Step 1: Create project and add the agent

If starting fresh (scaffolds a new project directory with `agentcore/agentcore.json`):

```bash
agentcore create --name LLMCouncil --defaults
```

If you already have this code checked out, add the agent to an existing
project using "bring your own" (BYO) mode:

```bash
agentcore add agent \
  --name LLMCouncil \
  --type byo \
  --language Python \
  --code-location . \
  --entrypoint main.py \
  --build CodeZip \
  --memory none
```

This updates `agentcore/agentcore.json` with the agent definition — entry
point, build type (CodeZip = S3, or Container = ECR), network mode, etc.

You can also run `agentcore add agent` without flags for interactive mode,
which prompts you for each option.

### Step 2: Deploy

```bash
agentcore deploy
```

This is where the real work happens. `agentcore deploy` will:

1. **Package your code** — Zips `main.py`, `council.py`, `bedrock_client.py`,
   `config.py`, `memory_integration.py`, and `requirements.txt` into a
   deployment artifact.

2. **Upload to S3** — Pushes the zip to an S3 bucket in your account. (If
   using container mode instead of CodeZip, it builds an ARM64 Docker image
   and pushes to ECR.)

3. **Create/update the AgentCore Runtime** — Calls the
   `CreateAgentRuntime` API (or `UpdateAgentRuntime` on subsequent deploys).
   This provisions the serverless infrastructure that will host your agent.
   Each deploy creates a new immutable version.

4. **Create the DEFAULT endpoint** — On first deploy, a DEFAULT endpoint is
   automatically created pointing to version 1. On subsequent deploys, the
   DEFAULT endpoint auto-updates to the latest version.

5. **Create an IAM execution role** (if needed) — The role trusts
   `bedrock-agentcore.amazonaws.com` and includes permissions for Bedrock
   model invocation, CloudWatch Logs, and X-Ray tracing.

6. **Provision memory** (if configured) — If you enabled memory when adding
   the agent, it creates the AgentCore Memory resource and waits for it to
   become ACTIVE (30-180 seconds depending on STM vs LTM).

After deploy completes, you'll see output with the agent's ARN and endpoint.

### Deployment Modes: CodeZip (S3) vs Container (ECR)

AgentCore supports two ways to get your code into the runtime. The choice
is made at configure time via `--deployment-type`.

#### Option A: CodeZip / S3 (default — recommended for this project)

```bash
agentcore add agent \
  --name LLMCouncil \
  --type byo \
  --code-location . \
  --entrypoint main.py \
  --build CodeZip

agentcore deploy
```

How it works:
1. The CLI zips your Python source files and `requirements.txt`.
2. Uploads the zip to an S3 bucket managed by AgentCore in your account.
3. At runtime, AgentCore unpacks the zip, installs dependencies via pip
   on a managed Python runtime (3.10–3.13), and starts your entry point.

Constraints: max 250 MB zipped / 750 MB unzipped. No Docker required on
your machine.

This is the right choice when your project is pure Python with
pip-installable dependencies — which this project is.

#### Option B: Container / ECR

```bash
agentcore add agent \
  --name LLMCouncil \
  --type byo \
  --code-location . \
  --entrypoint main.py \
  --build Container

agentcore deploy
```

How it works:
1. The CLI builds an ARM64 Docker image from your project. (You need
   Docker, Finch, or Podman installed locally — or use CodeBuild.)
2. Pushes the image to an ECR repository (`--ecr auto` creates one for you,
   or pass an existing repo name).
3. Calls `CreateAgentRuntime` with the ECR image URI.
4. At runtime, AgentCore pulls the image and runs it in a Firecracker
   microVM.

The image must be ARM64 — `docker buildx build --platform linux/arm64`.
It must expose `/invocations` on port 8080 and a `/ping` health check.

Use container mode when you need:
- System-level packages (e.g., `apt-get install ffmpeg`)
- Custom binaries or native libraries not available via pip
- A specific OS base image or precise control over the runtime
- Reproducible builds where you lock the entire filesystem

You can also build locally and deploy to the cloud in one step:

```bash
agentcore deploy --local-build
```

This builds the image on your machine (faster iteration than CodeBuild)
and pushes it to ECR.

#### Side-by-side comparison

| | CodeZip (S3) | Container (ECR) |
|---|---|---|
| Configure flag | `--deployment-type direct_code_deploy` (default) | `--deployment-type container` |
| Docker required | No | Yes (or CodeBuild) |
| Max size | 250 MB zip / 750 MB unzipped | ECR image limits |
| Dependency install | pip at deploy time | Baked into image |
| Python version | `--runtime PYTHON_3_13` etc. | Whatever's in your Dockerfile |
| System packages | Not supported | Full control |
| Build speed | Fast (just zip + upload) | Slower (image build + push) |
| Best for | Pure Python projects | Complex runtimes, native deps |

### Step 3: Invoke

```bash
# Basic invocation
agentcore invoke '{"prompt": "What are the tradeoffs of microservices vs monoliths?"}'

# With a session ID (for multi-turn conversations)
agentcore invoke '{"prompt": "Tell me more about the scaling aspect"}' \
  --session-id "my-session-abc123def456ghi789jkl012"
```

When you invoke, AgentCore:
- Spins up an isolated microVM (Firecracker) for your session
- Runs your agent code inside it
- Returns the response
- Keeps the microVM warm for 15 minutes (configurable) for follow-up calls
- Auto-terminates after idle timeout

### Step 4: Check status

```bash
agentcore status
```

Shows deployment status, endpoint readiness, memory configuration, and
CloudWatch log paths.

### Step 5: Stop sessions / Tear down

```bash
# Stop an active session early (saves cost vs waiting for idle timeout)
agentcore stop-session

# Destroy all resources when done
agentcore destroy
```

`agentcore destroy` removes the runtime, endpoint, ECR images, CodeBuild
project, IAM role, and memory resources.

## Optional: AgentCore Memory for Persistence

By default the agent runs statelessly. To enable conversation persistence
across sessions:

```bash
# Create a memory resource
python setup_memory.py

# Set the returned ID
export MEMORY_ID=<your-memory-id>

# Redeploy with memory
agentcore deploy --env MEMORY_ID=$MEMORY_ID
```

This replaces the JSON file storage from the original project. AgentCore
Memory gives you semantic search over past conversations and automatic
extraction of user preferences and facts.

## Hosting a Frontend on AWS

The architecture below keeps credentials server-side, authenticates users
via Cognito, and serves the React app from CloudFront.

Note: API Gateway REST APIs have a hard 29-second timeout, but the council
takes 30–90 seconds. To work around this, the frontend calls a Lambda
Function URL directly (no timeout limit). The Lambda validates the Cognito
JWT in-function to enforce authentication.

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                │
│  React app (CloudFront + S3)                            │
│       │                                                 │
│       │ 1. User signs in via Cognito                    │
│       │    → receives JWT id_token                      │
│       │                                                 │
│       │ 2. POST to Lambda Function URL                  │
│       │    (Authorization: Bearer <JWT>)                │
│       ▼                                                 │
│  Lambda Function URL                                    │
│       │  Validates Cognito JWT (issuer, expiry, aud)    │
│       │  Calls bedrock-agentcore InvokeAgentRuntime     │
│       ▼                                                 │
│  AgentCore Runtime (LLM Council agent)                  │
└─────────────────────────────────────────────────────────┘
```

### Step 1: Create a Cognito User Pool

This handles user sign-up/sign-in and issues JWTs that API Gateway validates.

```bash
# Create the user pool
aws cognito-idp create-user-pool \
  --pool-name llm-council-users \
  --auto-verified-attributes email \
  --username-attributes email \
  --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":true,"RequireLowercase":true,"RequireNumbers":true,"RequireSymbols":false}}' \
  --query 'UserPool.Id' --output text
# → returns POOL_ID (e.g., us-east-1_AbCdEfGhI)

# Create an app client (no secret — public client for SPA)
aws cognito-idp create-user-pool-client \
  --user-pool-id <POOL_ID> \
  --client-name llm-council-web \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_SRP_AUTH ALLOW_REFRESH_TOKEN_AUTH \
  --supported-identity-providers COGNITO \
  --callback-urls '["https://<your-cloudfront-domain>/callback"]' \
  --logout-urls '["https://<your-cloudfront-domain>"]' \
  --allowed-o-auth-flows code \
  --allowed-o-auth-scopes openid email profile \
  --allowed-o-auth-flows-user-pool-client \
  --query 'UserPoolClient.ClientId' --output text
# → returns CLIENT_ID

# Create a domain for the hosted login UI
aws cognito-idp create-user-pool-domain \
  --user-pool-id <POOL_ID> \
  --domain llm-council-<your-unique-suffix>
```

### Step 2: Create the Lambda proxy function

This is a thin function that receives authenticated requests from API
Gateway and forwards them to AgentCore Runtime. The AgentCore ARN and
AWS credentials never leave the server side.

```python
# lambda_function.py
import json
import boto3
import os

client = boto3.client("bedrock-agentcore", region_name=os.environ["AWS_REGION"])
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]

def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    prompt = body.get("prompt", "")

    # Use Cognito sub as session namespace for isolation
    user_sub = event["requestContext"]["authorizer"]["claims"]["sub"]
    session_id = body.get("session_id", f"web-{user_sub[:32]}-default")

    # Pad session_id to meet 33-char minimum
    session_id = session_id.ljust(33, "0")

    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        qualifier="DEFAULT",
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt}).encode(),
    )

    result = json.loads(response["payload"].read())

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": f"https://{os.environ['ALLOWED_ORIGIN']}",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(result),
    }
```

Deploy it:

```bash
# Zip and create the function
zip lambda_function.zip lambda_function.py

aws lambda create-function \
  --function-name llm-council-proxy \
  --runtime python3.13 \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_function.zip \
  --role <LAMBDA_EXECUTION_ROLE_ARN> \
  --timeout 120 \
  --memory-size 256 \
  --environment "Variables={AGENT_RUNTIME_ARN=<your-agentcore-arn>,ALLOWED_ORIGIN=<your-cloudfront-domain>}"
```

The Lambda execution role needs:
- `bedrock-agentcore:InvokeAgentRuntime` on your agent's ARN
- Basic Lambda execution (`AWSLambdaBasicExecutionRole`)

### Step 3: Create API Gateway with Cognito authorizer

```bash
# Create the REST API
aws apigateway create-rest-api \
  --name llm-council-api \
  --endpoint-configuration types=REGIONAL \
  --query 'id' --output text
# → returns API_ID

# Create Cognito authorizer
aws apigateway create-authorizer \
  --rest-api-id <API_ID> \
  --name cognito-auth \
  --type COGNITO_USER_POOLS \
  --provider-arns "arn:aws:cognito-idp:<region>:<account>:userpool/<POOL_ID>" \
  --identity-source "method.request.header.Authorization" \
  --query 'id' --output text
# → returns AUTHORIZER_ID

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources \
  --rest-api-id <API_ID> \
  --query 'items[?path==`/`].id' --output text)

# Create /council resource
aws apigateway create-resource \
  --rest-api-id <API_ID> \
  --parent-id $ROOT_ID \
  --path-part council \
  --query 'id' --output text
# → returns RESOURCE_ID

# Add POST method with Cognito auth
aws apigateway put-method \
  --rest-api-id <API_ID> \
  --resource-id <RESOURCE_ID> \
  --http-method POST \
  --authorization-type COGNITO_USER_POOLS \
  --authorizer-id <AUTHORIZER_ID>

# Add OPTIONS method for CORS (no auth)
aws apigateway put-method \
  --rest-api-id <API_ID> \
  --resource-id <RESOURCE_ID> \
  --http-method OPTIONS \
  --authorization-type NONE

# Wire POST to Lambda
aws apigateway put-integration \
  --rest-api-id <API_ID> \
  --resource-id <RESOURCE_ID> \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "arn:aws:apigateway:<region>:lambda:path/2015-03-31/functions/<LAMBDA_ARN>/invocations"

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission \
  --function-name llm-council-proxy \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:<region>:<account>:<API_ID>/*/POST/council"

# Deploy the API
aws apigateway create-deployment \
  --rest-api-id <API_ID> \
  --stage-name prod
```

Your API endpoint will be:
`https://<API_ID>.execute-api.<region>.amazonaws.com/prod/council`

### Step 4: Build and deploy the React frontend

Adapt the original `llm-council/frontend` — replace the `api.js` to
authenticate via Cognito and call API Gateway instead of localhost:

```javascript
// frontend/src/api.js (adapted for AWS)
import { CognitoUserPool, AuthenticationDetails, CognitoUser } from 'amazon-cognito-identity-js';

const API_BASE = 'https://<API_ID>.execute-api.<region>.amazonaws.com/prod';

const poolData = {
  UserPoolId: '<POOL_ID>',
  ClientId: '<CLIENT_ID>',
};
const userPool = new CognitoUserPool(poolData);

function getIdToken() {
  const user = userPool.getCurrentUser();
  return new Promise((resolve, reject) => {
    if (!user) return reject(new Error('Not signed in'));
    user.getSession((err, session) => {
      if (err) return reject(err);
      resolve(session.getIdToken().getJwtToken());
    });
  });
}

export const api = {
  async sendMessage(prompt, sessionId) {
    const token = await getIdToken();
    const response = await fetch(`${API_BASE}/council`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token,
      },
      body: JSON.stringify({ prompt, session_id: sessionId }),
    });
    if (!response.ok) throw new Error('Request failed');
    return response.json();
  },
};
```

Then build and upload to S3:

```bash
cd frontend
npm run build

# Create S3 bucket for static hosting
aws s3 mb s3://llm-council-frontend-<unique-suffix>

# Upload build output
aws s3 sync dist/ s3://llm-council-frontend-<unique-suffix>/ \
  --cache-control "public, max-age=31536000" \
  --exclude "index.html"

aws s3 cp dist/index.html s3://llm-council-frontend-<unique-suffix>/ \
  --cache-control "no-cache"
```

### Step 5: Create CloudFront distribution

```bash
# Create Origin Access Control for S3
aws cloudfront create-origin-access-control \
  --origin-access-control-config \
    "Name=llm-council-oac,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3"

# Create the distribution
aws cloudfront create-distribution \
  --distribution-config '{
    "CallerReference": "llm-council-'$(date +%s)'",
    "DefaultRootObject": "index.html",
    "Origins": {
      "Quantity": 1,
      "Items": [{
        "Id": "S3Origin",
        "DomainName": "llm-council-frontend-<unique-suffix>.s3.<region>.amazonaws.com",
        "S3OriginConfig": { "OriginAccessIdentity": "" },
        "OriginAccessControlId": "<OAC_ID>"
      }]
    },
    "DefaultCacheBehavior": {
      "TargetOriginId": "S3Origin",
      "ViewerProtocolPolicy": "redirect-to-https",
      "AllowedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] },
      "ForwardedValues": { "QueryString": false, "Cookies": { "Forward": "none" } },
      "MinTTL": 0
    },
    "ViewerCertificate": { "CloudFrontDefaultCertificate": true },
    "Enabled": true,
    "Comment": "LLM Council Frontend"
  }'
```

Then update the S3 bucket policy to allow CloudFront access:

```bash
aws s3api put-bucket-policy \
  --bucket llm-council-frontend-<unique-suffix> \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "AllowCloudFront",
      "Effect": "Allow",
      "Principal": { "Service": "cloudfront.amazonaws.com" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::llm-council-frontend-<unique-suffix>/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::<account>:distribution/<DIST_ID>"
        }
      }
    }]
  }'
```

### Security summary

| Layer | What it does |
|---|---|
| Cognito | Authenticates users, issues JWTs. No anonymous access. |
| Lambda (JWT validation) | Validates Cognito JWT in-function (issuer, expiry, audience, JWKS key ID). Rejects requests without a valid token. |
| Lambda (session isolation) | Scopes AgentCore sessions per user via Cognito `sub` claim. |
| Lambda Function URL | CORS restricted to CloudFront origin only. |
| CloudFront | HTTPS-only, no direct S3 access. |
| S3 bucket | Private, accessible only via CloudFront OAC. |
| AgentCore Runtime | Runs in isolated microVMs. No public endpoint exposed to browsers. |

### Why Lambda Function URL instead of API Gateway?

API Gateway REST APIs have a hard 29-second integration timeout. The LLM
Council takes 30–90 seconds (3 models × 2 stages of parallel calls + 1
chairman synthesis). There's no way to increase this limit. Lambda Function
URLs have no such timeout, so the council can run to completion. The
tradeoff is that JWT validation happens in Lambda code rather than at the
gateway level.

### What this gives you

- Users sign in via Cognito hosted UI (or embed the login form)
- Each user gets isolated sessions (keyed by their Cognito `sub`)
- The AgentCore runtime ARN is never exposed to the client
- All traffic is HTTPS
- You can add rate limiting on API Gateway, WAF rules on CloudFront, and Cognito MFA — all standard AWS controls

### Deploying with Terraform

The `terraform/` directory contains a validated Terraform config that
provisions all of the above in one shot. Structure:

```
terraform/
├── main.tf          # S3 bucket, CloudFront distribution
├── cognito.tf       # User pool, app client, hosted UI domain
├── apigateway.tf    # REST API (kept for reference, not used by frontend)
├── lambda.tf        # Proxy function + IAM role + Function URL
├── lambda/
│   └── lambda_function.py   # JWT validation + AgentCore invocation
├── variables.tf     # Inputs (region, agent ARN, etc.)
└── outputs.tf       # URLs, IDs you'll need for the frontend
```

Usage:

```bash
cd terraform

terraform init

# Preview what will be created
terraform plan -var="agent_runtime_arn=arn:aws:bedrock-agentcore:us-east-1:123456789:runtime/LLMCouncil"

# Apply
terraform apply -var="agent_runtime_arn=<your-arn-from-agentcore-status>"
```

Get your agent ARN with `agentcore status` after deploying the backend.

After `terraform apply`, the outputs tell you everything you need:

```
cloudfront_url       = "https://d1234abcdef.cloudfront.net"
api_endpoint         = "https://abc123.execute-api.us-east-1.amazonaws.com/prod/council"
function_url         = "https://xxxx.lambda-url.us-east-1.on.aws/"
s3_bucket            = "llm-council-frontend-xxxx"
cognito_user_pool_id = "us-east-1_AbCdEfGhI"
cognito_client_id    = "1a2b3c4d5e6f7g8h9i"
cognito_domain       = "https://llm-council-123456789.auth.us-east-1.amazoncognito.com"
```

The frontend uses `function_url` (not `api_endpoint`) to avoid the
29-second API Gateway timeout. Update `frontend/src/api.js` with the
`function_url` value before building.

Then build the frontend with those values and upload:

```bash
# Build the React app (set env vars or update api.js with the outputs)
cd ../frontend
npm run build

# Upload to S3
aws s3 sync dist/ s3://$(terraform -chdir=../terraform output -raw s3_bucket)/

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

To tear everything down:

```bash
# Empty the S3 bucket first (force_destroy is enabled, but good practice)
aws s3 rm s3://$(terraform output -raw s3_bucket) --recursive

terraform destroy -var="agent_runtime_arn=<your-arn>"
```

## What's Different from the Original

| Original (llm-council)         | This version (AgentCore)                    |
|--------------------------------|---------------------------------------------|
| OpenRouter API + API key       | Amazon Bedrock (native AWS, no extra keys)  |
| FastAPI server on port 8001    | AgentCore Runtime (serverless, auto-scaling) |
| JSON files in `data/`          | AgentCore Memory (semantic search, LTM)     |
| Manual server management       | `agentcore deploy` / `agentcore destroy`    |
| React frontend on localhost    | CloudFront + S3 + Cognito auth              |
| `start.sh` to run both servers | Single `agentcore deploy` + CDK/CLI infra   |

## References

- **Original LLM Council** — [github.com/karpathy/llm-council](https://github.com/karpathy/llm-council). The project this is based on, by Andrej Karpathy. 3-stage LLM deliberation using OpenRouter, FastAPI, and React.
- **Amazon Bedrock** — [aws.amazon.com/bedrock](https://aws.amazon.com/bedrock/). Managed service for foundation models. Provides the Converse API used to query Claude, Llama, Mistral, and other models.
- **Amazon Bedrock AgentCore** — [aws.amazon.com/bedrock/agentcore](https://aws.amazon.com/bedrock/agentcore/). Serverless runtime, memory, gateway, and observability for AI agents.
- **AgentCore CLI (`@aws/agentcore`)** — [github.com/aws/agentcore-cli](https://github.com/aws/agentcore-cli). The npm CLI for creating, deploying, and managing AgentCore projects.
- **AgentCore Starter Toolkit docs** — [aws.github.io/bedrock-agentcore-starter-toolkit](https://aws.github.io/bedrock-agentcore-starter-toolkit/). Guides, examples, and API reference for AgentCore.
- **Strands Agents** — [strandsagents.com](https://strandsagents.com/). The agent framework used for orchestration, integrated with AgentCore Runtime.
- **Bedrock Converse API** — [docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-call.html](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-call.html). The unified API for multi-model inference used in `bedrock_client.py`.
- **Amazon Cognito** — [docs.aws.amazon.com/cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/what-is-amazon-cognito.html). User authentication service used in the frontend architecture.
- **Terraform AWS Provider** — [registry.terraform.io/providers/hashicorp/aws](https://registry.terraform.io/providers/hashicorp/aws/latest/docs). Used for the frontend infrastructure-as-code in `terraform/`.
