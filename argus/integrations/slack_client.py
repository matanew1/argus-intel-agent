"""Slack SDK wrapper for posting messages and DMs."""
import os

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from argus.core.logger import get_logger

log = get_logger(__name__)

_client: WebClient | None = None


def _get_client() -> WebClient:
    """Return the singleton Slack WebClient, initialising it on first call."""
    global _client
    if _client is None:
        _client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    return _client


def post_to_channel(channel_id: str, text: str) -> str:
    """Post a message to a channel. Returns the message timestamp (ts)."""
    try:
        resp = _get_client().chat_postMessage(channel=channel_id, text=text)
        log.info("Slack message sent to channel %s", channel_id)
        return resp["ts"]
    except SlackApiError as exc:
        log.error("Slack postMessage failed: %s", exc.response["error"])
        raise


def send_dm(user_id: str, text: str) -> str:
    """Open a DM with user_id and send a message. Returns the message timestamp."""
    try:
        client = _get_client()
        conv = client.conversations_open(users=user_id)
        channel = conv["channel"]["id"]
        resp = client.chat_postMessage(channel=channel, text=text)
        log.info("Slack DM sent to user %s", user_id)
        return resp["ts"]
    except SlackApiError as exc:
        log.error("Slack DM failed: %s", exc.response["error"])
        raise


def notify_start(workflow_name: str, channel_id: str) -> None:
    """Post a green-circle startup ping to channel_id. Failures are silently ignored."""
    text = f":green_circle: *{workflow_name.replace('_', ' ').title()}* started"
    try:
        post_to_channel(channel_id, text)
    except Exception:
        pass


def notify_done(workflow_name: str, channel_id: str, items: int, actions: int) -> None:
    """Post a completion summary to channel_id. Failures are silently ignored."""
    text = (
        f":white_check_mark: *{workflow_name.replace('_', ' ').title()}* done "
        f"— {items} items processed, {actions} action(s) taken"
    )
    try:
        post_to_channel(channel_id, text)
    except Exception:
        pass
