"""Bedrock model client - replaces OpenRouter with native AWS Bedrock calls."""

import asyncio
import json
import time
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Optional
from config import AWS_REGION, MODEL_DISPLAY_NAMES


def get_bedrock_client():
    """Get a Bedrock Runtime client."""
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def get_display_name(model_id: str) -> str:
    """Get a friendly display name for a model."""
    return MODEL_DISPLAY_NAMES.get(model_id, model_id)


def query_model_sync(
    model_id: str,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    max_tokens: int = 4096,
    retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Query a single Bedrock model using the Converse API.
    Retries on throttling errors with exponential backoff.

    Args:
        model_id: Bedrock model identifier
        messages: List of message dicts with 'role' and 'content'
        system_prompt: Optional system prompt
        max_tokens: Maximum tokens in response
        retries: Number of retry attempts for throttling errors

    Returns:
        Dict with 'content' key, or None on failure
    """
    client = get_bedrock_client()

    # Convert messages to Bedrock Converse format
    bedrock_messages = []
    for msg in messages:
        bedrock_messages.append({
            "role": msg["role"],
            "content": [{"text": msg["content"]}],
        })

    kwargs = {
        "modelId": model_id,
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]

    for attempt in range(retries + 1):
        try:
            response = client.converse(**kwargs)
            output = response["output"]["message"]["content"]
            text = "".join(block.get("text", "") for block in output)
            return {"content": text}
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            print(f"[Attempt {attempt + 1}/{retries + 1}] Bedrock error for {model_id}: {error_code} - {e}")
            if error_code in ("ThrottlingException", "TooManyRequestsException", "ServiceUnavailableException") and attempt < retries:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
                continue
            return None
        except Exception as e:
            print(f"[Attempt {attempt + 1}/{retries + 1}] Unexpected error for {model_id}: {type(e).__name__}: {e}")
            return None


async def query_model(
    model_id: str,
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    max_tokens: int = 4096,
) -> Optional[Dict[str, Any]]:
    """Async wrapper around the sync Bedrock call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, query_model_sync, model_id, messages, system_prompt, max_tokens
    )


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    max_tokens: int = 4096,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple Bedrock models in parallel.

    Args:
        models: List of Bedrock model identifiers
        messages: Messages to send to each model
        system_prompt: Optional system prompt
        max_tokens: Maximum tokens per response

    Returns:
        Dict mapping model_id to response (or None on failure)
    """
    tasks = [query_model(m, messages, system_prompt, max_tokens) for m in models]
    responses = await asyncio.gather(*tasks)
    return {model: resp for model, resp in zip(models, responses)}
