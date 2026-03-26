const { ipcRenderer } = require("electron");
try { ipcRenderer.send("tray-log", "Settings preload attached"); } catch {}

function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: any = {}, children: Array<Node | string> = []) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (k === "style" && typeof v === "object") Object.assign((el as any).style, v);
    else if (k.startsWith("on") && typeof v === "function") (el as any)[k.toLowerCase()] = v;
    else el.setAttribute(k, String(v));
  });
  for (const c of children) el.append(c instanceof Node ? c : document.createTextNode(c));
  return el;
}

let currentStream: MediaStream | null = null;
let audioCtx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let rafId = 0;
let deviceSelect: HTMLSelectElement;
let levelBar: HTMLDivElement;
let saveBtn: HTMLButtonElement;
let testBtn: HTMLButtonElement;
let closeBtn: HTMLButtonElement;

async function listInputs(): Promise<MediaDeviceInfo[]> {
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
    audioCtx.close().catch(() => {});
    audioCtx = null;
  }
  if (currentStream) {
    currentStream.getTracks().forEach(t => t.stop());
    currentStream = null;
  }
}

async function startPreview(deviceId?: string) {
  stopPreview();
  try {
    currentStream = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: deviceId ? { exact: deviceId } : undefined }
    });
    audioCtx = new AudioContext({ sampleRate: 16000 });
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

async function populate(deviceId?: string) {
  const inputs = await listInputs();
  deviceSelect.innerHTML = "";
  for (const d of inputs) {
    const opt = h("option", { value: d.deviceId }, [d.label || d.deviceId || "input"]);
    deviceSelect.append(opt);
  }
  if (deviceId) deviceSelect.value = deviceId;
}

async function init() {
  document.body.style.margin = "0";
  document.body.style.fontFamily = "system-ui, Segoe UI, Arial";
  document.body.textContent = "";
  const title = h("div", { style: { padding: "12px 16px", fontWeight: "600" } }, ["Audio Settings"]);
  const container = h("div", { style: { padding: "0 16px 16px 16px" } });
  const row1 = h("div", { style: { marginBottom: "12px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Input device"]),
    deviceSelect = h("select", { style: { width: "100%", padding: "8px" } }) as HTMLSelectElement
  ]);
  const row2 = h("div", { style: { marginBottom: "8px" } }, [
    h("div", { style: { marginBottom: "6px" } }, ["Level"]),
    h("div", { style: { background: "#eee", width: "100%", height: "10px", borderRadius: "5px", overflow: "hidden" } }, [
      levelBar = h("div", { style: { background: "#4caf50", width: "0%", height: "100%" } }) as HTMLDivElement
    ])
  ]);
  const buttons = h("div", { style: { display: "flex", gap: "8px", marginTop: "12px" } }, [
    testBtn = h("button", {}, ["Test TTS"]) as HTMLButtonElement,
    saveBtn = h("button", {}, ["Save"]) as HTMLButtonElement,
    closeBtn = h("button", {}, ["Close"]) as HTMLButtonElement
  ]);
  container.append(row1, row2, buttons);
  document.body.append(title, container);

  const cfg = await ipcRenderer.invoke("settings:get").catch(() => null);
  await populate(cfg?.audio?.device_id);
  await startPreview(cfg?.audio?.device_id);

  deviceSelect.addEventListener("change", async () => {
    await startPreview(deviceSelect.value || undefined);
  });
  testBtn.addEventListener("click", () => {
    try { ipcRenderer.send("tray-log", "Settings: Test TTS clicked"); } catch {}
    ipcRenderer.send("tts:request", { text: "Microphone device set up window is working." });
  });
  saveBtn.addEventListener("click", async () => {
    const ok = await ipcRenderer.invoke("settings:update", { audio: { device_id: deviceSelect.value || "default" } }).catch(() => false);
    ipcRenderer.send("tray-log", ok ? "Settings saved" : "Settings save failed");
  });
  closeBtn.addEventListener("click", () => {
    window.close();
  });
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
