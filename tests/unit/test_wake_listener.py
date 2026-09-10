import json
import threading
from unittest.mock import MagicMock, patch

from src.daemon.wake_listener import listen_for_wake_phrase


def _run_one_callback(mock_recognizer_cls, accept_waveform_return, result_json, partial_json):
    """Drives listen_for_wake_phrase for exactly one audio callback, using a
    stop_event that's already set so the blocking sd.sleep loop exits
    immediately after the stream context manager registers the callback."""
    mock_recognizer = MagicMock()
    mock_recognizer.AcceptWaveform.return_value = accept_waveform_return
    mock_recognizer.Result.return_value = json.dumps(result_json)
    mock_recognizer.PartialResult.return_value = json.dumps(partial_json)
    mock_recognizer_cls.return_value = mock_recognizer

    on_wake = MagicMock()
    captured_callback = {}

    class FakeStream:
        def __init__(self, *args, **kwargs):
            captured_callback["fn"] = kwargs["callback"]

        def __enter__(self):
            captured_callback["fn"](b"\x00\x00" * 8000, 8000, None, None)
            return self

        def __exit__(self, *a):
            return False

    stop_event = threading.Event()
    stop_event.set()

    with patch("src.daemon.wake_listener.vosk.Model"), patch(
        "src.daemon.wake_listener.vosk.KaldiRecognizer", mock_recognizer_cls
    ), patch("src.daemon.wake_listener.sd.RawInputStream", FakeStream), patch(
        "src.daemon.wake_listener.sd.sleep"
    ):
        listen_for_wake_phrase(on_wake, stop_event=stop_event)

    return mock_recognizer, on_wake


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_uses_partial_result_when_no_utterance_boundary(mock_recognizer_cls):
    # Regression: an earlier version called Result() unconditionally, which
    # force-finalizes and resets Vosk's state every callback regardless of
    # whether AcceptWaveform() actually reached a boundary.
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=False,
        result_json={"text": "should not be used"},
        partial_json={"partial": "hey raiden"},
    )
    recognizer.Result.assert_not_called()
    recognizer.PartialResult.assert_called_once()
    on_wake.assert_called_once()


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_uses_final_result_at_utterance_boundary(mock_recognizer_cls):
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=True,
        result_json={"text": "hey raiden"},
        partial_json={"partial": "should not be used"},
    )
    recognizer.PartialResult.assert_not_called()
    on_wake.assert_called_once()


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_fuzzy_match_catches_phonetic_misrecognition(mock_recognizer_cls):
    # Vosk's small model doesn't have "raiden" in its vocabulary at all and
    # consistently transcribes it as "raden" instead — exact substring
    # matching would never fire on real audio.
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=True,
        result_json={"text": "hey raden the api is down"},
        partial_json={},
    )
    on_wake.assert_called_once()


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_unrelated_speech_does_not_trigger(mock_recognizer_cls):
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=True,
        result_json={"text": "can you restart the ecs cluster for me"},
        partial_json={},
    )
    on_wake.assert_not_called()


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_short_fragment_does_not_falsely_trigger(mock_recognizer_cls):
    # Regression: confirmed live that a lone "he" scored above
    # WAKE_MATCH_THRESHOLD against "hey raiden" via partial_ratio, since
    # that scorer normalizes by the shorter string's length.
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=True,
        result_json={"text": "he"},
        partial_json={},
    )
    on_wake.assert_not_called()


@patch("src.daemon.wake_listener.vosk.KaldiRecognizer")
def test_resets_recognizer_after_wake_to_avoid_retrigger(mock_recognizer_cls):
    recognizer, on_wake = _run_one_callback(
        mock_recognizer_cls,
        accept_waveform_return=True,
        result_json={"text": "hey raiden"},
        partial_json={},
    )
    recognizer.Reset.assert_called_once()
