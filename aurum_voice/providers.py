from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import PipelineConfig


class TTSProviderError(RuntimeError):
    """Raised when a TTS provider cannot produce audio."""


@dataclass(slots=True)
class ElevenLabsProvider:
    """ElevenLabs text-to-speech provider returning PCM16 mono audio bytes."""

    config: PipelineConfig
    base_url: str = "https://api.elevenlabs.io"

    def __post_init__(self) -> None:
        self._client = httpx.Client(timeout=self.config.request_timeout_seconds)

    def synthesize_chunk(self, text: str) -> bytes:
        if not text.strip():
            return b""

        payload = {
            "text": text,
            "model_id": self.config.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": self.config.elevenlabs_api_key,
            "accept": "application/octet-stream",
            "content-type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                response = self._client.post(
                    f"{self.base_url}/v1/text-to-speech/{self.config.voice_id}",
                    params={"output_format": "pcm_44100"},
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.content
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 >= self.config.max_retries:
                    break
                # Basic exponential backoff with a short base keeps latency low.
                time.sleep(0.25 * (2**attempt))

        raise TTSProviderError(f"ElevenLabs request failed after retries: {last_error}") from last_error

    def close(self) -> None:
        self._client.close()
