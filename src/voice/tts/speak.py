"""Text-to-speech via local Piper TTS.

POC scope only. Requires the `voice` extra:
    pip install -e ".[voice]"
And a downloaded Piper voice model (see https://github.com/rhasspy/piper).

Usage:
    echo "investigating the api service" | python src/voice/tts/speak.py
    python src/voice/tts/speak.py --text "hello" --voice en_US-lessac-medium
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def speak(text: str, voice: str = "en_US-lessac-medium") -> None:
    """Shell out to the `piper` CLI if available, otherwise print a hint."""
    if shutil.which("piper") is None:
        raise SystemExit(
            "piper CLI not found on PATH. Install with: pip install piper-tts, "
            "then download a voice model per https://github.com/rhasspy/piper"
        )
    # piper reads text on stdin, writes wav to stdout/file, and can pipe
    # straight to an audio player. Simplest POC path: play via `aplay`/`afplay`.
    proc = subprocess.Popen(
        ["piper", "--model", voice, "--output-raw"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    player_cmd = ["afplay", "-"] if shutil.which("afplay") else ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]
    player = subprocess.Popen(player_cmd, stdin=proc.stdout)
    proc.communicate(input=text.encode("utf-8"))
    player.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Raiden TTS (local Piper)")
    parser.add_argument("--text", type=str, help="Text to speak (else reads stdin)")
    parser.add_argument("--voice", type=str, default="en_US-lessac-medium")
    args = parser.parse_args()

    text = args.text or sys.stdin.read()
    speak(text.strip(), voice=args.voice)


if __name__ == "__main__":
    main()

