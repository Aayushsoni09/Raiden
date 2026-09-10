#!/usr/bin/env python3
"""List audio input devices and their index, for setting RAIDEN_INPUT_DEVICE.

A "default" input device reported by the OS/PortAudio doesn't always carry
real microphone signal — e.g. a Bluetooth headset commonly exposes several
device entries and only one (usually its Hands-Free Profile entry, not its
stereo/A2DP entry) actually delivers mic audio. If voice input is silent or
garbled, run this, then --test each candidate to find the one with a real
signal:

    python scripts/list_input_devices.py
    python scripts/list_input_devices.py --test 19

Once you find the right index, set it before running the daemon/frontend:
    export RAIDEN_INPUT_DEVICE=19
"""

import argparse
import sys

import numpy as np
import sounddevice as sd


def list_devices():
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"{i} - {d['name']} (default_samplerate={d['default_samplerate']:.0f})")


def test_device(index, seconds=3):
    info = sd.query_devices(index)
    samplerate = int(info["default_samplerate"])
    print(f"Recording {seconds}s from device {index} ({info['name']!r}) — talk now...", file=sys.stderr)
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="int16", device=index)
    sd.wait()
    max_amp = int(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    print(f"max amplitude: {max_amp} (out of 32768)  rms: {rms:.1f}")
    if max_amp < 500:
        print("Looks silent/near-silent — probably not the right device.")
    else:
        print("Real signal detected.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", type=int, metavar="INDEX", help="Record a few seconds from this device index to check for real signal")
    parser.add_argument("--seconds", type=int, default=3, help="Recording length for --test")
    args = parser.parse_args()

    if args.test is not None:
        test_device(args.test, seconds=args.seconds)
    else:
        list_devices()


if __name__ == "__main__":
    main()
