from __future__ import annotations

import io
import wave
from array import array


def ensure_even_length(audio: bytes) -> bytes:
    if len(audio) % 2 == 0:
        return audio
    return audio[:-1]


def crossfade_pcm16_mono(chunks: list[bytes], crossfade_ms: int, sample_rate: int = 44_100) -> bytes:
    """Join PCM16 mono chunks with a short linear crossfade to reduce choppiness."""
    if not chunks:
        return b""
    if len(chunks) == 1:
        return ensure_even_length(chunks[0])

    fade_samples = max(0, (crossfade_ms * sample_rate) // 1000)
    output = array("h")

    for idx, raw_chunk in enumerate(chunks):
        chunk = array("h")
        chunk.frombytes(ensure_even_length(raw_chunk))
        if idx == 0:
            output.extend(chunk)
            continue

        overlap = min(fade_samples, len(output), len(chunk))
        if overlap <= 0:
            output.extend(chunk)
            continue

        start = len(output) - overlap
        for i in range(overlap):
            fade_out = (overlap - i) / overlap
            fade_in = i / overlap
            mixed = int(output[start + i] * fade_out + chunk[i] * fade_in)
            output[start + i] = max(-32768, min(32767, mixed))

        output.extend(chunk[overlap:])

    return output.tobytes()


def pcm16_mono_to_wav_bytes(pcm_audio: bytes, sample_rate: int = 44_100) -> bytes:
    """Wrap raw PCM16 mono bytes into a WAV container."""
    clean = ensure_even_length(pcm_audio)
    with io.BytesIO() as stream:
        with wave.open(stream, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(clean)
        return stream.getvalue()
