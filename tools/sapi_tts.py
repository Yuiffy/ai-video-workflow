"""Offline Windows SAPI TTS source for the local RVC pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path

import win32com.client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice", default="Microsoft Huihui")
    parser.add_argument("--rate", type=int, default=0)
    args = parser.parse_args()
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    matches = [token for token in voice.GetVoices() if args.voice in token.GetDescription()]
    if not matches:
        raise ValueError(f"SAPI voice is not installed: {args.voice}")
    voice.Voice = matches[0]
    voice.Rate = args.rate
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stream.Open(str(target), 3, False)
    voice.AudioOutputStream = stream
    voice.Speak(args.text)
    stream.Close()
    print(f"tts: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
