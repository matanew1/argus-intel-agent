import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM = """\
You are a competitive intelligence analyst reading job postings to infer strategic intent.

Respond ONLY with valid JSON matching the schema:
{"label": "<label>", "reasoning": "<1-2 sentences>", "confidence": <0.0-1.0>}

Labels:
- infra_scaling: high volume of SRE/DevOps/platform roles signaling rapid growth
- entering_new_market: roles requiring geo/language/domain expertise new to this company
- building_ai_team: ML engineer, AI researcher, LLM specialist, or AI product roles
- routine_backfill: standard hiring any growing company does
"""


class JobJudgment(BaseModel):
    label: Literal["infra_scaling", "entering_new_market", "building_ai_team", "routine_backfill"]
    reasoning: str
    confidence: float


def judge_job_cluster(
    competitor: str, new_roles: list[dict], criteria: str
) -> JobJudgment:
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
    result: JobJudgment = llm.with_structured_output(JobJudgment).invoke(
        [SystemMessage(_SYSTEM), HumanMessage(prompt)]
    )
    log.info("Jobs judge: %s → %s (%.2f)", competitor, result.label, result.confidence)
    return result
