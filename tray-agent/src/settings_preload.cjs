// CommonJS preload for Settings window to avoid ESM preload restrictions
const { ipcRenderer } = require("electron");

function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el[k.toLowerCase()] = v;
    else el.setAttribute(k, String(v));
  });
  for (const c of children) el.append(c instanceof Node ? c : document.createTextNode(c));
  return el;
}

let currentStream = null;
let audioCtx = null;
let analyser = null;
let rafId = 0;
let deviceSelect;
let levelBar;
let saveBtn;
let testBtn;
let closeBtn;
let outputSelect;
let testOutBtn;
let voiceSelect;
let engineSelect;
let windowsBtn;

async function listInputs() {
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {}
  const all = await navigator.mediaDevices.enumerateDevices();
  return all.filter(d => d.kind === "audioinput");
}

function stopPreview() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
  if (analyser) analyser.disconnect();
  analyser = null;
  if (audioCtx) {
    try { audioCtx.close(); } catch {}
    audioCtx = null;
  }
  if (currentStream) {
    currentStream.getTracks().forEach(t => t.stop());
    currentStream = null;
  }
}

async function startPreview(deviceId) {
  stopPreview();
  try {
    currentStream = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: deviceId ? { exact: deviceId } : undefined }
    });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const src = audioCtx.createMediaStreamSource(currentStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const draw = () => {
      if (!analyser) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      const pct = Math.min(100, Math.max(0, Math.round(rms * 120)));
      levelBar.style.width = pct + "%";
      rafId = requestAnimationFrame(draw);
    };
    draw();
  } catch (e) {
    levelBar.style.width = "0%";
  }
}

async function populate(deviceId) {
  const inputs = await listInputs();
  const all = await navigator.mediaDevices.enumerateDevices();
  const outputs = all.filter(d => d.kind === "audiooutput");
  const voices = (window.speechSynthesis && window.speechSynthesis.getVoices && window.speechSynthesis.getVoices()) || [];
  deviceSelect.innerHTML = "";
  for (const d of inputs) {
    const label = d.label || d.deviceId || "input";
    const opt = h("option", { value: d.deviceId }, [label]);
    deviceSelect.append(opt);
  }
  if (deviceId) deviceSelect.value = deviceId;
  if (outputSelect) {
    outputSelect.innerHTML = "";
    for (const d of outputs) {
      const label = d.label || d.deviceId || "output";
      outputSelect.append(h("option", { value: d.deviceId }, [label]));
    }
  }
  if (voiceSelect) {
    await refreshVoices();
  }
}

async function refreshVoices() {
  if (!voiceSelect) return;
  try {
    const ws = (window.speechSynthesis && window.speechSynthesis.getVoices && window.speechSynthesis.getVoices()) || [];
    let sapi = [];
    try {
      sapi = (await ipcRenderer.invoke("settings:listSapiVoices")) || [];
    } catch {}
    const names = new Set();
    voiceSelect.innerHTML = "";
    for (const v of ws) {
      if (!v?.name) continue;
      if (names.has(v.name)) continue;
      names.add(v.name);
      voiceSelect.append(h("option", { value: v.name }, [v.name]));
    }
    for (const n of sapi) {
      if (!n) continue;
      if (names.has(n)) continue;
      names.add(n);
      voiceSelect.append(h("option", { value: n }, [n + " (SAPI)"]));
    }
    if (voiceSelect.options.length === 0) {
      voiceSelect.append(h("option", { value: "" }, ["(No voices found)"]));
    }
  } catch {}
}

async function init() {
  try { ipcRenderer.send("tray-log", "Settings preload (CJS) attached"); } catch {}
  document.body.style.margin = "0";
  document.body.style.fontFamily = "system-ui, Segoe UI, Arial";
  document.body.textContent = "";
  const title = h("div", { style: { padding: "12px 16px", fontWeight: "600" } }, ["Audio Settings"]);
  const container = h("div", { style: { padding: "0 16px 16px 16px" } });
  const row1 = h("div", { style: { marginBottom: "12px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Input device"]),
    deviceSelect = h("select", { style: { width: "100%", padding: "8px" } })
  ]);
  const rowOut = h("div", { style: { marginBottom: "12px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Output device"]),
    outputSelect = h("select", { style: { width: "100%", padding: "8px" } })
  ]);
  const rowVoice = h("div", { style: { marginBottom: "12px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Voice (best effort)"]),
    voiceSelect = h("select", { style: { width: "100%", padding: "8px" } })
  ]);
  const rowEngine = h("div", { style: { marginBottom: "12px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["TTS engine"]),
    engineSelect = h("select", { style: { width: "100%", padding: "8px" } }, [
      h("option", { value: "webspeech" }, ["Web Speech (default)"]),
      h("option", { value: "sapi" }, ["Windows SAPI (audio, sink-aware)"])
    ])
  ]);
  const row2 = h("div", { style: { marginBottom: "8px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Level"]),
    h("div", { style: { background: "#eee", width: "100%", height: "10px", borderRadius: "5px", overflow: "hidden" } }, [
      levelBar = h("div", { style: { background: "#4caf50", width: "0%", height: "100%" } })
    ])
  ]);
  const buttons = h("div", { style: { display: "flex", gap: "8px", marginTop: "12px" } }, [
    testBtn = h("button", {}, ["Test TTS"]),
    testOutBtn = h("button", {}, ["Test Output"]),
    windowsBtn = h("button", {}, ["Windows Speech Settings"]),
    saveBtn = h("button", {}, ["Save"]),
    closeBtn = h("button", {}, ["Close"])
  ]);
  container.append(row1, rowOut, rowVoice, rowEngine, row2, buttons);
  document.body.append(title, container);

  const cfg = await ipcRenderer.invoke("settings:get").catch(() => null);
  await populate(cfg && cfg.audio ? cfg.audio.device_id : undefined);
  if (outputSelect && cfg && cfg.tts && cfg.tts.output_device_id) {
    outputSelect.value = cfg.tts.output_device_id;
  }
  if (voiceSelect && cfg && cfg.tts && cfg.tts.voice) {
    voiceSelect.value = cfg.tts.voice;
  }
  if (engineSelect && cfg && cfg.tts && cfg.tts.engine) {
    engineSelect.value = cfg.tts.engine;
  }
  await startPreview(cfg && cfg.audio ? cfg.audio.device_id : undefined);
  try {
    if (window.speechSynthesis && window.speechSynthesis.addEventListener) {
      window.speechSynthesis.addEventListener("voiceschanged", () => { refreshVoices(); });
    }
    // Trigger initial load
    window.speechSynthesis && window.speechSynthesis.getVoices && window.speechSynthesis.getVoices();
    setTimeout(refreshVoices, 500);
  } catch {}

  deviceSelect.addEventListener("change", async () => {
    await startPreview(deviceSelect.value || undefined);
  });
  voiceSelect && voiceSelect.addEventListener("change", () => {
    try {
      const name = voiceSelect.value || "";
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(name ? `Voice ${name}` : "Voice changed");
        const vs = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
        const vv = (vs || []).find(v => v.name === name) || (vs || []).find(v => v.name && name && v.name.toLowerCase().includes(name.toLowerCase()));
        if (vv) u.voice = vv;
        window.speechSynthesis.speak(u);
      } else {
        ipcRenderer.send("tts:request", { text: name ? `Voice ${name}` : "Voice changed", sinkId: outputSelect ? outputSelect.value : undefined });
      }
    } catch {}
  });
  testBtn.addEventListener("click", () => {
    try { ipcRenderer.send("tray-log", "Settings: Test TTS clicked"); } catch {}
    // Speak locally in this window for immediate feedback
    try {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance("Microphone device setup window is working.");
        window.speechSynthesis.speak(u);
      }
    } catch {}
    // Also send to hidden window pipeline with sinkId so we can verify the full path
    ipcRenderer.send("tts:request", { text: "Microphone device set up window is working.", sinkId: outputSelect ? outputSelect.value : undefined });
  });
  testOutBtn.addEventListener("click", async () => {
    try { ipcRenderer.send("tray-log", "Settings: Test Output clicked"); } catch {}
    try {
      const audio = new Audio();
      if (audio.setSinkId && outputSelect && outputSelect.value) {
        await audio.setSinkId(outputSelect.value);
      }
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0.05;
      osc.frequency.value = 660;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest);
      const stream = dest.stream;
      audio.srcObject = stream;
      osc.start();
      await audio.play().catch(()=>{});
      setTimeout(() => {
        try { osc.stop(); ctx.close(); audio.pause(); } catch {}
      }, 300);
    } catch (e) {
      try { ipcRenderer.send("tray-log", `Output test error: ${String(e)}`);} catch {}
    }
  });
  saveBtn.addEventListener("click", async () => {
    const ok = await ipcRenderer.invoke("settings:update", { audio: { device_id: deviceSelect.value || "default" }, tts: { output_device_id: outputSelect ? (outputSelect.value || undefined) : undefined, voice: voiceSelect ? (voiceSelect.value || undefined) : undefined, engine: engineSelect ? (engineSelect.value || undefined) : undefined } }).catch(() => false);
    ipcRenderer.send("tray-log", ok ? "Settings saved" : "Settings save failed");
  });
  windowsBtn.addEventListener("click", async () => {
    await ipcRenderer.invoke("settings:openWindowsVoiceSettings").catch(()=>{});
  });
  closeBtn.addEventListener("click", () => window.close());
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
