from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class PipelineConfig:
    """Configurable knobs for smoother voice generation."""

    elevenlabs_api_key: str
    voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    model_id: str = "eleven_multilingual_v2"
    max_chars_per_request: int = 350
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    cache_enabled: bool = True

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        if not key:
            raise ValueError("ELEVENLABS_API_KEY is required.")
        return cls(
            elevenlabs_api_key=key,
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        )
