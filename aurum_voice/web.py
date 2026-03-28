from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, jsonify, render_template, request

from .config import PipelineConfig
from .pipeline import VoiceSynthesisPipeline
from .providers import ElevenLabsProvider, TTSProviderError


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

        try:
            config = PipelineConfig.from_env()
            if quality == "expressive":
                config = replace(config, model_id="eleven_multilingual_v2")
            elif quality == "fast":
                config = replace(config, model_id="eleven_turbo_v2_5")

            provider = ElevenLabsProvider(
                config=config,
                voice_settings={
                    "stability": _clamp(stability),
                    "similarity_boost": _clamp(similarity_boost),
                    "style": _clamp(style),
                    "use_speaker_boost": speaker_boost,
                },
            )
            try:
                pipeline = VoiceSynthesisPipeline(
                    provider=provider,
                    config=config,
                    crossfade_ms=max(0, crossfade_ms),
                )
                wav_bytes = pipeline.synthesize_wav(text)
            finally:
                provider.close()
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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
