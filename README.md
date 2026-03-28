# aurum

Smooth AI voice software with ElevenLabs integration.

## Features

- ElevenLabs provider (`pcm_44100`) for high quality synthesis
- Chunked generation for long text inputs
- Crossfade smoothing between chunk boundaries to reduce choppy playback
- In-memory chunk caching for repeated synthesis
- Retry/backoff for transient network errors
- CLI interface for generating `.wav` files

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

## Run tests

```bash
pytest -q
```
