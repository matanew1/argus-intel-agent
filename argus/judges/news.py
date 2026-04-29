import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM = """\
You are a competitive intelligence analyst. Classify the news article about a competitor.

Respond ONLY with valid JSON matching the schema:
{"label": "<label>", "reasoning": "<1-2 sentences>", "confidence": <0.0-1.0>}

Labels:
- funding: investment round, acquisition, or significant capital event
- product_launch: new product, major feature release, or public beta
- executive_change: CEO/CTO/VP departure, hire, or board change
- controversy: legal issue, data breach, customer backlash, regulatory action
- noise: blog post, award, minor update, recycled news
"""


class NewsJudgment(BaseModel):
    label: Literal["funding", "product_launch", "executive_change", "controversy", "noise"]
    reasoning: str
    confidence: float


def judge_news(article: dict, criteria: str) -> NewsJudgment:
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    llm = ChatMistralAI(model=model, temperature=0)
    prompt = (
        f"Competitor: {article.get('source', 'unknown')}\n"
        f"Headline: {article.get('title', '')}\n"
        f"Summary: {article.get('description', '')}\n"
        f"URL: {article.get('url', '')}\n\n"
        f"Observer's criteria:\n{criteria}"
    )
    result: NewsJudgment = llm.with_structured_output(NewsJudgment).invoke(
        [SystemMessage(_SYSTEM), HumanMessage(prompt)]
    )
    log.info("News judge: %s → %s (%.2f)", article.get("title", "")[:60], result.label, result.confidence)
    return result
