from unittest.mock import MagicMock, patch

from tests.conftest import SAMPLE_ARTICLE, SAMPLE_CRITERIA


def _make_mock_judgment(label: str):
    from argus.judges.news import NewsJudgment
    return NewsJudgment(label=label, reasoning="Test reasoning.", confidence=0.9)


@patch("argus.judges.news.ChatMistralAI")
def test_judge_news_funding(mock_llm_class):
    from argus.judges.news import judge_news

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("funding")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    result = judge_news(SAMPLE_ARTICLE, SAMPLE_CRITERIA)

    assert result.label == "funding"
    assert result.reasoning == "Test reasoning."
    assert 0.0 <= result.confidence <= 1.0
    mock_chain.invoke.assert_called_once()


@patch("argus.judges.news.ChatMistralAI")
def test_judge_news_noise(mock_llm_class):
    from argus.judges.news import judge_news

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("noise")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    result = judge_news({"title": "OpenAI wins award", "description": "", "url": "x", "source": "x"}, SAMPLE_CRITERIA)

    assert result.label == "noise"


@patch("argus.judges.news.ChatMistralAI")
def test_judge_news_passes_criteria_to_llm(mock_llm_class):
    from argus.judges.news import judge_news

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("product_launch")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    judge_news(SAMPLE_ARTICLE, "custom criteria text")

    call_args = mock_chain.invoke.call_args[0][0]
    assert any("custom criteria text" in str(msg) for msg in call_args)
