# LLM Council — Architecture Diagram

## Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   USER (Browser)                                                                │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  React Frontend (CloudFront + S3)                                       │   │
│   │                                                                         │   │
│   │  1. Sign in via Cognito (email/password → JWT)                          │   │
│   │  2. POST /council → submit question                                     │   │
│   │  3. GET /council/{id} → poll every 5s until COMPLETE                    │   │
│   └────────────────────────────────┬────────────────────────────────────────┘   │
│                                    │ HTTPS                                      │
└────────────────────────────────────┼────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   AWS CLOUD                                                                     │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  CloudFront Distribution                                                │   │
│   │  • HTTPS termination                                                    │   │
│   │  • Serves static React assets from S3                                   │   │
│   │  • Origin Access Control (no public S3)                                 │   │
│   └────────────────────────────────┬────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  S3 Bucket (Private)                                                    │   │
│   │  • index.html, JS, CSS                                                  │   │
│   │  • Only accessible via CloudFront OAC                                   │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  API Gateway (REST API)                                                 │   │
│   │  • Cognito User Pool Authorizer (validates JWT on every request)        │   │
│   │  • POST /council         → Submit Lambda                                │   │
│   │  • GET  /council/{id}    → Submit Lambda                                │   │
│   │  • OPTIONS (CORS)        → Submit Lambda                                │   │
│   └───────────────┬─────────────────────────────────────────────────────────┘   │
│                   │                                                             │
│                   ▼                                                             │
│   ┌───────────────────────────────────┐     ┌───────────────────────────────┐   │
│   │  Cognito User Pool                │     │  Submit Lambda (10s timeout)  │   │
│   │  • Email/password auth            │     │                               │   │
│   │  • Issues JWT id_tokens           │     │  POST: validates JWT,         │   │
│   │  • Self-service sign-up           │     │    writes to DynamoDB,        │   │
│   │  • Token refresh                  │     │    sends SQS message          │   │
│   │                                   │     │    → returns {requestId}      │   │
│   │                                   │     │                               │   │
│   │                                   │     │  GET: reads DynamoDB,         │   │
│   │                                   │     │    returns {status, result}   │   │
│   └───────────────────────────────────┘     └──────────┬──────────┬─────────┘   │
│                                                        │          │             │
│                                              write     │          │ read        │
│                                                        ▼          ▼             │
│                                             ┌────────────────────────────────┐  │
│                                             │  DynamoDB Table                │  │
│                                             │  (llm-council-requests)        │  │
│                                             │                                │  │
│                                             │  Key: requestId                │  │
│                                             │  Fields: userSub, prompt,      │  │
│                                             │    sessionId, status, result   │  │
│                                             │                                │  │
│                                             │  Status: PENDING →             │  │
│                                             │    PROCESSING → COMPLETE       │  │
│                                             └────────────────────────────────┘  │
│                                                        ▲                        │
│                                                        │ update                 │
│                                                        │                        │
│   ┌────────────────────────────┐     ┌─────────────────┴────────────────────┐   │
│   │  SQS Queue                 │     │  Worker Lambda (150s timeout)        │   │
│   │  (llm-council-council-     │────▶│                                      │   │
│   │   queue)                   │     │  • Triggered by SQS                  │   │
│   │                            │     │  • Calls AgentCore Runtime           │   │
│   │  • Visibility: 180s       │     │  • Writes result to DynamoDB         │   │
│   │  • Retention: 1 hour      │     │  • No public endpoint                │   │
│   │  • Batch size: 1          │     │                                      │   │
│   └────────────────────────────┘     └──────────────────┬───────────────────┘   │
│                                                         │                       │
│                                                         │ InvokeAgentRuntime    │
│                                                         ▼                       │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  AgentCore Runtime (us-west-2)                                          │   │
│   │  • Serverless, isolated microVMs (Firecracker)                          │   │
│   │  • Session management                                                   │   │
│   │  • OpenTelemetry auto-instrumentation                                   │   │
│   │                                                                         │   │
│   │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│   │  │  LLM Council Agent (main.py)                                    │    │   │
│   │  │                                                                 │    │   │
│   │  │  Stage 1: Query all models in parallel                          │    │   │
│   │  │     ├── Claude Sonnet 4.5                                       │    │   │
│   │  │     ├── Llama 4 Maverick                                        │    │   │
│   │  │     └── Mistral Large                                           │    │   │
│   │  │                                                                 │    │   │
│   │  │  Stage 2: Anonymized peer ranking (parallel)                    │    │   │
│   │  │     ├── Claude ranks Response A, B, C                           │    │   │
│   │  │     ├── Llama ranks Response A, B, C                            │    │   │
│   │  │     └── Mistral ranks Response A, B, C                          │    │   │
│   │  │                                                                 │    │   │
│   │  │  Stage 3: Chairman synthesis                                    │    │   │
│   │  │     └── Claude Sonnet 4.5 (chairman)                            │    │   │
│   │  └─────────────────────────────────────────────────────────────────┘    │   │
│   │                              │                                          │   │
│   │                              ▼                                          │   │
│   │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│   │  │  Amazon Bedrock (Converse API)                                  │    │   │
│   │  │  • us.anthropic.claude-sonnet-4-5-20250929-v1:0                 │    │   │
│   │  │  • us.meta.llama4-maverick-17b-instruct-v1:0                    │    │   │
│   │  │  • mistral.mistral-large-2402-v1:0                              │    │   │
│   │  └─────────────────────────────────────────────────────────────────┘    │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  Observability                                                          │   │
│   │  • CloudWatch Logs (agent + Lambda logs)                                │   │
│   │  • X-Ray Traces (auto-instrumented via OpenTelemetry)                   │   │
│   │  • GenAI Observability Dashboard (CloudWatch console)                   │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow (Request Lifecycle)

```
 User types question
       │
       ▼
 ① POST /council
       │  (JWT in Authorization header)
       ▼
 API Gateway validates JWT via Cognito
       │
       ▼
 Submit Lambda:
   • Generates requestId (UUID)
   • Writes {requestId, prompt, status=PENDING} to DynamoDB
   • Sends {requestId, prompt, sessionId} to SQS
   • Returns 202 {requestId} to frontend
       │
       │                    ┌──────────────────────────────────┐
       │                    │  SQS delivers message to Worker  │
       │                    └──────────────┬───────────────────┘
       │                                   │
       │                                   ▼
       │                    Worker Lambda:
       │                      • Updates DynamoDB: status=PROCESSING
       │                      • Calls AgentCore InvokeAgentRuntime
       │                      •   → Stage 1 (3 parallel Bedrock calls)
       │                      •   → Stage 2 (3 parallel Bedrock calls)
       │                      •   → Stage 3 (1 Bedrock call)
       │                      • Updates DynamoDB: status=COMPLETE, result={...}
       │
       ▼
 ② Frontend polls GET /council/{requestId} every 5 seconds
       │
       ▼
 Submit Lambda reads DynamoDB:
   • PENDING → frontend shows "Consulting the council..."
   • PROCESSING → frontend shows "Consulting the council..."
   • COMPLETE → frontend renders Stage 1, 2, 3 results
```

## Security Layers

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: CloudFront                                     │
│   • HTTPS only (redirect HTTP)                          │
│   • S3 bucket not publicly accessible                   │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Cognito                                        │
│   • Email/password authentication                       │
│   • JWT tokens with 1-hour expiry                       │
│   • Auto-refresh via refresh tokens                     │
├─────────────────────────────────────────────────────────┤
│ Layer 3: API Gateway + Cognito Authorizer               │
│   • Validates JWT signature, expiry, issuer, audience   │
│   • Rejects unauthenticated requests before Lambda      │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Submit Lambda                                  │
│   • Per-user session isolation (Cognito sub)            │
│   • Users can only poll their own requests              │
├─────────────────────────────────────────────────────────┤
│ Layer 5: Worker Lambda                                  │
│   • No public endpoint (SQS-triggered only)             │
│   • Least-privilege IAM (only InvokeAgentRuntime)       │
├─────────────────────────────────────────────────────────┤
│ Layer 6: AgentCore Runtime                              │
│   • Isolated microVMs per session                       │
│   • No direct internet exposure                         │
└─────────────────────────────────────────────────────────┘
```
