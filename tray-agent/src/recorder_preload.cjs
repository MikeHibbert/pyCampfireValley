// CommonJS preload for hidden recorder window
const { ipcRenderer } = require("electron");

try { ipcRenderer.send("tray-log", "Recorder preload (CJS) attached"); } catch {}

let audioCtx = null;
let processor = null;
let mediaStream = null;
let buffers = [];
let recorded = 0;
let maxSamples = 0;
let currentSampleRate = 16000;

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}
function floatTo16BitPCM(view, offset, input) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
}
function encodeWav(samples, sampleRate) {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample * 1;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * bytesPerSample, true);
  floatTo16BitPCM(view, 44, samples);
  return buffer;
}
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)));
  }
  return btoa(binary);
}

async function startCapture(opts) {
  try {
    buffers = [];
    recorded = 0;
    currentSampleRate = opts?.sampleRate || 16000;
    maxSamples = currentSampleRate * (opts?.maxDuration || 120);
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: currentSampleRate });
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioCtx.createMediaStreamSource(mediaStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioCtx.destination);
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      buffers.push(new Float32Array(input));
      recorded += input.length;
      if (recorded >= maxSamples) {
        stopCapture();
      }
    };
    try { ipcRenderer.send("tray-log", "Capture start ok"); } catch {}
  } catch (err) {
    console.error("Capture start error:", err);
    try { ipcRenderer.send("tray-log", `Capture start error: ${String(err)}`); } catch {}
  }
}

async function stopCapture() {
  try {
    if (processor) processor.disconnect();
    if (audioCtx) await audioCtx.close();
  } catch {}
  processor = null;
  audioCtx = null;
  try { ipcRenderer.send("tray-log", `Capture stop, samples=${recorded}`); } catch {}
  const out = new Float32Array(recorded);
  let offset = 0;
  for (const buf of buffers) { out.set(buf, offset); offset += buf.length; }
  buffers = [];
  const wav = encodeWav(out, currentSampleRate);
  const base64 = arrayBufferToBase64(wav);
  try {
    try { ipcRenderer.send("tray-log", "Invoking upload"); } catch {}
    await ipcRenderer.invoke("audio:final", { base64, encoding: "wav" });
  } catch (err) {
    console.error("Upload invoke error:", err);
    try { ipcRenderer.send("tray-log", `Upload invoke error: ${String(err)}`); } catch {}
  } finally {
    recorded = 0;
  }
}

ipcRenderer.on("recorder:start", (_ev, opts) => {
  try { ipcRenderer.send("tray-log", `IPC recorder:start (${opts?.sampleRate}/${opts?.maxDuration})`); } catch {}
  startCapture(opts || { sampleRate: 16000, maxDuration: 120 });
});
ipcRenderer.on("recorder:stop", () => {
  try { ipcRenderer.send("tray-log", "IPC recorder:stop"); } catch {}
  stopCapture();
});

function speakText(text, opts) {
  if (!text) return;
  try {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      if (opts && opts.voice) {
        const vs = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
        const vv = (vs || []).find(v => v.name === opts.voice) || (vs || []).find(v => v.name && v.name.toLowerCase().includes(String(opts.voice).toLowerCase()));
        if (vv) u.voice = vv;
      }
      window.speechSynthesis.speak(u);
    }
  } catch (e) {
    try { ipcRenderer.send("tray-log", `TTS speak error: ${String(e)}`);} catch {}
  }
}

ipcRenderer.on("tts:speak", (_ev, payload) => {
  speakText((payload && payload.text) || "", payload || {});
});

ipcRenderer.on("tts:playAudio", async (_ev, payload) => {
  try {
    const bin = atob(payload.base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio();
    try {
      if (payload.sinkId && audio.setSinkId) {
        await audio.setSinkId(payload.sinkId);
      }
    } catch {}
    audio.src = url;
    await audio.play().catch(()=>{});
    audio.onended = () => { try { URL.revokeObjectURL(url); } catch {} };
  } catch (e) {
    try { ipcRenderer.send("tray-log", `tts:playAudio error: ${String(e)}`);} catch {}
  }
});
