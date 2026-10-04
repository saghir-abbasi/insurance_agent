"""Tool the realtime agent calls to answer customer questions about Final Expense.

The agent must invoke `search_knowledge_base` whenever the customer asks a
general product question outside the scripted qualification: whole life vs.
term, cash value, eligibility after a previous decline, the application and
review period, etc. The returned text is grounding context for the agent's
spoken reply.
"""

import asyncio

from agents import function_tool

from insurance_agent.core.knowledge_base import get_knowledge_base
from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

MAX_SNIPPET_CHARS = 600
MAX_RESULTS = 3
# Calibrated for BGE cosine similarity: in-domain queries score well above
# this while clearly off-domain ones fall well below it. Recalibrate if the
# embedding model or the corpus changes substantially.
MIN_SCORE = 0.55


@function_tool(name_override="search_knowledge_base", failure_error_function=None)
async def search_knowledge_base_tool(question: str) -> str:
    """Look up general information about Final Expense whole life insurance.

    Call this whenever the customer asks a general product question that is
    not part of the scripted qualification: how whole life differs from term,
    cash value, whether a previous decline matters, the application, the
    paperwork, or the review period. Use the returned snippets as grounding
    for a brief spoken answer; do not read them verbatim and do not quote
    prices or carriers as promises. If no relevant information is returned,
    tell the customer the licensed agent can answer that.

    Args:
        question: The customer's question, paraphrased in your own words.

    Returns:
        A short block of retrieved text from the Final Expense knowledge base,
        or a message indicating no relevant information was found.
    """
    question = (question or "").strip()
    if not question:
        return "No question was provided. Ask the customer to repeat their question."

    try:
        kb = get_knowledge_base()
        # Embedding + Chroma search are CPU-bound; keep them off the realtime
        # event loop so live audio never stutters during a lookup.
        results = await asyncio.to_thread(kb.query, question, MAX_RESULTS)
    except Exception as e:
        logger.error(f"Knowledge base query failed: {e}", exc_info=True)
        return (
            "The knowledge base is temporarily unavailable. Tell the customer the "
            "licensed agent can go over that with them, then continue."
        )

    relevant = [r for r in results if r.score >= MIN_SCORE]
    if not relevant:
        return (
            "No matching information found in the Final Expense knowledge base. "
            "Tell the customer the licensed agent can answer that, then continue."
        )

    lines = ["Relevant information from the Final Expense knowledge base:"]
    for i, chunk in enumerate(relevant, start=1):
        snippet = chunk.text[:MAX_SNIPPET_CHARS].strip()
        lines.append(f"[{i}] {snippet}")
    lines.append(
        "Use these to give a brief, conversational reply. Do not read them "
        "verbatim, and do not quote exact prices or promise a carrier or "
        "approval; the licensed agent covers those. Then steer back to the "
        "question you were on."
    )
    return "\n\n".join(lines)


all_knowledge_base_tools = [search_knowledge_base_tool]
