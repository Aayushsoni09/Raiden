from unittest.mock import MagicMock, patch

import pytest

from src.voice import safe_print
from src.voice.loop import run_once
from src.voice.tts.speak import speak


def test_safe_print_survives_unencodable_characters(capsys):
    # Simulates a Windows console's cp1252 stdout, which can't encode this text.
    safe_print("emoji \U0001F600 and curly ‘quotes’", encoding="cp1252")
    captured = capsys.readouterr()
    assert "emoji" in captured.out


def test_speak_requires_piper_on_path():
    with patch("src.voice.tts.speak.shutil.which", return_value=None):
        with pytest.raises(SystemExit):
            speak("hello", "some-model.onnx")


def test_run_once_reports_ambiguous_or_unknown_project(tmp_path):
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "x.yaml").write_text(
        "id: x\naliases: [totally-specific-alias]\n", encoding="utf-8"
    )

    with patch("src.voice.loop.record_from_mic", return_value="fake.wav"), patch(
        "src.voice.loop.transcribe", return_value="something nobody will match"
    ), patch("src.voice.loop.speak") as mock_speak:
        run_once(catalog_dir=str(catalog_dir))

    # Should have spoken the opening prompt and then an error, never reached investigate.
    assert mock_speak.call_count == 2
    assert "no catalog entry" in mock_speak.call_args_list[-1][0][0].lower()
