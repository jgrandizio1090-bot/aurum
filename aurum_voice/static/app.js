const textEl = document.getElementById("text");
const charCountEl = document.getElementById("charCount");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const player = document.getElementById("player");
const downloadBtn = document.getElementById("downloadBtn");
const statusText = document.getElementById("statusText");
const waveform = document.getElementById("waveform");
const waveformCtx = waveform.getContext("2d");

const crossfade = document.getElementById("crossfade");
const crossfadeValue = document.getElementById("crossfadeValue");
const stability = document.getElementById("stability");
const stabilityValue = document.getElementById("stabilityValue");
const similarity = document.getElementById("similarity");
const similarityValue = document.getElementById("similarityValue");
const style = document.getElementById("style");
const styleValue = document.getElementById("styleValue");
const quality = document.getElementById("quality");
const speakerBoost = document.getElementById("speakerBoost");
const voiceA = document.getElementById("voiceA");
const voiceB = document.getElementById("voiceB");
const scriptMode = document.getElementById("scriptMode");
const insertTemplateBtn = document.getElementById("insertTemplateBtn");

const masteringEnabled = document.getElementById("masteringEnabled");
const normalizeEnabled = document.getElementById("normalizeEnabled");
const fadeMs = document.getElementById("fadeMs");
const fadeMsValue = document.getElementById("fadeMsValue");
const peakTarget = document.getElementById("peakTarget");
const peakTargetValue = document.getElementById("peakTargetValue");

const presetName = document.getElementById("presetName");
const presetSelect = document.getElementById("presetSelect");
const savePresetBtn = document.getElementById("savePresetBtn");
const loadPresetBtn = document.getElementById("loadPresetBtn");
const deletePresetBtn = document.getElementById("deletePresetBtn");
const useIntelligence = document.getElementById("useIntelligence");
const refreshIntelBtn = document.getElementById("refreshIntelBtn");
const intelStatus = document.getElementById("intelStatus");

let currentAudioUrl = null;
let waveformAnimation = null;
const PRESET_STORAGE_KEY = "aurumVoicePresets";
let intelPollHandle = null;

function setStatus(message, kind = "") {
  statusText.textContent = message;
  statusText.classList.remove("error", "success");
  if (kind) {
    statusText.classList.add(kind);
  }
}

function updateCount() {
  const count = textEl.value.trim().length;
  charCountEl.textContent = `${count} character${count === 1 ? "" : "s"}`;
}

function bindSlider(input, output, suffix = "") {
  const update = () => {
    output.textContent = `${input.value}${suffix}`;
  };
  input.addEventListener("input", update);
  update();
}

function getSettings() {
  return {
    script_mode: scriptMode.value,
    quality: quality.value,
    crossfade_ms: Number(crossfade.value),
    stability: Number(stability.value),
    similarity_boost: Number(similarity.value),
    style: Number(style.value),
    speaker_boost: Boolean(speakerBoost.checked),
    voices: {
      A: voiceA.value.trim(),
      B: voiceB.value.trim(),
    },
    use_intelligence: Boolean(useIntelligence.checked),
    apply_intelligence_context: false,
    mastering: {
      enabled: Boolean(masteringEnabled.checked),
      normalize: Boolean(normalizeEnabled.checked),
      fade_ms: Number(fadeMs.value),
      peak_target: Number(peakTarget.value),
    },
  };
}

function applySettings(settings) {
  scriptMode.value = settings.script_mode || "single";
  quality.value = settings.quality || "balanced";
  crossfade.value = String(settings.crossfade_ms ?? 24);
  stability.value = String(settings.stability ?? 0.5);
  similarity.value = String(settings.similarity_boost ?? 0.75);
  style.value = String(settings.style ?? 0.0);
  speakerBoost.checked = Boolean(settings.speaker_boost ?? true);
  voiceA.value = settings.voices?.A || "";
  voiceB.value = settings.voices?.B || "";
  useIntelligence.checked = Boolean(settings.use_intelligence ?? true);

  masteringEnabled.checked = Boolean(settings.mastering?.enabled ?? true);
  normalizeEnabled.checked = Boolean(settings.mastering?.normalize ?? true);
  fadeMs.value = String(settings.mastering?.fade_ms ?? 12);
  peakTarget.value = String(settings.mastering?.peak_target ?? 0.92);

  [crossfade, stability, similarity, style, fadeMs, peakTarget].forEach((el) => {
    el.dispatchEvent(new Event("input"));
  });
}

function parsePresets() {
  try {
    const raw = localStorage.getItem(PRESET_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function writePresets(presets) {
  localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets));
}

function refreshPresetSelect() {
  const presets = parsePresets();
  presetSelect.innerHTML = "";
  const names = Object.keys(presets).sort((a, b) => a.localeCompare(b));
  if (names.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No presets yet";
    presetSelect.appendChild(option);
    presetSelect.disabled = true;
    return;
  }

  presetSelect.disabled = false;
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    presetSelect.appendChild(option);
  }
}

function savePreset() {
  const name = presetName.value.trim();
  if (!name) {
    setStatus("Enter a preset name first.", "error");
    return;
  }
  const presets = parsePresets();
  presets[name] = getSettings();
  writePresets(presets);
  refreshPresetSelect();
  presetSelect.value = name;
  setStatus(`Preset "${name}" saved.`, "success");
}

function loadPreset() {
  const name = presetSelect.value;
  if (!name) {
    return;
  }
  const presets = parsePresets();
  const selected = presets[name];
  if (!selected) {
    setStatus("Preset not found.", "error");
    return;
  }
  applySettings(selected);
  setStatus(`Preset "${name}" loaded.`, "success");
}

function deletePreset() {
  const name = presetSelect.value;
  if (!name) {
    return;
  }
  const presets = parsePresets();
  delete presets[name];
  writePresets(presets);
  refreshPresetSelect();
  setStatus(`Preset "${name}" deleted.`, "success");
}

function renderIntelStatus(payload) {
  if (!payload) {
    intelStatus.textContent = "Intelligence unavailable";
    return;
  }
  const healthy = Boolean(payload.healthy);
  const items = Number(payload.item_count || 0);
  const revision = Number(payload.revision || 0);
  const at = payload.generated_at ? ` @ ${payload.generated_at}` : "";
  const mode = useIntelligence.checked ? "on" : "off";
  intelStatus.textContent = healthy
    ? `Live (${items} items, rev ${revision}, ${mode})${at}`
    : `Warming up (${items} items, ${mode})${at}`;
}

async function pollIntelStatus() {
  try {
    const response = await fetch("/api/intelligence/status");
    if (!response.ok) {
      throw new Error("status failed");
    }
    const data = await response.json();
    renderIntelStatus(data);
  } catch {
    intelStatus.textContent = "Intelligence status unavailable";
  }
}

async function refreshIntelligence(force = true) {
  try {
    refreshIntelBtn.disabled = true;
    intelStatus.textContent = "Refreshing intelligence...";
    const response = await fetch("/api/intelligence/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    if (!response.ok) {
      throw new Error("refresh failed");
    }
    await pollIntelStatus();
  } catch {
    intelStatus.textContent = "Refresh failed";
  } finally {
    refreshIntelBtn.disabled = false;
  }
}

function drawIdleWaveform() {
  const w = waveform.width;
  const h = waveform.height;
  waveformCtx.clearRect(0, 0, w, h);
  const gradient = waveformCtx.createLinearGradient(0, 0, w, h);
  gradient.addColorStop(0, "rgba(242, 209, 136, 0.08)");
  gradient.addColorStop(1, "rgba(110, 160, 255, 0.12)");
  waveformCtx.fillStyle = gradient;
  waveformCtx.fillRect(0, 0, w, h);

  waveformCtx.strokeStyle = "rgba(242, 209, 136, 0.45)";
  waveformCtx.lineWidth = 2;
  waveformCtx.beginPath();
  for (let x = 0; x < w; x += 1) {
    const y = h / 2 + Math.sin(x / 30) * 4;
    if (x === 0) {
      waveformCtx.moveTo(x, y);
    } else {
      waveformCtx.lineTo(x, y);
    }
  }
  waveformCtx.stroke();
}

function animateWaveformFromData(samples) {
  if (!samples.length) {
    drawIdleWaveform();
    return;
  }
  if (waveformAnimation) {
    cancelAnimationFrame(waveformAnimation);
  }
  let frame = 0;
  const w = waveform.width;
  const h = waveform.height;
  const bars = 180;
  const step = Math.max(1, Math.floor(samples.length / bars));

  const render = () => {
    frame += 1;
    waveformCtx.clearRect(0, 0, w, h);
    waveformCtx.fillStyle = "rgba(8, 13, 31, 0.85)";
    waveformCtx.fillRect(0, 0, w, h);

    const barWidth = w / bars;
    for (let i = 0; i < bars; i += 1) {
      const idx = (i * step + frame * 9) % samples.length;
      const amplitude = Math.abs(samples[idx]) / 32768;
      const eased = Math.pow(amplitude, 0.75);
      const barHeight = Math.max(4, eased * (h - 20));
      const x = i * barWidth;
      const y = (h - barHeight) / 2;
      const alpha = 0.3 + eased * 0.65;
      waveformCtx.fillStyle = `rgba(242, 209, 136, ${alpha})`;
      waveformCtx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight);
    }
    waveformAnimation = requestAnimationFrame(render);
  };
  waveformAnimation = requestAnimationFrame(render);
}

function extractPcmSamplesFromWav(arrayBuffer) {
  if (arrayBuffer.byteLength < 44) {
    return new Int16Array();
  }
  const headerOffset = 44;
  return new Int16Array(arrayBuffer.slice(headerOffset));
}

async function generateVoice() {
  const text = textEl.value.trim();
  if (!text) {
    setStatus("Please enter text before generating audio.", "error");
    return;
  }

  generateBtn.disabled = true;
  setStatus("Rendering premium voice...", "");

  try {
    const response = await fetch("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        ...getSettings(),
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to synthesize audio.");
    }

    const audioBytes = atob(data.audio_b64);
    const len = audioBytes.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
      bytes[i] = audioBytes.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: "audio/wav" });
    const arrayBuffer = await blob.arrayBuffer();
    const samples = extractPcmSamplesFromWav(arrayBuffer);
    animateWaveformFromData(samples);

    if (currentAudioUrl) {
      URL.revokeObjectURL(currentAudioUrl);
    }
    currentAudioUrl = URL.createObjectURL(blob);
    player.src = currentAudioUrl;
    downloadBtn.href = currentAudioUrl;
    downloadBtn.classList.remove("disabled");
    setStatus("Voice ready. Enjoy.", "success");
  } catch (error) {
    setStatus(error.message || "Unexpected error while generating audio.", "error");
  } finally {
    generateBtn.disabled = false;
  }
}

function clearAll() {
  textEl.value = "";
  updateCount();
  setStatus("Ready");
  player.removeAttribute("src");
  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
  }
  if (waveformAnimation) {
    cancelAnimationFrame(waveformAnimation);
    waveformAnimation = null;
  }
  drawIdleWaveform();
  downloadBtn.removeAttribute("href");
  downloadBtn.classList.add("disabled");
}

function insertTemplate() {
  const template = "A: Welcome to Aurum Voice Studio.\nB: Thanks. This sounds polished and premium.\nA: Let's generate a luxury-grade narration.";
  textEl.value = template;
  scriptMode.value = "multi";
  updateCount();
}

textEl.addEventListener("input", updateCount);
generateBtn.addEventListener("click", generateVoice);
clearBtn.addEventListener("click", clearAll);
insertTemplateBtn.addEventListener("click", insertTemplate);
savePresetBtn.addEventListener("click", savePreset);
loadPresetBtn.addEventListener("click", loadPreset);
deletePresetBtn.addEventListener("click", deletePreset);
refreshIntelBtn.addEventListener("click", () => refreshIntelligence(true));

bindSlider(crossfade, crossfadeValue, " ms");
bindSlider(stability, stabilityValue);
bindSlider(similarity, similarityValue);
bindSlider(style, styleValue);
bindSlider(fadeMs, fadeMsValue, " ms");
bindSlider(peakTarget, peakTargetValue);
updateCount();
refreshPresetSelect();
drawIdleWaveform();
pollIntelStatus();
if (intelPollHandle) {
  clearInterval(intelPollHandle);
}
intelPollHandle = setInterval(pollIntelStatus, 30000);
