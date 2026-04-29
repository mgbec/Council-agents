"""
LLM Council on Amazon Bedrock AgentCore.

This is the main entry point. It can run:
  1. Locally via `python main.py` (starts an HTTP server on :8080)
  2. Deployed to AgentCore Runtime via `agentcore deploy`
  3. Interactively in the terminal for quick testing
"""

import asyncio
import json
import uuid
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from council import run_full_council
from memory_integration import (
    store_conversation_event,
    store_council_result,
    get_conversation_history,
)

app = BedrockAgentCoreApp()


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


@app.entrypoint
async def invoke(payload, context):
    """
    AgentCore Runtime entry point.

    Payload: {"prompt": "your question here"}
    Returns: Full council deliberation result.
    """
    user_query = payload.get(
        "prompt",
        "No prompt provided. Please send {\"prompt\": \"your question\"}.",
    )

    # Determine session ID (from AgentCore context or generate one)
    session_id = getattr(context, "session_id", None) or str(uuid.uuid4())

    # Store user message in memory
    store_conversation_event(session_id, "user", user_query)

    # Run the 3-stage council
    result = await run_full_council(user_query)

    # Store council result in memory
    store_council_result(session_id, result)

    # Return both structured data and a readable text version
    return {
        "text": format_response_text(result),
        "structured": result,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        # Interactive terminal mode for quick testing
        print("LLM Council (Bedrock AgentCore) — Interactive Mode")
        print("Type your question and press Enter. Ctrl+C to exit.\n")
        while True:
            try:
                query = input("You: ").strip()
                if not query:
                    continue
                print("\nConsulting the council...\n")
                result = asyncio.run(run_full_council(query))
                print(format_response_text(result))
                print()
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
    else:
        # Start as AgentCore Runtime server
        app.run()
