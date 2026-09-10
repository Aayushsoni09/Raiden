from unittest.mock import MagicMock, patch

import pytest

from src.daemon.run import _looks_like_action_request, handle_command

CATALOG_ENTRY_INVESTIGATE_ONLY = {
    "id": "example-project",
    "clouds": [{"provider": "gcp", "project_id": "x", "regions": ["asia-south1"], "services": []}],
    "free_form_actions_allowed": False,
}

CATALOG_ENTRY_ACTION_ENABLED = {
    "id": "example-project-aws",
    "clouds": [{"provider": "aws", "account_id": "x", "regions": ["ap-south-1"], "services": []}],
    "free_form_actions_allowed": True,
}


@pytest.mark.parametrize("text,expected", [
    ("make an instance in ap-south-1", True),
    ("create a new bucket", True),
    ("the api service is down", False),
    ("just checking on things", False),
])
def test_looks_like_action_request(text, expected):
    assert _looks_like_action_request(text) is expected


def test_handle_command_routes_report_to_investigate():
    with patch("src.daemon.run.speak") as mock_speak, patch(
        "src.daemon.run.record_from_mic", return_value="fake.wav"
    ), patch("src.daemon.run.transcribe", return_value="the api service is down"), patch(
        "src.daemon.run.resolve_project", return_value=CATALOG_ENTRY_INVESTIGATE_ONLY
    ), patch("src.daemon.run.investigate", return_value="hypotheses text") as mock_investigate:
        handle_command()

    mock_investigate.assert_called_once()
    assert mock_speak.call_count == 3  # "Yes?", "Investigating X.", then final reply
    assert mock_speak.call_args_list[-1][0][0] == "hypotheses text"


def test_handle_command_routes_action_request_to_proposer():
    with patch("src.daemon.run.speak") as mock_speak, patch(
        "src.daemon.run.record_from_mic", return_value="fake.wav"
    ), patch("src.daemon.run.transcribe", return_value="make an instance in ap-south-1"), patch(
        "src.daemon.run.resolve_project", return_value=CATALOG_ENTRY_ACTION_ENABLED
    ), patch(
        "src.daemon.run.propose_action", return_value=(["aws", "ec2", "run-instances"], "Launch an instance.")
    ) as mock_propose:
        handle_command()

    mock_propose.assert_called_once()
    final_reply = mock_speak.call_args_list[-1][0][0]
    assert "run-instances" in final_reply
    assert "frontend" in final_reply.lower()


def test_handle_command_blocks_action_when_not_opted_in():
    with patch("src.daemon.run.speak") as mock_speak, patch(
        "src.daemon.run.record_from_mic", return_value="fake.wav"
    ), patch("src.daemon.run.transcribe", return_value="make an instance"), patch(
        "src.daemon.run.resolve_project", return_value=CATALOG_ENTRY_INVESTIGATE_ONLY
    ), patch("src.daemon.run.propose_action") as mock_propose:
        handle_command()

    mock_propose.assert_not_called()
    assert "aren't enabled" in mock_speak.call_args_list[-1][0][0].lower()


def test_handle_command_reports_ambiguous_project():
    from src.resolver.resolver import AmbiguousProjectError

    with patch("src.daemon.run.speak") as mock_speak, patch(
        "src.daemon.run.record_from_mic", return_value="fake.wav"
    ), patch("src.daemon.run.transcribe", return_value="something ambiguous"), patch(
        "src.daemon.run.resolve_project", side_effect=AmbiguousProjectError("something ambiguous", ["a", "b"])
    ):
        handle_command()

    assert "matches multiple projects" in mock_speak.call_args_list[-1][0][0]


def test_handle_command_handles_empty_transcription():
    with patch("src.daemon.run.speak") as mock_speak, patch(
        "src.daemon.run.record_from_mic", return_value="fake.wav"
    ), patch("src.daemon.run.transcribe", return_value="   "):
        handle_command()

    assert "didn't catch" in mock_speak.call_args_list[-1][0][0].lower()
