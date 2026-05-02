from unittest.mock import patch


@patch("argus.workflows.job_watch.scrape_jobs_html")
@patch("argus.workflows.job_watch.scrape_jobs_rss")
def test_fetch_jobs_uses_linkedin_rss_when_configured(mock_rss, mock_html):
    from argus.workflows.job_watch import JobWatchWorkflow

    mock_rss.return_value = [{"id": "job-1", "title": "ML Engineer", "location": ""}]

    jobs = JobWatchWorkflow._fetch_jobs(
        {
            "name": "OpenAI",
            "careers_url": "https://openai.com/careers",
            "linkedin_rss": "https://example.com/openai-jobs.xml",
        }
    )

    assert jobs == [{"id": "job-1", "title": "ML Engineer", "location": ""}]
    mock_rss.assert_called_once_with("https://example.com/openai-jobs.xml")
    mock_html.assert_not_called()


@patch("argus.workflows.job_watch.scrape_jobs_html")
@patch("argus.workflows.job_watch.scrape_jobs_rss")
def test_fetch_jobs_falls_back_to_careers_html_without_linkedin_rss(mock_rss, mock_html):
    from argus.workflows.job_watch import JobWatchWorkflow

    mock_html.return_value = [{"id": "job-2", "title": "Product Engineer", "location": ""}]

    jobs = JobWatchWorkflow._fetch_jobs(
        {
            "name": "Anthropic",
            "careers_url": "https://www.anthropic.com/careers",
            "linkedin_rss": "",
        }
    )

    assert jobs == [{"id": "job-2", "title": "Product Engineer", "location": ""}]
    mock_html.assert_called_once_with("https://www.anthropic.com/careers")
    mock_rss.assert_not_called()
