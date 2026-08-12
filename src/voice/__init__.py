import sys


def safe_print(text, encoding=None):
    """print() that survives Windows consoles defaulting to cp1252, which
    can't encode every character Whisper might transcribe (accents, unusual
    punctuation)."""
    encoding = encoding or sys.stdout.encoding or "utf-8"
    print(str(text).encode(encoding, errors="replace").decode(encoding))
