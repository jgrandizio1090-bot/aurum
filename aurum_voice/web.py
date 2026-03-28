from __future__ import annotations

import base64
import re
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, jsonify, render_template, request

from .audio_utils import crossfade_pcm16_mono, master_pcm16_mono, pcm16_mono_to_wav_bytes
from .config import PipelineConfig
from .intelligence import DomainIntelligenceService
from .pipeline import VoiceSynthesisPipeline
from .providers import ElevenLabsProvider, TTSProviderError

_SPEAKER_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>[abAB])\]\s*:?|(?P<plain>[abAB])\s*:)\s*(?P<text>.+?)\s*$"
)


def create_app(
    *,
    intelligence_service: DomainIntelligenceService | None = None,
    start_background_intelligence: bool = True,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).with_name("templates")),
        static_folder=str(Path(__file__).with_name("static")),
    )
    intelligence = intelligence_service or DomainIntelligenceService()
    app.config["INTELLIGENCE_SERVICE"] = intelligence
    if start_background_intelligence:
        intelligence.start_background_refresh()

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
        use_intelligence = _as_bool(payload.get("use_intelligence", True))
        apply_intelligence_context = _as_bool(payload.get("apply_intelligence_context", False))
        apply_ai_recommendations = _as_bool(payload.get("apply_ai_recommendations", False))

        mastering = payload.get("mastering", {}) if isinstance(payload.get("mastering"), dict) else {}
        mastering_enabled = bool(mastering.get("enabled", True))
        normalize_enabled = bool(mastering.get("normalize", True))
        fade_ms = int(mastering.get("fade_ms", 12))
        peak_target = float(mastering.get("peak_target", 0.92))

        recommendations = intelligence.recommendations_payload() if use_intelligence else {}
        settings_patch = (
            recommendations.get("plan", {}).get("settings_patch", {})
            if isinstance(recommendations, dict)
            else {}
        )
        if apply_ai_recommendations and isinstance(settings_patch, dict):
            quality = str(settings_patch.get("quality", quality))
            script_mode = str(settings_patch.get("script_mode", script_mode))
            crossfade_ms = int(settings_patch.get("crossfade_ms", crossfade_ms))
            stability = float(settings_patch.get("stability", stability))
            similarity_boost = float(settings_patch.get("similarity_boost", similarity_boost))
            style = float(settings_patch.get("style", style))
            speaker_boost = _as_bool(settings_patch.get("speaker_boost", speaker_boost))
            use_intelligence = _as_bool(settings_patch.get("use_intelligence", use_intelligence))
            apply_intelligence_context = _as_bool(
                settings_patch.get("apply_intelligence_context", apply_intelligence_context)
            )
            patched_mastering = settings_patch.get("mastering", {})
            if isinstance(patched_mastering, dict):
                mastering_enabled = _as_bool(patched_mastering.get("enabled", mastering_enabled))
                normalize_enabled = _as_bool(patched_mastering.get("normalize", normalize_enabled))
                fade_ms = int(patched_mastering.get("fade_ms", fade_ms))
                peak_target = float(patched_mastering.get("peak_target", peak_target))

        voice_settings = {
            "stability": _clamp(stability),
            "similarity_boost": _clamp(similarity_boost),
            "style": _clamp(style),
            "use_speaker_boost": speaker_boost,
        }
        intelligence_context = intelligence.get_context_for_prompt() if use_intelligence else ""
        should_apply_context = use_intelligence and apply_intelligence_context and script_mode != "multi"
        enriched_text = _enrich_prompt_text(text, intelligence_context) if should_apply_context else text

        try:
            base_config = _resolve_quality_config(PipelineConfig.from_env(), quality)
            segments = _extract_segments(enriched_text, script_mode)
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
        intelligence_state = intelligence.status()
        return jsonify(
            {
                "audio_b64": audio_b64,
                "intelligence": {
                    "enabled": use_intelligence,
                    "applied_to_audio": should_apply_context,
                    "applied_ai_recommendations": apply_ai_recommendations,
                    "revision": intelligence_state.get("revision", 0),
                    "keywords": intelligence_state.get("keywords", []),
                },
                "recommendations": recommendations,
            }
        )

    @app.get("/api/intelligence/status")
    def intelligence_status():
        return jsonify(intelligence.status())

    @app.post("/api/intelligence/refresh")
    def intelligence_refresh():
        force = _as_bool((request.get_json(silent=True) or {}).get("force", False))
        threading.Thread(target=intelligence.refresh_now, kwargs={"force": force}, daemon=True).start()
        return jsonify({"ok": True})

    @app.post("/api/intelligence/enhance")
    def intelligence_enhance():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"error": "Text is required."}), 400
        max_chars = int(payload.get("max_context_chars", 800))
        enhanced = intelligence.enhance_prompt(text, max_chars=max_chars)
        return jsonify(
            {
                "enhanced_text": enhanced,
                "context": intelligence.get_context_for_prompt(max_chars=max_chars),
                "status": intelligence.status(),
            }
        )

    @app.get("/api/intelligence/recommendations")
    def intelligence_recommendations():
        return jsonify(intelligence.recommendations_payload())

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


def _enrich_prompt_text(text: str, context: str) -> str:
    if not context.strip():
        return text
    return (
        f"{text.strip()}\n\n"
        "[Live domain intelligence context for accuracy and recency]\n"
        f"{context.strip()}"
    )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


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
