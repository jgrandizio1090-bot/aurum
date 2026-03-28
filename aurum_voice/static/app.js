const textEl = document.getElementById("text");
const charCountEl = document.getElementById("charCount");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const player = document.getElementById("player");
const downloadBtn = document.getElementById("downloadBtn");
const statusText = document.getElementById("statusText");

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

let currentAudioUrl = null;

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
        quality: quality.value,
        crossfade_ms: Number(crossfade.value),
        stability: Number(stability.value),
        similarity_boost: Number(similarity.value),
        style: Number(style.value),
        speaker_boost: Boolean(speakerBoost.checked),
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
  downloadBtn.removeAttribute("href");
  downloadBtn.classList.add("disabled");
}

textEl.addEventListener("input", updateCount);
generateBtn.addEventListener("click", generateVoice);
clearBtn.addEventListener("click", clearAll);

bindSlider(crossfade, crossfadeValue, " ms");
bindSlider(stability, stabilityValue);
bindSlider(similarity, similarityValue);
bindSlider(style, styleValue);
updateCount();
