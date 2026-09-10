"""Raiden voice daemon: always listens in the background for a wake
phrase ("hey raiden" by default), then records one command, transcribes
it, resolves which project it's about, and either investigates (read
-only) or drafts a free-form action — speaking the result back via
Piper TTS. No browser required.

Run with:
    python -m src.daemon.run

Safety note: voice can propose a free-form action and read it back, but
it never executes one. Mishearing a spoken "yes"/"confirm" is not a
reliable enough confirmation channel for something that mutates real
infrastructure — actually running a proposed command still requires the
Streamlit frontend's explicit review-and-click flow (frontend/app.py).
"""

import os

from src.daemon.wake_listener import DEFAULT_WAKE_PHRASE, listen_for_wake_phrase
from src.investigator import investigate
from src.investigator.action_proposer import ActionProposalError, propose_action
from src.resolver.resolver import (
    AmbiguousProjectError,
    ProjectNotFoundError,
    resolve_project,
)
from src.voice import safe_print
from src.voice.stt.transcribe import record_from_mic, transcribe
from src.voice.tts.speak import speak

DEFAULT_TTS_MODEL = os.environ.get("RAIDEN_TTS_MODEL", ".voice-models/en_US-lessac-medium.onnx")
DEFAULT_CATALOG_DIR = os.environ.get("RAIDEN_CATALOG_DIR", "catalog")
DEFAULT_WHISPER_MODEL = os.environ.get("RAIDEN_WHISPER_MODEL", "small")
DEFAULT_LLM_MODEL = os.environ.get("RAIDEN_LLM_MODEL")  # None -> investigator/proposer's own default

# Rough, best-effort routing: presence of any of these words treats the
# command as an infrastructure-change request (drafted via action_proposer)
# rather than a status/incident report (handled by the read-only investigator).
ACTION_VERBS = {
    "make", "create", "launch", "start", "deploy", "provision",
    "spin", "allocate", "build", "scale", "restart", "stop",
}


def _looks_like_action_request(text):
    return bool(set(text.lower().split()) & ACTION_VERBS)


def handle_command(
    catalog_dir=DEFAULT_CATALOG_DIR,
    tts_model=DEFAULT_TTS_MODEL,
    whisper_model=DEFAULT_WHISPER_MODEL,
    llm_model=DEFAULT_LLM_MODEL,
):
    speak("Yes?", tts_model)
    wav_path = record_from_mic(seconds=6)
    report = transcribe(wav_path, model_size=whisper_model)
    safe_print(f"You said: {report}")

    if not report.strip():
        speak("I didn't catch that.", tts_model)
        return

    try:
        entry = resolve_project(report, catalog_dir)
    except (ProjectNotFoundError, AmbiguousProjectError) as e:
        speak(str(e), tts_model)
        return

    llm_kwargs = {"model": llm_model} if llm_model else {}

    if _looks_like_action_request(report):
        if not entry.get("free_form_actions_allowed", False):
            speak(f"Free-form actions aren't enabled for {entry['id']}.", tts_model)
            return
        try:
            command, explanation = propose_action(report, entry, **llm_kwargs)
        except ActionProposalError as e:
            speak(f"I couldn't draft a command: {e}", tts_model)
            return
        if command:
            speak(
                f"{explanation} Proposed command: {' '.join(command)}. "
                "Open the Raiden frontend to review and confirm before it runs anything.",
                tts_model,
            )
        else:
            speak(explanation, tts_model)
    else:
        speak(f"Investigating {entry['id']}.", tts_model)
        hypotheses = investigate(report, entry, **llm_kwargs)
        speak(hypotheses, tts_model)


def main(wake_phrase=DEFAULT_WAKE_PHRASE, tts_model=DEFAULT_TTS_MODEL):
    def on_wake(heard_text):
        safe_print(f"Wake phrase heard in: {heard_text!r}")
        try:
            handle_command()
        except Exception as e:  # keep the daemon alive across a single bad turn
            safe_print(f"Error handling command: {e}")

    safe_print(f"Listening for '{wake_phrase}'... (Ctrl+C to stop)")
    # Confirms the daemon process itself is up and audio output works,
    # independent of whether wake-word detection ever fires — otherwise
    # there's no feedback distinguishing "not listening yet" from
    # "listening but didn't catch the wake phrase."
    speak("Raiden is now listening.", tts_model)
    listen_for_wake_phrase(on_wake, wake_phrase=wake_phrase)


if __name__ == "__main__":
    main()
