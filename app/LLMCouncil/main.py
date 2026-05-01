"""
LLM Council on Amazon Bedrock AgentCore — Strands Agent version.

Uses the Strands Agent framework for proper session management and
OpenTelemetry integration, so sessions appear in AgentCore observability.
"""

import asyncio
import json
import os
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from council import run_full_council
from config import COUNCIL_MODELS, CHAIRMAN_MODEL, MODEL_DISPLAY_NAMES

app = BedrockAgentCoreApp()


@tool
def consult_council(question: str) -> str:
    """Consult the LLM Council with a question. The council queries multiple AI models,
    has them peer-review each other's responses anonymously, then synthesizes a final answer.

    Args:
        question: The question to ask the council.

    Returns:
        A formatted string with all three stages of the council deliberation.
    """
    result = asyncio.run(run_full_council(question))
    return format_response_text(result)


def format_response_text(result: dict) -> str:
    """Format the council result into readable text output."""
    lines = []

    # Stage 1: Individual responses
    lines.append("=" * 60)
    lines.append("STAGE 1: Individual Responses")
    lines.append("=" * 60)
    for resp in result.get("stage1", []):
        name = resp.get("display_name", resp["model"])
        lines.append(f"\n--- {name} ---")
        lines.append(resp["response"])

    # Stage 2: Peer rankings
    lines.append("\n" + "=" * 60)
    lines.append("STAGE 2: Peer Rankings")
    lines.append("=" * 60)
    for rank in result.get("stage2", []):
        name = rank.get("display_name", rank["model"])
        lines.append(f"\n--- {name}'s Evaluation ---")
        lines.append(rank["ranking"])
        if rank.get("parsed_ranking"):
            lines.append(f"  Extracted order: {', '.join(rank['parsed_ranking'])}")

    # Aggregate rankings
    agg = result.get("metadata", {}).get("aggregate_rankings", [])
    if agg:
        lines.append("\n--- Aggregate Rankings (lower is better) ---")
        for i, entry in enumerate(agg, 1):
            name = entry.get("display_name", entry["model"])
            lines.append(
                f"  #{i} {name} — avg rank {entry['average_rank']} "
                f"({entry['rankings_count']} votes)"
            )

    # Stage 3: Final answer
    lines.append("\n" + "=" * 60)
    lines.append("STAGE 3: Final Council Answer")
    lines.append("=" * 60)
    s3 = result.get("stage3", {})
    chairman = s3.get("display_name", s3.get("model", "Chairman"))
    lines.append(f"Chairman: {chairman}\n")
    lines.append(s3.get("response", ""))

    return "\n".join(lines)


# Build the model list for the system prompt
model_names = [MODEL_DISPLAY_NAMES.get(m, m) for m in COUNCIL_MODELS]
chairman_name = MODEL_DISPLAY_NAMES.get(CHAIRMAN_MODEL, CHAIRMAN_MODEL)

SYSTEM_PROMPT = f"""You are the LLM Council orchestrator. When a user asks a question, 
use the consult_council tool to get the council's deliberation. Always pass the user's 
full question to the tool. Return the tool's output directly to the user without 
modification.

The council consists of: {', '.join(model_names)}.
The chairman (who synthesizes the final answer) is: {chairman_name}.

Do not answer questions yourself — always delegate to the council tool."""


@app.entrypoint
def invoke(payload, context):
    """AgentCore Runtime entry point using Strands Agent."""
    user_query = payload.get(
        "prompt",
        'No prompt provided. Please send {"prompt": "your question"}.',
    )

    # Create agent with session context from AgentCore
    agent = Agent(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        tools=[consult_council],
        system_prompt=SYSTEM_PROMPT,
    )

    # Invoke the agent — Strands handles OTEL context propagation
    result = agent(user_query)

    # Return structured response
    return {
        "text": str(result),
        "session_id": getattr(context, "session_id", None),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        print("LLM Council (Strands Agent) — Interactive Mode")
        print("Type your question and press Enter. Ctrl+C to exit.\n")
        agent = Agent(
            model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            tools=[consult_council],
            system_prompt=SYSTEM_PROMPT,
        )
        while True:
            try:
                query = input("You: ").strip()
                if not query:
                    continue
                print("\nConsulting the council...\n")
                result = agent(query)
                print(result)
                print()
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
    else:
        app.run()
