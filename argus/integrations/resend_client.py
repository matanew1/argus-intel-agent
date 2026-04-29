import os

import markdown
import resend

from argus.core.logger import get_logger

log = get_logger(__name__)

_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "argus@updates.argus-intel.dev")


def send_digest_email(to: str, subject: str, markdown_body: str) -> str:
    """Send HTML email via Resend. Returns message ID."""
    resend.api_key = os.environ["RESEND_API_KEY"]
    html_body = markdown.markdown(markdown_body, extensions=["nl2br", "tables"])
    result = resend.Emails.send(
        {
            "from": _FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": html_body,
        }
    )
    msg_id = result.get("id", "")
    log.info("Digest email sent to %s (id=%s)", to, msg_id)
    return msg_id
