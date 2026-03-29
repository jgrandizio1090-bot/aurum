from __future__ import annotations

import argparse
from pathlib import Path

from .config import PipelineConfig
from .pipeline import VoiceSynthesisPipeline
from .providers import ElevenLabsProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate smooth speech audio via ElevenLabs.")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--output", required=True, help="Output WAV path")
    parser.add_argument("--crossfade-ms", type=int, default=24, help="Crossfade duration between chunks")
    parser.add_argument("--no-cache", action="store_true", help="Disable in-memory chunk cache")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = PipelineConfig.from_env()
    if args.no_cache:
        config.cache_enabled = False

    provider = ElevenLabsProvider(config=config)
    try:
        pipeline = VoiceSynthesisPipeline(provider=provider, config=config, crossfade_ms=max(0, args.crossfade_ms))
        wav_audio = pipeline.synthesize_wav(args.text)
    finally:
        provider.close()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(wav_audio)


if __name__ == "__main__":
    main()
