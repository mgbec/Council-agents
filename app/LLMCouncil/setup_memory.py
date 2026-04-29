"""
Set up AgentCore Memory for conversation persistence.

Run this once to create a memory resource, then set the MEMORY_ID
environment variable with the returned ID.

Usage:
    python setup_memory.py
"""

import uuid
from bedrock_agentcore.memory import MemoryClient
from config import AWS_REGION

client = MemoryClient(region_name=AWS_REGION)

print("Creating AgentCore Memory resource for LLM Council...\n")

memory = client.create_memory_and_wait(
    name=f"LLMCouncil_{uuid.uuid4().hex[:8]}",
    strategies=[
        # Semantic memory: extracts key facts from council deliberations
        {
            "semanticMemoryStrategy": {
                "name": "council_facts",
                "namespaces": ["/council/facts/"],
            }
        },
        # User preference memory: remembers what topics/styles the user prefers
        {
            "userPreferenceMemoryStrategy": {
                "name": "user_prefs",
                "namespaces": ["/user/preferences/"],
            }
        },
    ],
    event_expiry_days=30,
)

memory_id = memory["id"]

print(f"Memory created: {memory_id}")
print(f"\nTo use it, set the environment variable:")
print(f"  export MEMORY_ID={memory_id}")
print(f"\nOr add to your .env file:")
print(f"  MEMORY_ID={memory_id}")
