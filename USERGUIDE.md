# LLM Council — User Guide

This guide is for end users of a deployed LLM Council instance. You don't
need to know anything about AWS, Bedrock, or AgentCore to use it.

## What is LLM Council?

LLM Council is a system that answers your questions using multiple AI models
working together, rather than relying on a single one. When you ask a
question, here's what happens behind the scenes:

1. **Stage 1 — Individual Responses.** Your question is sent to several AI
   models at the same time (e.g., Claude, Llama, Mistral). Each model writes
   its own independent answer.

2. **Stage 2 — Peer Review.** Every model reads the other models' answers
   (anonymized so they can't play favorites) and ranks them from best to
   worst. This produces an aggregate "street cred" score for each model.

3. **Stage 3 — Final Answer.** A designated "Chairman" model reads all the
   individual answers and all the peer reviews, then synthesizes one
   comprehensive final answer that represents the council's collective
   judgment.

The result is a more balanced, thoroughly vetted answer than any single
model would produce on its own.

## Using the Web Interface

### Signing in

The LLM Council uses Amazon Cognito for authentication. Here's what the
sign-in flow looks like:

1. Open the LLM Council URL provided by your administrator.
2. You'll be redirected to a sign-in page (hosted by Amazon Cognito).
3. **First time?** Click "Sign up", enter your email and choose a password.
   You'll receive a 6-digit verification code by email — enter it to
   confirm your account.
4. **Returning?** Enter your email and password, then click "Sign in".
5. After signing in, you're redirected back to the LLM Council app and
   can start asking questions immediately.

Your session stays active for about an hour. After that, the app
automatically refreshes your session in the background — you won't be
asked to sign in again unless you've been inactive for an extended period
or explicitly sign out.

If your administrator has enabled multi-factor authentication (MFA),
you'll also be prompted for a code from your authenticator app after
entering your password.

**Note:** Depending on how your instance is configured, self-registration
may be disabled. In that case, your administrator will create your account
and send you temporary credentials. You'll be asked to set a new password
on first sign-in.

### Asking a question

1. Type your question in the text box at the bottom of the screen.
2. Press Enter (or click Send).
3. Wait for the council to deliberate. This typically takes 30–90 seconds
   depending on the complexity of your question, because multiple AI models
   are being consulted in sequence.

### Reading the response

The response is organized into three collapsible sections:

**Stage 1: Individual Responses**
- A tab for each AI model showing its independent answer.
- Click the tabs to compare how different models approached your question.
- This is useful when you want to see the range of perspectives.

**Stage 2: Peer Rankings**
- Each model's evaluation of the other models' answers.
- Model names appear in bold for readability, but the models themselves
  evaluated anonymous "Response A", "Response B", etc.
- At the bottom, you'll see the aggregate ranking — which model's answer
  was rated best overall. Lower average rank is better.

**Stage 3: Final Council Answer**
- The synthesized answer from the Chairman model.
- This is the "bottom line" — the council's best collective answer.
- It draws on the strongest points from all individual responses and
  accounts for the peer review feedback.

### Tips for good questions

- **Be specific.** "What are the tradeoffs of microservices vs monoliths
  for a team of 5 engineers?" works better than "Tell me about
  microservices."
- **Ask for analysis, not trivia.** The council shines on questions where
  multiple perspectives add value — comparisons, tradeoffs, strategy,
  explanations of complex topics.
- **One question at a time.** The council treats your entire input as a
  single question. If you ask three things at once, the responses may be
  unfocused.

## Using the CLI

If you have access to the `agentcore` CLI (for developers or power users):

### Basic invocation

```bash
agentcore invoke '{"prompt": "Your question here"}'
```

The response includes a `text` field (human-readable) and a `structured`
field (JSON with all three stages).

### Multi-turn conversations

Use a session ID to maintain context across questions:

```bash
# First question
agentcore invoke '{"prompt": "Explain event sourcing"}' \
  --session-id "my-research-session-00000000001"

# Follow-up (same session)
agentcore invoke '{"prompt": "How does that compare to CQRS?"}' \
  --session-id "my-research-session-00000000001"
```

Session IDs must be at least 33 characters.

### Using curl directly

If you have the API endpoint URL:

```bash
curl -X POST https://<api-endpoint>/council \
  -H "Content-Type: application/json" \
  -H "Authorization: <your-jwt-token>" \
  -d '{"prompt": "What are the best practices for database indexing?"}'
```

## Understanding the Output

### The structured response

If you're consuming the API programmatically, the JSON response looks like:

```json
{
  "text": "... human-readable formatted output ...",
  "structured": {
    "stage1": [
      {
        "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "display_name": "Claude Sonnet 4",
        "response": "..."
      }
    ],
    "stage2": [
      {
        "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "display_name": "Claude Sonnet 4",
        "ranking": "... full evaluation text ...",
        "parsed_ranking": ["Response B", "Response A", "Response C"]
      }
    ],
    "stage3": {
      "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
      "display_name": "Claude Sonnet 4",
      "response": "... final synthesized answer ..."
    },
    "metadata": {
      "label_to_model": {
        "Response A": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "Response B": "us.meta.llama4-maverick-17b-instruct-v1:0",
        "Response C": "mistral.mistral-large-2411-v1:0"
      },
      "aggregate_rankings": [
        {
          "model": "us.meta.llama4-maverick-17b-instruct-v1:0",
          "display_name": "Llama 4 Maverick",
          "average_rank": 1.33,
          "rankings_count": 3
        }
      ]
    }
  }
}
```

### Aggregate rankings explained

- Each model assigns a rank (1st, 2nd, 3rd...) to every response.
- The aggregate averages these ranks across all reviewers.
- An average rank of 1.0 means every reviewer ranked that model first.
- Lower is better.
- `rankings_count` shows how many reviewers successfully parsed a ranking
  for that model. If it's less than the total number of models, some
  evaluations may have had formatting issues (the system handles this
  gracefully).

## Frequently Asked Questions

**How long does a query take?**
Typically 30–90 seconds. Stage 1 and Stage 2 each run all models in
parallel, but the stages themselves run sequentially (Stage 2 needs Stage 1's
output, Stage 3 needs Stage 2's output).

**Which AI models are in the council?**
This depends on how your instance was configured. Common setups include
Claude (Anthropic), Llama (Meta), and Mistral. Ask your administrator
for the specific models in your deployment.

**Can I see which model said what?**
Yes. Stage 1 shows each model's individual response with its name. Stage 2
shows each model's evaluation. The anonymization only applies during the
peer review process itself — the results are fully transparent to you.

**Why are responses anonymized during peer review?**
To prevent bias. If a model knew which response came from which competitor,
it might rate itself higher or rate certain brands differently. Anonymous
labels (Response A, B, C) ensure the evaluation is based purely on content
quality.

**What if one model fails?**
The system continues with whichever models respond successfully. If a model
is down or times out, it's simply excluded from that round. The council
still produces a result as long as at least one model responds.

**Is my data stored?**
If memory is enabled, your questions and the council's final answers are
stored for session continuity. Ask your administrator about the retention
policy. If memory is not enabled, nothing is persisted — each query is
independent.

**Do I need an AWS account to use this?**
No. You only need the login credentials for the LLM Council app itself
(managed through Cognito). The AWS infrastructure is handled by whoever
deployed the system.

**I got a "Session expired" or 401 error.**
Your authentication token expired and couldn't be refreshed automatically.
Reload the page — you'll be redirected to sign in again. This is normal
after long periods of inactivity.

**Can my administrator see my questions?**
The system logs are accessible to administrators via AWS CloudWatch. Treat
your usage the same way you would any company-provided tool.

**Can I use this for sensitive or confidential questions?**
Your questions are sent to AI models hosted on Amazon Bedrock within your
AWS account. Data does not leave your AWS environment. However, standard
AI usage policies apply — avoid sharing passwords, API keys, or personally
identifiable information in your prompts.
