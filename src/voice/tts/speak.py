"""Text-to-speech via local Piper TTS.

POC scope only. Requires the `piper` CLI on PATH and a downloaded voice
model (.onnx + .onnx.json): https://github.com/rhasspy/piper

Usage:
    echo "investigating the api service" | python -m src.voice.tts.speak --model path/to/voice.onnx
    python -m src.voice.tts.speak --text "hello" --model path/to/voice.onnx
"""

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile

from scripts._shell import resolve


def speak(text, model_path):
    """Synthesize `text` with Piper and play it back.

    Windows has no aplay/afplay, so we always render to a temp WAV file
    and play it — simpler and more portable than piping raw PCM to a
    platform-specific player.
    """
    if shutil.which("piper") is None:
        raise SystemExit(
            "piper CLI not found on PATH. Install with: pip install piper-tts, "
            "then download a voice model (.onnx + .onnx.json) per https://github.com/rhasspy/piper"
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    proc = subprocess.run(
        [resolve("piper"), "--model", model_path, "--output-file", wav_path],
        input=text.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"piper failed: {proc.stderr.decode('utf-8', errors='replace')}")

    _play(wav_path)


def _play(wav_path):
    if platform.system() == "Windows":
        subprocess.run(
            [
                "powershell", "-NonInteractive", "-Command",
                f"(New-Object System.Media.SoundPlayer '{wav_path}').PlaySync()",
            ],
            check=True,
        )
    elif shutil.which("afplay"):
        subprocess.run(["afplay", wav_path], check=True)
    else:
        subprocess.run(["aplay", wav_path], check=True)


def main():
    parser = argparse.ArgumentParser(description="Raiden TTS (local Piper)")
    parser.add_argument("--text", type=str, help="Text to speak (else reads stdin)")
    parser.add_argument("--model", type=str, required=True, help="Path to a Piper .onnx voice model")
    args = parser.parse_args()

    text = args.text or sys.stdin.read()
    speak(text.strip(), model_path=args.model)


if __name__ == "__main__":
    main()
