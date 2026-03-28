from array import array

from aurum_voice.audio_utils import crossfade_pcm16_mono, pcm16_mono_to_wav_bytes


def _samples_to_pcm(samples: list[int]) -> bytes:
    data = array("h", samples)
    return data.tobytes()


def test_crossfade_reduces_discontinuity() -> None:
    left = _samples_to_pcm([1000] * 100)
    right = _samples_to_pcm([-1000] * 100)
    joined = crossfade_pcm16_mono([left, right], crossfade_ms=1, sample_rate=1000)

    samples = array("h")
    samples.frombytes(joined)
    # With a 1 ms fade at 1kHz we overlap 1 sample and reduce abrupt jump.
    assert len(samples) == 199
    assert samples[98] == 1000
    assert -1000 <= samples[99] <= 1000


def test_pcm_to_wav_wraps_header() -> None:
    pcm = _samples_to_pcm([0, 1, -1, 4, -4])
    wav_bytes = pcm16_mono_to_wav_bytes(pcm, sample_rate=44_100)
    assert wav_bytes[:4] == b"RIFF"
    assert b"WAVE" in wav_bytes[:16]
