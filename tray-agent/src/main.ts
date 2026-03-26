import { app, BrowserWindow, Tray, Menu, ipcMain, globalShortcut, nativeImage, session, shell } from "electron";
import path from "node:path";
import { defaultConfig, TrayConfig } from "./config.js";
import { spawn } from "node:child_process";
import os from "node:os";
import fs from "node:fs";

let tray: Tray | null = null;
let win: BrowserWindow | null = null;
let settingsWin: BrowserWindow | null = null;
let overlayWin: BrowserWindow | null = null;
let isListening = false;
let config: TrayConfig = defaultConfig;
let overlayTickTimer: NodeJS.Timeout | null = null;
let autoStopTimer: NodeJS.Timeout | null = null;
let hookLoaded = false;
let devtools = false;
let historyStore: { time: number; transcript: string; reply: string }[] = [];

try {
  app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
} catch {}

function showInfo(message: string) {
  console.log(`[TrayAgent] ${message}`);
}

function createWindow() {
  win = new BrowserWindow({
    width: 400,
    height: 300,
    show: false,
    webPreferences: {
      preload: path.join(app.getAppPath(), "src", "recorder_preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      backgroundThrottling: false
    }
  });
  // Load from file for secure context (mediaDevices support)
  try {
    const html = path.join(app.getAppPath(), "src", "recorder.html");
    win.loadFile(html);
  } catch {
    win.loadURL("about:blank");
  }
  try {
    win.webContents.setAudioMuted?.(false);
  } catch {}
  applyDevTools();
}

function sendToRenderer(channel: string, payload?: any) {
  if (!win || win.isDestroyed()) {
    createWindow();
  }
  const doSend = () => {
    try {
      if (payload !== undefined) {
        win?.webContents.send(channel, payload);
      } else {
        win?.webContents.send(channel);
      }
    } catch {}
  };
  if (win?.webContents.isLoading()) {
    win?.webContents.once("did-finish-load", doSend);
  } else {
    doSend();
  }
}

function createOverlay() {
  if (overlayWin && !overlayWin.isDestroyed()) return;
  overlayWin = new BrowserWindow({
    width: 100,
    height: 36,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    movable: true,
    focusable: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false }
  });
  const html = `
    <html><body style="margin:0;background:transparent;">
    <div id="b" style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(0,0,0,0.6);color:#fff;border-radius:12px;font:12px system-ui;">
      <div style="width:10px;height:10px;border-radius:50%;background:#e53935;box-shadow:0 0 6px #e53935;"></div>
      <span id="t">REC</span>
    </div>
    <script>
      const { ipcRenderer } = require('electron');
      ipcRenderer.on('overlay:update', (_e, s) => { document.getElementById('t').textContent = 'REC ' + s; });
    </script>
    </body></html>`;
  overlayWin.loadURL(`data:text/html,${encodeURIComponent(html)}`);
}

function showOverlay() {
  createOverlay();
  overlayWin?.showInactive();
}
function hideOverlay() {
  overlayWin?.hide();
}
function updateOverlay(seconds: number) {
  overlayWin?.webContents.send("overlay:update", seconds.toFixed(0).padStart(2, "0") + "s");
}

function applyDevTools() {
  try {
    if (devtools) {
      win?.webContents.openDevTools({ mode: "detach" });
      settingsWin?.webContents.openDevTools({ mode: "detach" });
    } else {
      win?.webContents.closeDevTools();
      settingsWin?.webContents.closeDevTools();
    }
  } catch {}
}

function buildMenu() {
  const menu = Menu.buildFromTemplate([
    {
      label: "Settings…",
      click: () => {
        if (settingsWin && !settingsWin.isDestroyed()) {
          settingsWin.focus();
          return;
        }
        settingsWin = new BrowserWindow({
          width: 460,
          height: 560,
          show: true,
          webPreferences: {
            preload: path.join(app.getAppPath(), "src", "settings_preload.cjs"),
            nodeIntegration: false,
            contextIsolation: false,
            sandbox: false,
            backgroundThrottling: false,
            webSecurity: true
          }
        });
        settingsWin.on("closed", () => (settingsWin = null));
        try {
          const html = path.join(app.getAppPath(), "src", "settings.html");
          settingsWin.loadFile(html);
        } catch {
          settingsWin.loadURL("about:blank");
        }
        applyDevTools();
      }
    },
    {
      label: "Target Campfire",
      submenu: config.routing.allowlist.map(c => ({
        label: c,
        type: "radio",
        checked: c === config.routing.default_campfire,
        click: () => (config.routing.default_campfire = c)
      }))
    },
    {
      label: "History…",
      click: () => openHistoryWindow()
    },
    { type: "separator" },
    { label: "Quit", role: "quit" }
  ]);
  tray?.setContextMenu(menu);
}

function toggleListening() {
  isListening = !isListening;
  if (isListening) {
    showInfo("Listening started (PTT ready)");
    if (overlayTickTimer) {
      clearTimeout(overlayTickTimer);
      overlayTickTimer = null;
    }
    if (autoStopTimer) {
      clearTimeout(autoStopTimer);
      autoStopTimer = null;
    }
    showOverlay();
    let elapsed = 0;
    const tick = () => {
      if (!isListening) return;
      elapsed += 1;
      updateOverlay(elapsed);
      overlayTickTimer = setTimeout(tick, 1000);
    };
    sendToRenderer("recorder:start", {
      sampleRate: config.audio.sample_rate,
      maxDuration: config.audio.max_duration_seconds
    });
    const autoStop = Math.min(config.audio.max_duration_seconds || 120, 15);
    autoStopTimer = setTimeout(() => {
      if (isListening) {
        toggleListening();
      }
    }, autoStop * 1000);
    setTimeout(tick, 1000);
  } else {
    showInfo("Listening stopped");
    if (overlayTickTimer) {
      clearTimeout(overlayTickTimer);
      overlayTickTimer = null;
    }
    if (autoStopTimer) {
      clearTimeout(autoStopTimer);
      autoStopTimer = null;
    }
    sendToRenderer("recorder:stop");
    hideOverlay();
  }
  buildMenu();
}

function createTray() {
  // Fallback: empty icon. Projects should add platform icons under assets/.
  const image = nativeImage.createEmpty();
  tray = new Tray(image);
  tray.setToolTip("Campfire Valley Tray Agent");
  tray.on("click", () => toggleListening());
  buildMenu();
}

function encodeWavBase64(samples: Float32Array, sampleRate: number): string {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample * 1;
  const buffer = Buffer.alloc(44 + samples.length * bytesPerSample);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + samples.length * bytesPerSample, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * blockAlign, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(bytesPerSample * 8, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples.length * bytesPerSample, 40);
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    const val = s < 0 ? s * 0x8000 : s * 0x7fff;
    buffer.writeInt16LE(val, offset);
    offset += 2;
  }
  return buffer.toString("base64");
}

async function uploadAudio(base64Data: string, encoding: string) {
  try {
    showInfo(`Uploading ${encoding} audio to ${config.server.base_url}${config.server.api_path} (campfire: ${config.routing.default_campfire})`);
    let recognized = "";
    try {
      if (process.platform === "win32" && config.stt?.enabled && config.stt.engine === "sapi") {
        recognized = await transcribeViaSapiFromBase64(base64Data);
        if (recognized) showInfo(`Transcribed: ${recognized.slice(0, 80)}`);
      }
    } catch (e) {
      showInfo(`STT failed: ${String(e)}`);
    }
    const body: any = {
      campfire: config.routing.default_campfire,
      text: recognized || ""
    };
    if (encoding === "wav" || encoding === "opus" || encoding === "flac") {
      body.audio_base64 = base64Data;
      body.encoding = encoding;
    } else {
      body.audio_base64 = base64Data;
      body.encoding = "wav";
    }
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.server.admin_token) {
      headers["Authorization"] = `Bearer ${config.server.admin_token}`;
    }
    const url = `${config.server.base_url}${config.server.api_path}`;
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${text}`);
    }
    const data = await res.json().catch(() => ({}));
    const respPreview = typeof data?.response === "string"
      ? data.response.slice(0, 140)
      : JSON.stringify(data?.response ?? data).slice(0, 140);
    showInfo(`Upload succeeded. Reply: ${respPreview || "(no content)"}`);
    try {
      const txt = typeof data?.response === "string"
        ? data.response
        : (data?.response?.llm_response || data?.response?.text || "");
      historyStore.push({
        time: Date.now(),
        transcript: recognized || "",
        reply: txt || respPreview || ""
      });
      if (txt && config.tts?.enabled) {
        speakTextViaEngine(txt, {
          voice: config.tts.voice,
          sinkId: config.tts?.output_device_id
        });
      }
    } catch {}
    // No balloon on success; keep console log only
    return data;
  } catch (e) {
    console.error("Upload error:", e);
    return null;
  }
}

function transcribeViaSapiFromBase64(base64Data: string): Promise<string> {
  return new Promise((resolve, reject) => {
    try {
      const tmp = path.join(os.tmpdir(), `tray-stt-${Date.now()}.wav`);
      const buf = Buffer.from(base64Data, "base64");
      fs.writeFileSync(tmp, buf);
      const script = [
        'Add-Type -AssemblyName System.Speech;',
        '$c = [System.Globalization.CultureInfo]::CurrentCulture;',
        '$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($c);',
        '$r.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new());',
        `$r.SetInputToWaveFile('${tmp.replace(/\\/g, "\\\\")}');`,
        '$res = $r.Recognize();',
        '$r.Dispose();',
        'if ($res) { $res.Text }'
      ].join('\n');
      const ps = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { windowsHide: true });
      let out = "";
      let err = "";
      ps.stdout.on("data", d => (out += d.toString()));
      ps.stderr.on("data", d => (err += d.toString()));
      ps.on("exit", code => {
        try { fs.unlink(tmp, () => {}); } catch {}
        if (code !== 0) {
          reject(new Error(err || `PowerShell exited ${code}`));
          return;
        }
        resolve((out || "").trim());
      });
    } catch (e) {
      reject(e);
    }
  });
}

function openHistoryWindow() {
  const winH = new BrowserWindow({
    width: 520,
    height: 560,
    show: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false }
  });
  const rows = historyStore.slice(-50).reverse().map(item => {
    const t = new Date(item.time).toLocaleTimeString();
    const tr = (item.transcript || "").replace(/</g, "&lt;");
    const rp = (item.reply || "").replace(/</g, "&lt;");
    return `<div style="padding:8px 0;border-bottom:1px solid #eee">
      <div style="color:#666;font-size:11px">${t}</div>
      <div><strong>You:</strong> ${tr || "(audio)"}</div>
      <div><strong>Reply:</strong> ${rp}</div>
    </div>`;
  }).join("");
  const html = `
  <html><head><meta charset="utf-8"><title>History</title>
  <style>body{font:13px system-ui;margin:12px;} h1{font-size:16px;margin:0 0 8px;} .wrap{max-height:100%;overflow:auto}</style>
  </head><body>
  <h1>Recent Transcripts</h1>
  <div class="wrap">${rows || "<em>No history yet</em>"}</div>
  </body></html>`;
  winH.loadURL(`data:text/html,${encodeURIComponent(html)}`);
}
app.whenReady().then(() => {
  createWindow();
  // Auto-allow media permission for hidden capture window
  try {
    session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
      if (permission === "media") {
        callback(true);
      } else {
        callback(false);
      }
    });
    showInfo("Media permission handler installed (auto-allow)");
  } catch {}
  createTray();
  try {
    if (!hookLoaded) {
      // optional dependency for true hold-to-talk; falls back silently if not installed
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const iohook = (require as any)("iohook");
      hookLoaded = true;
      let down = false;
      iohook.on("keydown", (e: any) => {
        if (!e?.altKey) return;
        if (!(e?.rawcode === 32 || e?.keycode === 57)) return;
        if (!down) {
          down = true;
          if (!isListening) toggleListening();
        }
      });
      iohook.on("keyup", (e: any) => {
        if (!(e?.rawcode === 32 || e?.keycode === 57)) return;
        if (down) {
          down = false;
          if (isListening) toggleListening();
        }
      });
      iohook.start();
      showInfo("Hold-to-talk enabled");
    }
  } catch {
    showInfo("Hold-to-talk not available; using toggle");
  }
  const desired = config.behavior.hotkey || "Alt+Space";
  const registered = globalShortcut.register(desired, () => {
    toggleListening();
  });
  const ok = globalShortcut.isRegistered(desired);
  if (!registered || !ok) {
    showInfo(`Hotkey '${desired}' could not be registered; trying 'Ctrl+Alt+Space'`);
    const fallback = "Ctrl+Alt+Space";
    const reg2 = globalShortcut.register(fallback, () => {
      toggleListening();
    });
    if (reg2 && globalShortcut.isRegistered(fallback)) {
      showInfo(`Fallback hotkey '${fallback}' registered. Click tray icon to toggle as well.`);
    } else {
      showInfo("Global hotkey registration failed. Use tray click or menu to start/stop.");
    }
  } else {
    showInfo(`Hotkey '${desired}' registered. Click tray icon to toggle as well.`);
  }
});

app.on("window-all-closed", () => {
  // keep backgrounding; do not quit
});

ipcMain.handle("audio:final", async (_evt, payload: { base64: string; encoding: string }) => {
  return uploadAudio(payload.base64, payload.encoding);
});

ipcMain.on("tray-log", (_evt, msg: string) => {
  showInfo(msg);
});

ipcMain.on("tts:request", (_evt, payload: { text: string; voice?: string; rate?: number; pitch?: number; volume?: number }) => {
  try {
    showInfo("Main: tts:request received");
    if (!win || win.isDestroyed()) {
      showInfo("Main: hidden window missing; recreating");
      createWindow();
    }
    const sinkId = (payload as any)?.sinkId || config.tts?.output_device_id;
    const voice = payload?.voice || config.tts?.voice;
    speakTextViaEngine(payload?.text || "", { sinkId, voice });
  } catch (e) {
    showInfo(`Main: tts forward error: ${String(e)}`);
  }
});

ipcMain.handle("settings:get", async () => {
  return config;
});

ipcMain.handle("settings:update", async (_evt, patch: Partial<TrayConfig>) => {
  try {
    if (patch?.audio?.device_id) {
      config.audio.device_id = patch.audio.device_id;
    }
    if (patch?.tts) {
      config.tts = { ...config.tts, ...patch.tts };
    }
    return true;
  } catch {
    return false;
  }
});

ipcMain.handle("settings:openWindowsVoiceSettings", async () => {
  try {
    const ok = await shell.openExternal("ms-settings:speech");
    return ok;
  } catch {
    try {
      spawn("control.exe", ["/name", "Microsoft.TextToSpeech"], { detached: true, stdio: "ignore" }).unref();
      return true;
    } catch {
      return false;
    }
  }
});

ipcMain.handle("settings:listSapiVoices", async () => {
  return new Promise<string[]>((resolve) => {
    try {
      const script = [
        'Add-Type -AssemblyName System.Speech;',
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;',
        '$voices = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name };',
        '$s.Dispose();',
        '[System.String]::Join([System.Environment]::NewLine, $voices)'
      ].join('\n');
      const ps = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { windowsHide: true });
      let out = "";
      ps.stdout.on("data", d => (out += d.toString()));
      ps.on("exit", () => {
        const arr = out.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        resolve(arr);
      });
    } catch {
      resolve([]);
    }
  });
});

function speakTextViaEngine(text: string, opts: { sinkId?: string; voice?: string }) {
  if (!text) return;
  const engine = config.tts?.engine || "webspeech";
  if (engine === "sapi" && process.platform === "win32") {
    speakViaSapi(text, opts.voice)
      .then(base64 => {
        if (!win || win.isDestroyed()) createWindow();
        win?.webContents.send("tts:playAudio", { base64, sinkId: opts.sinkId });
      })
      .catch(err => {
        showInfo(`SAPI TTS failed: ${String(err)}`);
      });
  } else {
    if (!win || win.isDestroyed()) createWindow();
    win?.webContents.send("tts:speak", {
      text,
      voice: opts.voice,
      rate: config.tts?.rate,
      pitch: config.tts?.pitch,
      volume: config.tts?.volume,
      sinkId: opts.sinkId
    });
  }
}

function escapePS(s: string) {
  return s.replace(/'/g, "''");
}

function speakViaSapi(text: string, voice?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    try {
      const tmp = path.join(os.tmpdir(), `tray-tts-${Date.now()}.wav`);
      const voiceCmd = voice ? `$s.SelectVoice('${escapePS(voice)}');` : "";
      const scriptLines = [
        'Add-Type -AssemblyName System.Speech;',
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;',
        voiceCmd,
        '$s.Rate = 0;',
        '$s.Volume = 100;',
        `$path = '${tmp.replace(/\\/g, "\\\\")}';`,
        '$s.SetOutputToWaveFile($path);',
        `$s.Speak('${escapePS(text)}');`,
        '$s.Dispose();',
        'Write-Output $path'
      ];
      const script = scriptLines.join('\n');
      const ps = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { windowsHide: true });
      let out = "";
      let err = "";
      ps.stdout.on("data", d => (out += d.toString()));
      ps.stderr.on("data", d => (err += d.toString()));
      ps.on("exit", code => {
        const p = out.trim().split(/\r?\n/).filter(Boolean).pop() || tmp;
        if (code !== 0) {
          reject(new Error(err || `PowerShell exited ${code}`));
          return;
        }
        try {
          const buf = fs.readFileSync(p);
          const b64 = buf.toString("base64");
          fs.unlink(p, () => {});
          resolve(b64);
        } catch (e) {
          reject(e);
        }
      });
    } catch (e) {
      reject(e);
    }
  });
}
