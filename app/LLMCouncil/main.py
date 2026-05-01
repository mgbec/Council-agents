"""
LLM Council on Amazon Bedrock AgentCore.

Uses manual OpenTelemetry spans for session tracking in observability.
"""

import asyncio
import json
import uuid
import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from council import run_full_council

# Optional: OTEL for session observability
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("llm-council")
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

app = BedrockAgentCoreApp()


def format_response_text(result: dict) -> str:
    """Format the council result into readable text output."""
    lines = []

    lines.append("=" * 60)
    lines.append("STAGE 1: Individual Responses")
    lines.append("=" * 60)
    for resp in result.get("stage1", []):
        name = resp.get("display_name", resp["model"])
        lines.append(f"\n--- {name} ---")
        lines.append(resp["response"])

    lines.append("\n" + "=" * 60)
    lines.append("STAGE 2: Peer Rankings")
    lines.append("=" * 60)
    for rank in result.get("stage2", []):
        name = rank.get("display_name", rank["model"])
        lines.append(f"\n--- {name}'s Evaluation ---")
        lines.append(rank["ranking"])
        if rank.get("parsed_ranking"):
            lines.append(f"  Extracted order: {', '.join(rank['parsed_ranking'])}")

    agg = result.get("metadata", {}).get("aggregate_rankings", [])
    if agg:
        lines.append("\n--- Aggregate Rankings (lower is better) ---")
        for i, entry in enumerate(agg, 1):
            name = entry.get("display_name", entry["model"])
            lines.append(
                f"  #{i} {name} — avg rank {entry['average_rank']} "
                f"({entry['rankings_count']} votes)"
            )

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
    """AgentCore Runtime entry point."""
    user_query = payload.get(
        "prompt",
        "No prompt provided. Please send {\"prompt\": \"your question\"}.",
    )

    session_id = getattr(context, "session_id", None) or str(uuid.uuid4())

    # Run council with OTEL span for observability
    if HAS_OTEL:
        from opentelemetry import baggage, context as otel_context
        # Set session ID as baggage so it propagates to all child spans
        ctx = baggage.set_baggage("session.id", session_id)
        ctx = baggage.set_baggage("gen_ai.session.id", session_id, context=ctx)
        token = otel_context.attach(ctx)
        try:
            with tracer.start_as_current_span("council.deliberation") as span:
                span.set_attribute("session.id", session_id)
                span.set_attribute("gen_ai.session.id", session_id)
                span.set_attribute("council.query", user_query[:200])
                result = await run_full_council(user_query)
                span.set_attribute("council.models_responded", len(result.get("stage1", [])))
        finally:
            otel_context.detach(token)
    else:
        result = await run_full_council(user_query)

    return {
        "text": format_response_text(result),
        "structured": result,
        "session_id": session_id,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
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
        app.run()
