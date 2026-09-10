"""Always-on speech listener that triggers on a wake phrase.

This is NOT a dedicated acoustic wake-word model (like openWakeWord/
Porcupine) — those need a purpose-trained tiny classifier and, for a
custom phrase like "hey raiden", a synthetic-data training pipeline we
don't have the voice diversity to do well locally. Instead this runs
Vosk (offline, free, no training) continuously on the mic and checks
each transcript segment for the wake phrase. Higher background CPU
usage than a real wake-word engine, but works today with zero training
data.

Matching is fuzzy, not exact-substring, for a real reason: Vosk's small
English model's fixed vocabulary doesn't contain "raiden" at all (it
warns "Ignoring word missing in vocabulary: 'raiden'" if you try to
constrain decoding to it), so it always transcribes the name as the
phonetically-closest real word it does know — consistently "raden" in
testing, sometimes "ridden". Exact matching for "raiden" would almost
never fire. rapidfuzz's partial_ratio against known-good recordings
scored 90-100 for correct utterances and topped out around 60 for
unrelated speech, so WAKE_MATCH_THRESHOLD=80 gives a wide margin.
"""

import json
import os
import sys

import sounddevice as sd
import vosk
from rapidfuzz import fuzz

DEBUG = bool(os.environ.get("RAIDEN_WAKE_DEBUG"))

# The small model (~40MB) is fast but has real accuracy limits. A larger
# model (e.g. vosk-model-en-us-0.22, ~1.8GB — download and unzip into
# .voice-models/) may do better in a noisier room or with an unusual mic;
# set RAIDEN_VOSK_MODEL_PATH to switch without a code change.
DEFAULT_MODEL_PATH = os.environ.get("RAIDEN_VOSK_MODEL_PATH", ".voice-models/vosk-model-small-en-us-0.15")
DEFAULT_WAKE_PHRASE = "hey raiden"
SAMPLE_RATE = 16000
WAKE_MATCH_THRESHOLD = 80

# See src/voice/stt/transcribe.py's DEFAULT_INPUT_DEVICE docstring — the
# same "default input device may not carry real mic signal" issue applies
# here (e.g. a Bluetooth headset's Hands-Free-Profile entry vs. its
# separate, silent A2DP entries).
DEFAULT_INPUT_DEVICE = os.environ.get("RAIDEN_INPUT_DEVICE")
if DEFAULT_INPUT_DEVICE is not None:
    DEFAULT_INPUT_DEVICE = int(DEFAULT_INPUT_DEVICE)

vosk.SetLogLevel(-1)


def listen_for_wake_phrase(
    on_wake,
    model_path=DEFAULT_MODEL_PATH,
    wake_phrase=DEFAULT_WAKE_PHRASE,
    stop_event=None,
    device=DEFAULT_INPUT_DEVICE,
):
    """Blocks, continuously listening on the microphone.

    Calls on_wake(heard_text) whenever a transcript segment fuzzy-matches
    `wake_phrase` above WAKE_MATCH_THRESHOLD. Runs until stop_event (a
    threading.Event) is set, or forever if stop_event is None.
    """
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    wake_phrase = wake_phrase.lower()
    # rapidfuzz's partial_ratio is normalized by the SHORTER string's length,
    # so tiny fragments ("he", "hi") can trivially score 100 against "hey
    # raiden" purely by being short — confirmed live: a lone "he" scored
    # above threshold and falsely triggered wake. Require the heard text to
    # be a meaningful fraction of the wake phrase's length before scoring it.
    min_text_len = max(4, len(wake_phrase) // 2)

    def _callback(indata, frames, time_info, status):
        # AcceptWaveform() only returns True at an actual utterance/silence
        # boundary. Calling Result() unconditionally on every chunk (as an
        # earlier version of this did) force-finalizes and resets Vosk's
        # internal state every ~0.5s regardless of that boundary, which
        # never gives it enough context to recognize a two-word phrase.
        # Check PartialResult() (no reset) the rest of the time so the
        # phrase is caught as soon as it's spoken, not only at a pause.
        if recognizer.AcceptWaveform(bytes(indata)):
            text = json.loads(recognizer.Result()).get("text", "")
        else:
            text = json.loads(recognizer.PartialResult()).get("partial", "")

        if DEBUG:
            import numpy as np
            amp = int(np.max(np.abs(np.frombuffer(bytes(indata), dtype="int16"))))
            print(f"[wake debug] callback fired, frames={frames}, amp={amp}, text={text!r}", file=sys.stderr, flush=True)

        if (
            text
            and len(text) >= min_text_len
            and fuzz.partial_ratio(wake_phrase, text.lower()) >= WAKE_MATCH_THRESHOLD
        ):
            recognizer.Reset()  # avoid re-triggering on the same lingering partial
            on_wake(text)

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16", channels=1,
        device=device, callback=_callback,
    ):
        while stop_event is None or not stop_event.is_set():
            sd.sleep(200)
