# aurum

Smooth AI voice software with ElevenLabs integration.

## Features

- ElevenLabs provider (`pcm_44100`) for high quality synthesis
- Chunked generation for long text inputs
- Crossfade smoothing between chunk boundaries to reduce choppy playback
- In-memory chunk caching for repeated synthesis
- Retry/backoff for transient network errors
- CLI interface for generating `.wav` files
- Premium web studio UI with modern controls and real-time playback

## Install

```bash
pip install -e ".[dev]"
```

## Environment

Set the required ElevenLabs API key:

```bash
export ELEVENLABS_API_KEY="your_api_key"
```

Optional:

- `ELEVENLABS_VOICE_ID` (default: `EXAVITQu4vr4xnSDxMaL`)
- `ELEVENLABS_MODEL_ID` (default: `eleven_multilingual_v2`)

## Usage

```bash
aurum-voice \
  --text "Hello from Aurum. This voice should sound smoother now." \
  --output ./out/voice.wav \
  --crossfade-ms 24
```

## Web Studio (Luxury UI)

Start the app:

```bash
aurum-voice-web
```

Then open:

```text
http://localhost:8080
```

Includes:

- modern glassmorphism UI with premium color system
- live controls for quality, smoothness, stability, similarity, and style
- in-browser playback and WAV download

## Run tests

```bash
pytest -q
```
