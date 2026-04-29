from unittest.mock import MagicMock, patch

from tests.conftest import SAMPLE_DIFF


def _make_mock_judgment(label: str, summary: str = "Price changed."):
    from argus.judges.diff import DiffJudgment
    return DiffJudgment(label=label, reasoning="Test reasoning.", summary=summary, confidence=0.9)


@patch("argus.judges.diff.ChatMistralAI")
def test_judge_diff_material(mock_llm_class):
    from argus.judges.diff import judge_diff

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("material", "Pro plan price increased from $20 to $30.")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    result = judge_diff("OpenAI", "https://openai.com/pricing", SAMPLE_DIFF)

    assert result.label == "material"
    assert "30" in result.summary


@patch("argus.judges.diff.ChatMistralAI")
def test_judge_diff_cosmetic(mock_llm_class):
    from argus.judges.diff import judge_diff

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("cosmetic", "Typo fixed.")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    result = judge_diff("OpenAI", "https://openai.com/pricing", "-teh\n+the")

    assert result.label == "cosmetic"
