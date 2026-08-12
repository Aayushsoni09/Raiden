"""Speech-to-text via local Whisper (openai-whisper).

Thin wrapper — POC scope only. Requires the voice extras:
    pip install -r requirements-voice.txt

Usage:
    python -m src.voice.stt.transcribe --mic          # record from mic, transcribe
    python -m src.voice.stt.transcribe --file foo.wav  # transcribe a file
"""

import argparse
import sys
import tempfile


def record_from_mic(seconds=6, samplerate=16000):
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as e:
        raise SystemExit(
            "Mic recording needs sounddevice + soundfile. "
            "Install with: pip install -r requirements-voice.txt"
        ) from e

    print(f"Recording {seconds}s from default mic... speak now.", file=sys.stderr)
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="float32")
    sd.wait()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, audio, samplerate)
    return tmp.name


def transcribe(path, model_size="base"):
    try:
        import whisper
    except ImportError as e:
        raise SystemExit(
            "Transcription needs openai-whisper. Install with: pip install -r requirements-voice.txt"
        ) from e
    model = whisper.load_model(model_size)
    result = model.transcribe(path)
    return result["text"].strip()


def main():
    parser = argparse.ArgumentParser(description="Raiden STT (local Whisper)")
    parser.add_argument("--mic", action="store_true", help="Record from the default microphone")
    parser.add_argument("--file", type=str, help="Path to a WAV/MP3 file to transcribe")
    parser.add_argument("--model", type=str, default="base", help="Whisper model size")
    parser.add_argument("--seconds", type=int, default=6, help="Recording length for --mic")
    args = parser.parse_args()

    if args.mic:
        path = record_from_mic(seconds=args.seconds)
    elif args.file:
        path = args.file
    else:
        parser.error("Pass --mic or --file")
        return

    print(transcribe(path, model_size=args.model))


if __name__ == "__main__":
    main()
