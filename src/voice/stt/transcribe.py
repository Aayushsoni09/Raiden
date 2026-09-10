"""Speech-to-text via local Whisper (openai-whisper).

Thin wrapper — POC scope only. Requires the voice extras:
    pip install -r requirements-voice.txt

Usage:
    python -m src.voice.stt.transcribe --mic          # record from mic, transcribe
    python -m src.voice.stt.transcribe --file foo.wav  # transcribe a file
"""

import argparse
import os
import sys
import tempfile

from src.voice import safe_print

# Not every "default" input device Windows/PortAudio picks actually carries
# mic signal — e.g. a Bluetooth headset's A2DP-profile entries are
# playback-only or near-silent for input, while its separate Hands-Free
# Profile entry (a different device index) is the one with a real signal.
# Confirmed live on this machine that a WDM-KS Bluetooth HFP device can also
# need a *different* device index for one-shot sd.rec() than the one that
# works for continuous streaming (src/daemon/wake_listener.py) — and that
# it silently returns garbage (not an error) for a dtype it doesn't support,
# e.g. float32 came back with amplitudes ~1e17. int16 is the reliable
# format. Run scripts/list_input_devices.py --test <index> to check.
DEFAULT_INPUT_DEVICE = os.environ.get("RAIDEN_COMMAND_INPUT_DEVICE") or os.environ.get("RAIDEN_INPUT_DEVICE")
if DEFAULT_INPUT_DEVICE is not None:
    DEFAULT_INPUT_DEVICE = int(DEFAULT_INPUT_DEVICE)


def record_from_mic(seconds=6, samplerate=16000, device=DEFAULT_INPUT_DEVICE):
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as e:
        raise SystemExit(
            "Mic recording needs sounddevice + soundfile. "
            "Install with: pip install -r requirements-voice.txt"
        ) from e

    print(f"Recording {seconds}s from mic (device={device})... speak now.", file=sys.stderr)
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="int16", device=device)
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

    safe_print(transcribe(path, model_size=args.model))


if __name__ == "__main__":
    main()
