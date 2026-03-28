from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .audio_utils import crossfade_pcm16_mono, pcm16_mono_to_wav_bytes
from .config import PipelineConfig
from .providers import ElevenLabsProvider
from .text_utils import TextChunker


@dataclass(slots=True)
class VoiceSynthesisPipeline:
    """High-level synthesis pipeline with chunking, caching, and smoothing."""

    provider: ElevenLabsProvider
    config: PipelineConfig
    crossfade_ms: int = 24
    sample_rate: int = 44_100
    _cache: dict[str, bytes] = field(default_factory=dict)

    def synthesize_pcm(self, text: str) -> bytes:
        chunks = TextChunker(max_chars=self.config.max_chars_per_request).split(text)
        if not chunks:
            return b""

        audio_chunks: list[bytes] = []
        for chunk in chunks:
            cache_key = self._chunk_cache_key(chunk)
            if self.config.cache_enabled and cache_key in self._cache:
                audio_chunks.append(self._cache[cache_key])
                continue

            audio = self.provider.synthesize_chunk(chunk)
            audio_chunks.append(audio)
            if self.config.cache_enabled:
                self._cache[cache_key] = audio

        return crossfade_pcm16_mono(audio_chunks, crossfade_ms=self.crossfade_ms, sample_rate=self.sample_rate)

    def synthesize_wav(self, text: str) -> bytes:
        pcm_audio = self.synthesize_pcm(text)
        return pcm16_mono_to_wav_bytes(pcm_audio, sample_rate=self.sample_rate)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _chunk_cache_key(self, chunk: str) -> str:
        fingerprint = f"{self.config.voice_id}|{self.config.model_id}|{chunk}".encode("utf-8")
        return hashlib.sha256(fingerprint).hexdigest()
