"""3-stage LLM Council orchestration using Amazon Bedrock."""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from bedrock_client import query_models_parallel, query_model, get_display_name
from config import COUNCIL_MODELS, CHAIRMAN_MODEL


async def stage1_collect_responses(user_query: str) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models in parallel.
    """
    messages = [{"role": "user", "content": user_query}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    results = []
    for model, response in responses.items():
        if response is not None:
            results.append({
                "model": model,
                "display_name": get_display_name(model),
                "response": response["content"],
            })
    return results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses from Stage 1.

    Returns (rankings_list, label_to_model mapping).
    """
    labels = [chr(65 + i) for i in range(len(stage1_results))]

    label_to_model = {
        f"Response {lbl}": result["model"]
        for lbl, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join(
        f"Response {lbl}:\n{result['response']}"
        for lbl, result in zip(labels, stage1_results)
    )

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. Evaluate each response individually. For each, explain what it does well and poorly.
2. At the very end, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list responses from best to worst as a numbered list
- Each line: number, period, space, then ONLY the response label (e.g., "1. Response A")

Example format:
FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response["content"]
            parsed = parse_ranking_from_text(full_text)
            results.append({
                "model": model,
                "display_name": get_display_name(model),
                "ranking": full_text,
                "parsed_ranking": parsed,
            })

    return results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes the final response from all inputs.
    """
    stage1_text = "\n\n".join(
        f"Model: {r['display_name']}\nResponse: {r['response']}"
        for r in stage1_results
    )
    stage2_text = "\n\n".join(
        f"Model: {r['display_name']}\nRanking: {r['ranking']}"
        for r in stage2_results
    )

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Synthesize all of this into a single, comprehensive, accurate answer. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Patterns of agreement or disagreement

Provide a clear, well-reasoned final answer representing the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]
    response = await query_model(CHAIRMAN_MODEL, messages)

    if response is None:
        return {
            "model": CHAIRMAN_MODEL,
            "display_name": get_display_name(CHAIRMAN_MODEL),
            "response": "Error: Unable to generate final synthesis.",
        }

    return {
        "model": CHAIRMAN_MODEL,
        "display_name": get_display_name(CHAIRMAN_MODEL),
        "response": response["content"],
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from a model's evaluation."""
    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered:
                return [re.search(r"Response [A-Z]", m).group() for m in numbered]
            return re.findall(r"Response [A-Z]", ranking_section)
    return re.findall(r"Response [A-Z]", ranking_text)


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Calculate aggregate rankings across all peer evaluations."""
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        parsed = parse_ranking_from_text(ranking["ranking"])
        for position, label in enumerate(parsed, start=1):
            if label in label_to_model:
                model_id = label_to_model[label]
                model_positions[model_id].append(position)

    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            aggregate.append({
                "model": model,
                "display_name": get_display_name(model),
                "average_rank": round(sum(positions) / len(positions), 2),
                "rankings_count": len(positions),
            })

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def run_full_council(user_query: str) -> Dict[str, Any]:
    """
    Run the complete 3-stage council process.

    Returns a dict with stage1, stage2, stage3, and metadata.
    """
    # Stage 1
    stage1_results = await stage1_collect_responses(user_query)
    if not stage1_results:
        return {
            "stage1": [],
            "stage2": [],
            "stage3": {"model": "error", "response": "All models failed to respond."},
            "metadata": {},
        }

    # Stage 2
    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query, stage1_results
    )
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3
    stage3_result = await stage3_synthesize_final(
        user_query, stage1_results, stage2_results
    )

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        },
    }
