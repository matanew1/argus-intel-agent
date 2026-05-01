from unittest.mock import MagicMock, patch

from tests.conftest import SAMPLE_CRITERIA, SAMPLE_ROLES


def _make_mock_judgment(label: str):
    from argus.classifiers.jobs import JobSignal
    return JobSignal(label=label, reasoning="Test reasoning.", confidence=0.85)


@patch("argus.classifiers.jobs.ChatMistralAI")
def test_classify_job_cluster_building_ai_team(mock_llm_class):
    from argus.classifiers.jobs import classify_job_cluster

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("building_ai_team")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    result = classify_job_cluster("OpenAI", SAMPLE_ROLES, SAMPLE_CRITERIA)

    assert result.label == "building_ai_team"
    assert result.confidence == 0.85


@patch("argus.classifiers.jobs.ChatMistralAI")
def test_classify_job_cluster_routine(mock_llm_class):
    from argus.classifiers.jobs import classify_job_cluster

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _make_mock_judgment("routine_backfill")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    mock_llm_class.return_value = mock_llm

    routine_roles = [{"id": "u1", "title": "Office Manager", "location": "NYC"}]
    result = classify_job_cluster("OpenAI", routine_roles, SAMPLE_CRITERIA)

    assert result.label == "routine_backfill"
