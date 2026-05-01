"""Classifier for competitor page diffs (material vs cosmetic changes)."""
import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a competitive intelligence analyst reviewing changes to a competitor's pricing or product page.

Respond ONLY with valid JSON matching the schema:
{"label": "<label>", "reasoning": "<1-2 sentences>", "summary": "<one sentence describing what changed>", "confidence": <0.0-1.0>}

Labels:
- material: price changes, new tiers, removed plans, new feature announcements, changed positioning
- cosmetic: typo fixes, image swaps, color changes, testimonial updates, minor copy tweaks
"""


class DiffSignal(BaseModel):
    """Structured output returned by the page diff classifier."""

    label: Literal["material", "cosmetic"]
    reasoning: str
    summary: str
    confidence: float


def classify_diff(competitor: str, url: str, diff_text: str) -> DiffSignal:
    """Classify a unified diff as material or cosmetic using Mistral.

    Only the first 3000 characters of the diff are sent to stay within token limits.

    Args:
        competitor: Competitor display name.
        url: URL of the page that changed.
        diff_text: Unified diff string (--- old, +++ new).

    Returns:
        A DiffSignal with label, reasoning, summary, and confidence score.
    """
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    llm = ChatMistralAI(model=model, temperature=0)
    prompt = (
        f"Competitor: {competitor}\n"
        f"Page: {url}\n\n"
        f"Diff (--- old, +++ new):\n{diff_text[:3000]}"
    )
    result: DiffSignal = llm.with_structured_output(DiffSignal).invoke(
        [SystemMessage(_SYSTEM_PROMPT), HumanMessage(prompt)]
    )
    log.info("Diff classifier: %s %s -> %s (%.2f)", competitor, url, result.label, result.confidence)
    return result
