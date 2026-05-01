from unittest.mock import patch

from tests.conftest import SAMPLE_ARTICLE, SAMPLE_CRITERIA

_CFG = {
    "competitors": [
        {"name": "OpenAI", "news_query": "OpenAI funding", "pricing_urls": []}
    ],
    "criteria": {"what_i_care_about": SAMPLE_CRITERIA},
    "notifications": {
        "slack_channel": "C123",
        "slack_dm_user": "U456",
        "calendar_id": "primary",
        "google_sheet_id": "sheet123",
        "digest_email": "test@example.com",
    },
}


@patch("argus.workflows.news_watch.fetch_news")
@patch("argus.workflows.news_watch.classify_news")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._create_calendar_event")
@patch("argus.workflows.base.ConfigLoader")
def test_news_watch_funding_creates_calendar_event(mock_cfg, mock_cal, mock_classify, mock_news):
    from argus.integrations.news_client import Article
    from argus.classifiers.news import NewsSignal
    from argus.workflows.news_watch import NewsWatchWorkflow

    mock_cfg.instance.return_value.get.return_value = _CFG
    mock_news.return_value = [Article(**SAMPLE_ARTICLE)]
    mock_classify.return_value = NewsSignal(label="funding", reasoning="Big round.", confidence=0.95)
    mock_cal.return_value = ("event-123", "https://calendar.google.com/event/123")

    wf = NewsWatchWorkflow()
    run_log = wf.run(dry_run=False)

    mock_cal.assert_called_once()
    decisions = __import__("json").loads(run_log.decisions)
    assert decisions[0]["label"] == "funding"


@patch("argus.workflows.news_watch.fetch_news")
@patch("argus.workflows.news_watch.classify_news")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._append_url_to_calendar_event")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._create_calendar_event")
@patch("argus.workflows.base.ConfigLoader")
def test_news_watch_same_day_duplicate_appends_url(
    mock_cfg,
    mock_cal,
    mock_append,
    mock_classify,
    mock_news,
):
    from argus.integrations.news_client import Article
    from argus.classifiers.news import NewsSignal
    from argus.workflows.news_watch import NewsWatchWorkflow

    second_article = {
        **SAMPLE_ARTICLE,
        "url": "https://example.com/openai-funding-followup",
        "title": "OpenAI funding round gets additional coverage",
    }

    mock_cfg.instance.return_value.get.return_value = _CFG
    mock_news.return_value = [Article(**SAMPLE_ARTICLE), Article(**second_article)]
    mock_classify.return_value = NewsSignal(label="funding", reasoning="Big round.", confidence=0.95)
    mock_cal.return_value = ("event-123", "https://calendar.google.com/event/123")
    mock_append.return_value = "event-123"

    wf = NewsWatchWorkflow()
    run_log = wf.run(dry_run=False)

    mock_cal.assert_called_once()
    mock_append.assert_called_once_with(
        "primary",
        "event-123",
        "https://example.com/openai-funding-followup",
    )
    actions = __import__("json").loads(run_log.actions_taken)
    assert [action["status"] for action in actions] == ["created", "updated"]


@patch("argus.workflows.news_watch.fetch_news")
@patch("argus.workflows.news_watch.classify_news")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._post_to_slack")
@patch("argus.workflows.base.ConfigLoader")
def test_news_watch_controversy_posts_to_slack(mock_cfg, mock_slack, mock_classify, mock_news):
    from argus.integrations.news_client import Article
    from argus.classifiers.news import NewsSignal
    from argus.workflows.news_watch import NewsWatchWorkflow

    mock_cfg.instance.return_value.get.return_value = _CFG
    mock_news.return_value = [Article(**SAMPLE_ARTICLE)]
    mock_classify.return_value = NewsSignal(label="controversy", reasoning="Data breach.", confidence=0.9)

    wf = NewsWatchWorkflow()
    wf.run(dry_run=False)

    mock_slack.assert_called_once()


@patch("argus.workflows.news_watch.fetch_news")
@patch("argus.workflows.news_watch.classify_news")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._post_to_slack")
@patch("argus.workflows.news_watch.NewsWatchWorkflow._create_calendar_event")
@patch("argus.workflows.base.ConfigLoader")
def test_news_watch_noise_takes_no_action(mock_cfg, mock_cal, mock_slack, mock_classify, mock_news):
    from argus.integrations.news_client import Article
    from argus.classifiers.news import NewsSignal
    from argus.workflows.news_watch import NewsWatchWorkflow

    mock_cfg.instance.return_value.get.return_value = _CFG
    mock_news.return_value = [Article(**SAMPLE_ARTICLE)]
    mock_classify.return_value = NewsSignal(label="noise", reasoning="Just a blog post.", confidence=0.8)

    wf = NewsWatchWorkflow()
    run_log = wf.run(dry_run=False)

    mock_cal.assert_not_called()
    mock_slack.assert_not_called()
    actions = __import__("json").loads(run_log.actions_taken)
    assert len(actions) == 0
