"""Classifier for competitor news articles."""
import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel, ValidationError

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a competitive intelligence analyst. Classify the news article about a competitor.

Respond ONLY with valid JSON matching the schema:
{"label": "<label>", "reasoning": "<1-2 sentences>", "confidence": <0.0-1.0>}

You MUST use one of these exact labels — no other values are allowed:
- funding: investment round, acquisition, or significant capital event
- product_launch: new product, major feature release, or public beta
- executive_change: CEO/CTO/VP departure, hire, or board change
- controversy: legal issue, data breach, customer backlash, regulatory action
- noise: anything else — blog post, award, minor update, recycled news, unrelated article

If you are unsure, use noise.
"""


class NewsSignal(BaseModel):
    """Structured output returned by the news classifier."""

    label: Literal["funding", "product_launch", "executive_change", "controversy", "noise"]
    reasoning: str
    confidence: float


def classify_news(article: dict, criteria: str) -> NewsSignal:
    """Classify a single news article using Mistral structured output.

    Falls back to ``noise`` if the LLM returns an invalid label, rather than
    raising a ValidationError and skipping the article entirely.

    Args:
        article: Dict with keys ``title``, ``description``, ``url``, ``source``.
        criteria: Plain-English observer criteria from config.yaml.

    Returns:
        A NewsSignal with label, reasoning, and confidence score.
    """
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    llm = ChatMistralAI(model=model, temperature=0)
    prompt = (
        f"Competitor: {article.get('source', 'unknown')}\n"
        f"Headline: {article.get('title', '')}\n"
        f"Summary: {article.get('description', '')}\n"
        f"URL: {article.get('url', '')}\n\n"
        f"Observer's criteria:\n{criteria}"
    )
    try:
        result: NewsSignal = llm.with_structured_output(NewsSignal).invoke(
            [SystemMessage(_SYSTEM_PROMPT), HumanMessage(prompt)]
        )
    except ValidationError as exc:
        log.warning("News classifier returned invalid label for '%s': %s — defaulting to noise",
                    article.get("title", "")[:60], exc)
        result = NewsSignal(label="noise", reasoning="Invalid label from LLM", confidence=0.0)
    log.info("News classifier: %s -> %s (%.2f)", article.get("title", "")[:60], result.label, result.confidence)
    return result
