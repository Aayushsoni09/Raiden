from unittest.mock import MagicMock, patch

import pytest

from src.investigator.action_proposer import ActionProposalError, propose_action

CATALOG_ENTRY = {
    "id": "example-project-aws",
    "clouds": [{"provider": "aws", "account_id": "123456789012", "regions": ["ap-south-1"]}],
}


def test_propose_action_parses_valid_json():
    with patch("src.investigator.action_proposer.ChatOllama") as mock_chat:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='{"command": ["aws", "ec2", "run-instances", "--region", "ap-south-1"], '
                    '"explanation": "Launch an EC2 instance in ap-south-1."}'
        )
        mock_chat.return_value = mock_llm

        command, explanation = propose_action("make an instance in ap-south-1", CATALOG_ENTRY)

    assert command == ["aws", "ec2", "run-instances", "--region", "ap-south-1"]
    assert "ap-south-1" in explanation


def test_propose_action_handles_surrounding_prose():
    with patch("src.investigator.action_proposer.ChatOllama") as mock_chat:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='Sure, here you go:\n{"command": ["gcloud", "compute", "instances", "list"], '
                    '"explanation": "List instances."}\nLet me know if you need anything else.'
        )
        mock_chat.return_value = mock_llm

        command, _ = propose_action("show me instances", CATALOG_ENTRY)

    assert command == ["gcloud", "compute", "instances", "list"]


def test_propose_action_raises_on_non_json_response():
    with patch("src.investigator.action_proposer.ChatOllama") as mock_chat:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="I cannot help with that.")
        mock_chat.return_value = mock_llm

        with pytest.raises(ActionProposalError):
            propose_action("do something", CATALOG_ENTRY)


def test_propose_action_empty_command_when_model_lacks_info():
    with patch("src.investigator.action_proposer.ChatOllama") as mock_chat:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='{"command": [], "explanation": "Need to know which AMI to use."}'
        )
        mock_chat.return_value = mock_llm

        command, explanation = propose_action("make an instance", CATALOG_ENTRY)

    assert command == []
    assert "AMI" in explanation
