"""Full voice loop: mic -> STT -> text investigator -> TTS.

POC glue script. Prefer calling src.investigator.investigate directly in
text mode while iterating on the investigator logic; use this once that's
solid.

Naive project resolution: assumes the spoken report is close enough to a
catalog alias for src.resolver.resolve_project's fuzzy match. A production
version would separate "which project" from "what's wrong" instead of
matching the whole utterance.
"""

import os

from src.investigator import investigate
from src.resolver.resolver import (
    AmbiguousProjectError,
    ProjectNotFoundError,
    resolve_project,
)
from src.voice import safe_print
from src.voice.stt.transcribe import record_from_mic, transcribe
from src.voice.tts.speak import speak

DEFAULT_TTS_MODEL = os.environ.get("RAIDEN_TTS_MODEL", ".voice-models/en_US-lessac-medium.onnx")


def run_once(catalog_dir="catalog", audit_log_path="audit/session.jsonl", tts_model=DEFAULT_TTS_MODEL):
    speak("What's broken?", tts_model)
    wav_path = record_from_mic(seconds=6)
    report = transcribe(wav_path)
    safe_print(f"You said: {report}")

    try:
        entry = resolve_project(report, catalog_dir)
    except (ProjectNotFoundError, AmbiguousProjectError) as e:
        speak(str(e), tts_model)
        return

    speak(f"Investigating {entry['id']}.", tts_model)
    hypotheses = investigate(report, entry, audit_log_path=audit_log_path)
    speak(hypotheses, tts_model)


if __name__ == "__main__":
    run_once()
