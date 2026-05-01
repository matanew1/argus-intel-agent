"""Classifier for inferring strategic intent from a batch of job postings."""
import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel, ValidationError

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a competitive intelligence analyst reading job postings to infer strategic intent.

Respond ONLY with valid JSON matching the schema:
{"label": "<label>", "reasoning": "<1-2 sentences>", "confidence": <0.0-1.0>}

Labels:
- infra_scaling: high volume of SRE/DevOps/platform roles signaling rapid growth
- entering_new_market: roles requiring geo/language/domain expertise new to this company
- building_ai_team: ML engineer, AI researcher, LLM specialist, or AI product roles
- routine_backfill: standard hiring any growing company does
"""


class JobSignal(BaseModel):
    """Structured output returned by the job cluster classifier."""

    label: Literal["infra_scaling", "entering_new_market", "building_ai_team", "routine_backfill"]
    reasoning: str
    confidence: float


def classify_job_cluster(
    competitor: str, new_roles: list[dict], criteria: str
) -> JobSignal:
    """Classify a batch of new job postings as a single strategic signal.

    Batching is intentional — individual roles are noise; clusters reveal intent.

    Args:
        competitor: Competitor display name.
        new_roles: List of dicts with ``title`` and ``location`` keys (max 25 used).
        criteria: Plain-English observer criteria from config.yaml.

    Returns:
        A JobSignal with label, reasoning, and confidence score.
    """
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    llm = ChatMistralAI(model=model, temperature=0)
    roles_text = "\n".join(
        f"- {r.get('title', '')} ({r.get('location', 'remote')})"
        for r in new_roles[:25]
    )
    prompt = (
        f"Competitor: {competitor}\n"
        f"New job postings this cycle:\n{roles_text}\n\n"
        f"Observer's criteria:\n{criteria}"
    )
    try:
        result: JobSignal = llm.with_structured_output(JobSignal).invoke(
            [SystemMessage(_SYSTEM_PROMPT), HumanMessage(prompt)]
        )
    except ValidationError as exc:
        log.warning("Jobs classifier returned invalid label for %s: %s — defaulting to routine_backfill", competitor, exc)
        result = JobSignal(label="routine_backfill", reasoning="Invalid label from LLM", confidence=0.0)
    log.info("Jobs classifier: %s -> %s (%.2f)", competitor, result.label, result.confidence)
    return result
