import os

import pytest

# Use in-memory SQLite for all tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ.setdefault("NEWSAPI_KEY", "test-key")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("RESEND_API_KEY", "re_test")

from argus.core.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def setup_db():
    """Create and drop all tables around each test."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


SAMPLE_ARTICLE = {
    "title": "OpenAI raises $6.6 billion in Series E funding",
    "description": "OpenAI has closed a $6.6 billion funding round at a $157 billion valuation.",
    "url": "https://example.com/openai-funding",
    "published_at": "2024-10-02T10:00:00Z",
    "source": "TechCrunch",
}

SAMPLE_CRITERIA = "I care about competitor fundraising, AI features, and pricing changes."

SAMPLE_ROLES = [
    {"id": "https://openai.com/jobs/1", "title": "Senior ML Engineer", "location": "SF"},
    {"id": "https://openai.com/jobs/2", "title": "AI Research Scientist", "location": "Remote"},
    {"id": "https://openai.com/jobs/3", "title": "LLM Infrastructure Engineer", "location": "NYC"},
]

SAMPLE_DIFF = """\
--- old
+++ new
@@ -1,3 +1,3 @@
-Pro plan: $20/month
+Pro plan: $30/month
 Enterprise: Contact us
"""
