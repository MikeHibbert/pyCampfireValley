import { ipcRenderer } from "electron";
console.log("[TrayAgent] Preload initialized");
try { ipcRenderer.send("tray-log", "Recorder preload attached"); } catch {}

let audioCtx: AudioContext | null = null;
let processor: ScriptProcessorNode | null = null;
let mediaStream: MediaStream | null = null;
let buffers: Float32Array[] = [];
let recorded = 0;
let maxSamples = 0;
let currentSampleRate = 16000;

function pickVoice(name?: string) {
  const voices = window.speechSynthesis.getVoices();
  if (!voices || voices.length === 0) return undefined;
  if (!name) return voices[0];
  const exact = voices.find(v => v.name === name);
  if (exact) return exact;
  const part = voices.find(v => v.name.toLowerCase().includes(name.toLowerCase()));
  return part || voices[0];
}

function speakText(text: string, opts?: { voice?: string; rate?: number; pitch?: number; volume?: number }) {
  try {
    if (!text || !("speechSynthesis" in window)) return;
    const doSpeak = () => {
      try {
        console.log("[TrayAgent] TTS speaking:", text.slice(0, 60));
        ipcRenderer.send("tray-log", `TTS speaking: ${text.slice(0, 40)}${text.length>40?"…":""}`);
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        const v = pickVoice(opts?.voice);
        if (v) u.voice = v;
        if (opts?.rate) u.rate = opts.rate;
        if (opts?.pitch) u.pitch = opts.pitch;
        if (opts?.volume !== undefined) u.volume = opts.volume;
        window.speechSynthesis.speak(u);
      } catch (e) {
        console.error("TTS speak error:", e);
        try {
          ipcRenderer.send("tray-log", `TTS speak error: ${String(e)}`);
        } catch {}
      }
    };
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) {
      const once = () => {
        window.speechSynthesis.removeEventListener?.("voiceschanged", once);
        doSpeak();
      };
      window.speechSynthesis.addEventListener?.("voiceschanged", once);
      window.speechSynthesis.getVoices();
      setTimeout(doSpeak, 500);
      return;
    }
    doSpeak();
  } catch (e) {
    console.error("TTS error:", e);
    try {
      ipcRenderer.send("tray-log", `TTS error: ${String(e)}`);
    } catch {}
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.value = 0.05;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      setTimeout(() => { osc.stop(); ctx.close(); }, 200);
    } catch {}
  }
}

window.speechSynthesis.addEventListener?.("voiceschanged", () => {});

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

function floatTo16BitPCM(view: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
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

function arrayBufferToBase64(buffer: ArrayBuffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)) as any);
  }
  return btoa(binary);
}

async function startCapture(opts: { sampleRate: number; maxDuration: number }) {
  try {
    console.log("[TrayAgent] Capture start", opts);
    ipcRenderer.send("tray-log", "Capture start");
    buffers = [];
    recorded = 0;
    currentSampleRate = opts.sampleRate || 16000;
    maxSamples = currentSampleRate * (opts.maxDuration || 120);
    audioCtx = new AudioContext({ sampleRate: currentSampleRate });
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioCtx.createMediaStreamSource(mediaStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioCtx.destination);
    processor.onaudioprocess = (e: AudioProcessingEvent) => {
      const input = e.inputBuffer.getChannelData(0);
      buffers.push(new Float32Array(input));
      recorded += input.length;
      if (recorded % (currentSampleRate * 0.5) < 4096) {
        console.log("[TrayAgent] Capture progress samples=", recorded);
        ipcRenderer.send("tray-log", `Capture progress: ${recorded} samples`);
      }
      if (recorded >= maxSamples) {
        stopCapture();
      }
    };
  } catch (err) {
    console.error("Capture start error:", err);
    ipcRenderer.send("tray-log", `Capture start error: ${String(err)}`);
  }
}

async function stopCapture() {
  try {
    if (processor) processor.disconnect();
    if (audioCtx) await audioCtx.close();
  } catch {}
  processor = null;
  audioCtx = null;
  console.log("[TrayAgent] Capture stop, samples=", recorded);
  ipcRenderer.send("tray-log", `Capture stop, samples=${recorded}`);
  const length = recorded;
  const out = new Float32Array(length);
  let offset = 0;
  for (const buf of buffers) {
    out.set(buf, offset);
    offset += buf.length;
  }
  buffers = [];
  recorded = 0;
  const wav = encodeWav(out, currentSampleRate);
  const base64 = arrayBufferToBase64(wav);
  try {
    console.log("[TrayAgent] Invoking upload");
    ipcRenderer.send("tray-log", "Invoking upload");
    await ipcRenderer.invoke("audio:final", { base64, encoding: "wav" });
  } catch (err) {
    console.error("Upload invoke error:", err);
    ipcRenderer.send("tray-log", `Upload invoke error: ${String(err)}`);
  }
}

ipcRenderer.on("recorder:start", (_ev, opts: { sampleRate: number; maxDuration: number }) => {
  console.log("[TrayAgent] IPC recorder:start", opts);
  try { ipcRenderer.send("tray-log", `IPC recorder:start (${opts?.sampleRate}/${opts?.maxDuration})`); } catch {}
  startCapture(opts);
});
ipcRenderer.on("recorder:stop", () => {
  console.log("[TrayAgent] IPC recorder:stop");
  try { ipcRenderer.send("tray-log", "IPC recorder:stop"); } catch {}
  stopCapture();
});

ipcRenderer.on("tts:speak", (_ev, payload: { text: string; voice?: string; rate?: number; pitch?: number; volume?: number; sinkId?: string }) => {
  try {
    ipcRenderer.send("tray-log", "tts:speak received");
  } catch {}
  if (payload?.sinkId && (HTMLMediaElement.prototype as any).setSinkId) {
    try {
      const audio = new Audio();
      (audio as any).setSinkId(payload.sinkId).catch(()=>{});
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0.02;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain).connect(dest);
      audio.srcObject = dest.stream as any;
      osc.start();
      audio.play().catch(()=>{});
      setTimeout(() => { try { osc.stop(); ctx.close(); audio.pause(); } catch {} }, 120);
    } catch {}
  }
  speakText(payload?.text || "", payload);
});

ipcRenderer.on("tts:playAudio", async (_ev, payload: { base64: string; sinkId?: string }) => {
  try {
    const bin = atob(payload.base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio();
    try {
      if (payload.sinkId && (audio as any).setSinkId) {
        await (audio as any).setSinkId(payload.sinkId);
      }
    } catch {}
    audio.src = url;
    await audio.play().catch(()=>{});
    audio.onended = () => {
      try { URL.revokeObjectURL(url); } catch {}
    };
  } catch (e) {
    console.error("tts:playAudio error", e);
    try { ipcRenderer.send("tray-log", `tts:playAudio error: ${String(e)}`);} catch {}
  }
});
