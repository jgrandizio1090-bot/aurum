from __future__ import annotations

import base64
import re
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, jsonify, render_template, request

from .audio_utils import crossfade_pcm16_mono, master_pcm16_mono, pcm16_mono_to_wav_bytes
from .config import PipelineConfig
from .pipeline import VoiceSynthesisPipeline
from .providers import ElevenLabsProvider, TTSProviderError

_SPEAKER_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>[abAB])\]\s*:?|(?P<plain>[abAB])\s*:)\s*(?P<text>.+?)\s*$"
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).with_name("templates")),
        static_folder=str(Path(__file__).with_name("static")),
    )

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/api/synthesize")
    def synthesize():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"error": "Text is required."}), 400

        crossfade_ms = int(payload.get("crossfade_ms", 24))
        stability = float(payload.get("stability", 0.5))
        similarity_boost = float(payload.get("similarity_boost", 0.75))
        style = float(payload.get("style", 0.0))
        speaker_boost = bool(payload.get("speaker_boost", True))
        quality = str(payload.get("quality", "balanced"))
        script_mode = str(payload.get("script_mode", "single")).strip().lower()
        voices = payload.get("voices", {}) if isinstance(payload.get("voices"), dict) else {}

        mastering = payload.get("mastering", {}) if isinstance(payload.get("mastering"), dict) else {}
        mastering_enabled = bool(mastering.get("enabled", True))
        normalize_enabled = bool(mastering.get("normalize", True))
        fade_ms = int(mastering.get("fade_ms", 12))
        peak_target = float(mastering.get("peak_target", 0.92))

        voice_settings = {
            "stability": _clamp(stability),
            "similarity_boost": _clamp(similarity_boost),
            "style": _clamp(style),
            "use_speaker_boost": speaker_boost,
        }

        try:
            base_config = _resolve_quality_config(PipelineConfig.from_env(), quality)
            segments = _extract_segments(text, script_mode)
            segment_audio: list[bytes] = []
            for speaker, segment_text in segments:
                requested_voice = str(voices.get(speaker, "")).strip()
                voice_id = requested_voice or base_config.voice_id
                segment_config = replace(base_config, voice_id=voice_id)
                segment_audio.append(
                    _synthesize_segment_pcm(
                        text=segment_text,
                        config=segment_config,
                        crossfade_ms=max(0, crossfade_ms),
                        voice_settings=voice_settings,
                    )
                )

            combined_pcm = crossfade_pcm16_mono(
                segment_audio,
                crossfade_ms=max(0, min(20, crossfade_ms)),
                sample_rate=44_100,
            )
            if mastering_enabled:
                combined_pcm = master_pcm16_mono(
                    combined_pcm,
                    sample_rate=44_100,
                    normalize=normalize_enabled,
                    fade_ms=max(0, fade_ms),
                    peak_target=_clamp(peak_target, lower=0.1),
                )
            wav_bytes = pcm16_mono_to_wav_bytes(combined_pcm, sample_rate=44_100)
        except (ValueError, TTSProviderError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "Synthesis failed due to an unexpected error."}), 500

        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        return jsonify({"audio_b64": audio_b64})

    @app.post("/api/synthesize/save")
    def synthesize_to_file():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"error": "Text is required."}), 400

        try:
            config = PipelineConfig.from_env()
            provider = ElevenLabsProvider(config=config)
            try:
                pipeline = VoiceSynthesisPipeline(provider=provider, config=config)
                wav_bytes = pipeline.synthesize_wav(text)
            finally:
                provider.close()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

        with NamedTemporaryFile(delete=False, suffix=".wav", prefix="aurum_", dir="/tmp") as temp:
            temp.write(wav_bytes)
            path = temp.name
        return jsonify({"path": path})

    return app


def _resolve_quality_config(config: PipelineConfig, quality: str) -> PipelineConfig:
    if quality == "expressive":
        return replace(config, model_id="eleven_multilingual_v2")
    if quality == "fast":
        return replace(config, model_id="eleven_turbo_v2_5")
    return config


def _extract_segments(text: str, script_mode: str) -> list[tuple[str, str]]:
    if script_mode != "multi":
        return [("A", text)]

    segments: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SPEAKER_RE.match(line)
        if match:
            speaker = (match.group("bracket") or match.group("plain") or "A").upper()
            segment_text = match.group("text").strip()
        else:
            speaker = "A"
            segment_text = line
        if segment_text:
            segments.append((speaker, segment_text))
    return segments or [("A", text)]


def _synthesize_segment_pcm(
    *,
    text: str,
    config: PipelineConfig,
    crossfade_ms: int,
    voice_settings: dict[str, float | bool],
) -> bytes:
    provider = ElevenLabsProvider(config=config, voice_settings=voice_settings)
    try:
        pipeline = VoiceSynthesisPipeline(provider=provider, config=config, crossfade_ms=crossfade_ms)
        return pipeline.synthesize_pcm(text)
    finally:
        provider.close()


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
