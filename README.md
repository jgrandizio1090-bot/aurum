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
- Animated waveform visualizer during playback previews
- Project preset save/load/delete (stored in browser local storage)
- Multi-voice A/B script mode with per-speaker voice ID overrides
- One-click mastering (normalization + fade in/out smoothing)
- Background intelligence fetch for wealth management + tax policy signals
- Live intelligence status + manual refresh in UI

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
- waveform animation for visual feedback
- preset system for saving creative direction configurations
- multi-speaker script support using `A:` / `B:` lines
- mastering controls for polished output in one pass
- background intelligence status from IRS/SEC/Treasury feeds
- optional use of intelligence context to improve guidance metadata while keeping audio rendering fast
- topic-tracked background refinement for family office creation, governance, family advisory, and philanthropy

### Live intelligence layer

Aurum runs a background intelligence refresher that pulls public regulatory/news signals from:

- IRS Newsroom RSS
- SEC Press Releases RSS
- U.S. Treasury News feed
- DOJ Press Releases feed
- Federal Reserve Press Releases feed

What this does:

- keeps a cached summary + keywords in memory
- updates in the background on an interval
- classifies topic coverage counts for:
  - family office creation
  - governance
  - family advisory
  - philanthropy
- exposes status and refresh endpoints:
  - `GET /api/intelligence/status`
  - `POST /api/intelligence/refresh`
  - `POST /api/intelligence/enhance`

In the UI, enable **Use background wealth/tax intelligence** to attach this context as smart guidance metadata during generation requests.

### Multi-voice script format

When **Script Mode** is set to `Multi Voice (A/B)`, use lines like:

```text
A: Welcome to Aurum Voice Studio.
B: Thanks. This sounds polished and premium.
A: Let's begin today's narration.
```

You can optionally set distinct `Voice ID (Speaker A)` and `Voice ID (Speaker B)` in the UI.

## Run tests

```bash
pytest -q
```
