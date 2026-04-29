import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI

from argus.core.logger import get_logger

log = get_logger(__name__)

_SYSTEM = """\
You are a competitive intelligence analyst writing a weekly executive digest.

Structure your response as markdown with these exact sections:
## Key Developments (ranked by strategic importance)
## What To Watch Next Week
## Full Signal Log

Rules:
- Be direct. Use bullet points.
- Each item must cite the date and competitor name.
- Rank Key Developments by strategic importance to the observer's business.
- Omit sections where there is nothing to report.
"""


def synthesize_digest(run_logs_text: str, criteria: str) -> str:
    """Synthesize a weekly markdown digest from run log text."""
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    llm = ChatMistralAI(model=model, temperature=0)
    prompt = (
        f"Observer's criteria:\n{criteria}\n\n"
        f"Raw signals from the past 7 days:\n{run_logs_text}"
    )
    result = llm.invoke([SystemMessage(_SYSTEM), HumanMessage(prompt)])
    digest = result.content if hasattr(result, "content") else str(result)
    log.info("Weekly digest synthesized (%d chars)", len(digest))
    return digest
