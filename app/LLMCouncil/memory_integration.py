"""AgentCore Memory integration - replaces JSON file storage."""

import os
import json
import time
from typing import Optional, Dict, Any, List

# Try to import AgentCore memory client; fall back gracefully
try:
    from bedrock_agentcore.memory import MemoryClient

    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False

from config import MEMORY_ID, AWS_REGION


def get_memory_client() -> Optional[Any]:
    """Get an AgentCore Memory client if configured."""
    if not HAS_MEMORY or not MEMORY_ID:
        return None
    return MemoryClient(region_name=AWS_REGION)


def store_conversation_event(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, str]] = None,
):
    """
    Store a conversation event in AgentCore Memory.

    This replaces the JSON file-based storage from the original project.
    Each user message and council response becomes a memory event,
    enabling cross-session recall via semantic search.
    """
    client = get_memory_client()
    if client is None:
        return

    try:
        payload = [{"conversationMessage": {"role": role, "content": [{"text": content}]}}]
        client.create_event(
            memory_id=MEMORY_ID,
            actor_id="council-user",
            session_id=session_id,
            messages=[(content, role)],
        )
    except Exception as e:
        print(f"Warning: Failed to store memory event: {e}")


def store_council_result(session_id: str, result: Dict[str, Any]):
    """Store the full council result as a memory event."""
    client = get_memory_client()
    if client is None:
        return

    try:
        summary = result.get("stage3", {}).get("response", "")
        # Store the chairman's final answer as the assistant message
        client.create_event(
            memory_id=MEMORY_ID,
            actor_id="council-user",
            session_id=session_id,
            messages=[(summary, "assistant")],
        )
    except Exception as e:
        print(f"Warning: Failed to store council result: {e}")


def get_conversation_history(session_id: str, max_turns: int = 5) -> List[Dict]:
    """
    Retrieve recent conversation history from AgentCore Memory.

    Returns list of message dicts for context injection.
    """
    client = get_memory_client()
    if client is None:
        return []

    try:
        turns = client.get_last_k_turns(
            memory_id=MEMORY_ID,
            actor_id="council-user",
            session_id=session_id,
            k=max_turns,
        )
        messages = []
        if turns:
            for turn in turns:
                for msg in turn:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]["text"],
                    })
        return messages
    except Exception as e:
        print(f"Warning: Failed to retrieve memory: {e}")
        return []
