from unittest.mock import patch

_CFG = {
    "competitors": [
        {"name": "OpenAI", "news_query": "", "pricing_urls": ["https://openai.com/pricing"]}
    ],
    "criteria": {"what_i_care_about": "pricing changes matter"},
    "notifications": {
        "slack_channel": "C123",
        "slack_dm_user": "U456",
        "calendar_id": "primary",
        "google_sheet_id": "sheet123",
        "digest_email": "test@example.com",
    },
}


@patch("argus.workflows.pricing_watch.fetch_page_text")
@patch("argus.workflows.pricing_watch.judge_diff")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._get_snapshot")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._store_snapshot")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._send_dm")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._post_channel")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._create_pricing_event")
@patch("argus.workflows.base.ConfigLoader")
def test_material_change_triggers_all_actions(
    mock_cfg, mock_cal, mock_ch, mock_dm, mock_store, mock_snap, mock_judge, mock_fetch
):
    from argus.core.models import PageSnapshot
    from argus.judges.diff import DiffJudgment
    from argus.workflows.pricing_watch import PricingWatchWorkflow

    mock_cfg.instance.return_value.get.return_value = _CFG
    mock_fetch.return_value = "new page text"
    old = PageSnapshot(url="https://openai.com/pricing", content_hash="oldhash", content_text="old text")
    mock_snap.return_value = old
    mock_judge.return_value = DiffJudgment(
        label="material", reasoning="Price went up.", summary="$20 → $30.", confidence=0.95
    )

    wf = PricingWatchWorkflow()
    run_log = wf.run(dry_run=False)

    mock_dm.assert_called_once()
    mock_ch.assert_called_once()
    mock_cal.assert_called_once()
    actions = __import__("json").loads(run_log.actions_taken)
    assert len(actions) == 3


@patch("argus.workflows.pricing_watch.fetch_page_text")
@patch("argus.workflows.pricing_watch.PricingWatchWorkflow._get_snapshot")
@patch("argus.workflows.base.ConfigLoader")
def test_no_change_skips_everything(mock_cfg, mock_snap, mock_fetch):
    from argus.core.models import PageSnapshot
    from argus.integrations.scraper import content_hash
    from argus.workflows.pricing_watch import PricingWatchWorkflow

    mock_cfg.instance.return_value.get.return_value = _CFG
    text = "unchanged page text"
    mock_fetch.return_value = text
    mock_snap.return_value = PageSnapshot(
        url="https://openai.com/pricing", content_hash=content_hash(text), content_text=text
    )

    wf = PricingWatchWorkflow()
    run_log = wf.run(dry_run=False)

    actions = __import__("json").loads(run_log.actions_taken)
    assert len(actions) == 0
