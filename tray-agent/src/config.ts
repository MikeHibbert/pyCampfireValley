export type TrayConfig = {
  server: {
    base_url: string;
    api_path: string;
    verify_tls: boolean;
    admin_token?: string;
  };
  audio: {
    device_id: string;
    sample_rate: number;
    channels: number;
    vad_enabled: boolean;
    vad_sensitivity: "high" | "medium" | "low";
    encoding: "wav" | "opus" | "flac";
    max_duration_seconds: number;
  };
  behavior: {
    push_to_talk: boolean;
    hotkey: string;
    auto_start: boolean;
    minimize_to_tray: boolean;
  };
  tts?: {
    enabled: boolean;
    voice?: string;
    rate: number;
    pitch: number;
    volume: number;
    output_device_id?: string;
    engine?: "webspeech" | "sapi";
  };
  stt?: {
    enabled: boolean;
    engine: "sapi" | "none";
  };
  routing: {
    default_campfire: string;
    allowlist: string[];
    prompt_template?: string;
  };
};

export const defaultConfig: TrayConfig = {
  server: {
    base_url: process.env.CF_TRAY_BASE_URL || "http://localhost:8000",
    api_path: process.env.CF_TRAY_API_PATH || "/api/voice/ingest",
    verify_tls: process.env.CF_TRAY_VERIFY_TLS ? process.env.CF_TRAY_VERIFY_TLS === "true" : true
  },
  audio: {
    device_id: "default",
    sample_rate: 16000,
    channels: 1,
    vad_enabled: true,
    vad_sensitivity: "medium",
    encoding: "wav",
    max_duration_seconds: 120
  },
  behavior: {
    push_to_talk: true,
    hotkey: "Alt+Space",
    auto_start: false,
    minimize_to_tray: true
  },
  tts: {
    enabled: true,
    voice: undefined,
    rate: 1.0,
    pitch: 1.0,
    volume: 1.0,
    engine: "webspeech"
  },
  stt: {
    enabled: true,
    engine: "sapi"
  },
  routing: {
    default_campfire: "Development Team",
    allowlist: ["Development Team", "Design Team", "QA Team"]
  }
};
