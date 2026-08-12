"""Speech-to-text via local Whisper (openai-whisper or whisper.cpp).

This is a thin wrapper — POC scope only. Requires the `voice` extra:
    pip install -e ".[voice]"

Usage:
    python src/voice/stt/transcribe.py --mic          # record from mic, transcribe
    python src/voice/stt/transcribe.py --file foo.wav # transcribe a file
"""
from __future__ import annotations

import argparse
import sys
import tempfile


def _record_from_mic(seconds: int = 6, samplerate: int = 16000) -> str:
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
    except ImportError as e:
        raise SystemExit(
            "Mic recording needs sounddevice + soundfile. "
            "Install with: pip install -e '.[voice]'"
        ) from e

    print(f"Recording {seconds}s from default mic... speak now.", file=sys.stderr)
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="float32")
    sd.wait()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, audio, samplerate)
    return tmp.name


def transcribe(path: str, model_size: str = "base") -> str:
    try:
        import whisper
    except ImportError as e:
        raise SystemExit(
            "Transcription needs openai-whisper. Install with: pip install -e '.[voice]'"
        ) from e
    model = whisper.load_model(model_size)
    result = model.transcribe(path)
    return result["text"].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Raiden STT (local Whisper)")
    parser.add_argument("--mic", action="store_true", help="Record from the default microphone")
    parser.add_argument("--file", type=str, help="Path to a WAV/MP3 file to transcribe")
    parser.add_argument("--model", type=str, default="base", help="Whisper model size")
    parser.add_argument("--seconds", type=int, default=6, help="Recording length for --mic")
    args = parser.parse_args()

    if args.mic:
        path = _record_from_mic(seconds=args.seconds)
    elif args.file:
        path = args.file
    else:
        parser.error("Pass --mic or --file")
        return

    print(transcribe(path, model_size=args.model))


if __name__ == "__main__":
    main()

