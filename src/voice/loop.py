"""Full voice loop: mic -> STT -> text investigator -> TTS.

POC glue script. Prefer the text-mode `raiden investigate` command while
iterating on the investigator logic; use this once that's solid.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from src.audit import AuditLogger
from src.executor import RunbookRunner
from src.investigator import Investigator
from src.resolver import AmbiguousMatchError, NoMatchError, Resolver
from src.voice.stt.transcribe import _record_from_mic, transcribe
from src.voice.tts.speak import speak


def run_once(resolver: Resolver, investigator: Investigator) -> None:
    speak("What's broken?")
    wav_path = _record_from_mic(seconds=6)
    text = transcribe(wav_path)
    print(f"You said: {text}")

    # Very naive: assume the first word(s) before " is/are down" etc. is the
    # project name. Real implementation should ask the LLM-free resolver to
    # try matching substrings, or explicitly prompt "which project?".
    try:
        entry = resolver.resolve(text)
    except (NoMatchError, AmbiguousMatchError) as e:
        speak(str(e))
        return

    speak(f"Investigating {entry.id}.")
    result = investigator.investigate(entry, text)
    speak(result.raw_answer)


def main() -> None:
    audit = AuditLogger()
    resolver = Resolver()
    investigator = Investigator(audit_logger=audit)
    RunbookRunner(audit_logger=audit)  # constructed for parity; not used in read-only loop
    run_once(resolver, investigator)


if __name__ == "__main__":
    main()

