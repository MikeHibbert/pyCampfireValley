import base64
import email.utils
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import aiohttp


REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_GOOGLE_DOCS_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]
DEFAULT_GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

DEFAULT_GMAIL_ACTIONS = [
    {
        "id": "check_email",
        "label": "Check email",
        "description": "Read recent email and summarize relevant messages.",
        "triggers": ["check my email", "check my emails", "check gmail", "check inbox"],
    },
    {
        "id": "find_email",
        "label": "Find email",
        "description": "Search mailbox messages using the user's request as search intent.",
        "triggers": ["find email", "search email", "search my inbox", "look through my emails"],
    },
    {
        "id": "job_email_scan",
        "label": "Find job emails",
        "description": "Look for recruiter, hiring, interview, and role-related messages.",
        "triggers": ["job email", "job emails", "recruiter email", "hiring email", "interview email"],
    },
    {
        "id": "recent_email_activity",
        "label": "Recent email activity",
        "description": "Summarize recent inbox activity and related messages.",
        "triggers": ["recent email activity", "mail activity", "email activity"],
    },
]

DEFAULT_GOOGLE_DOCS_ACTIONS = [
    {
        "id": "search_documents",
        "label": "Search documents",
        "description": "Search Google Docs and summarize matching content.",
        "triggers": ["search docs", "search documents", "find documents", "find docs"],
    },
    {
        "id": "recent_documents",
        "label": "Recent document activity",
        "description": "Show recently modified Google Docs activity.",
        "triggers": ["recent docs", "recent documents", "document activity", "docs activity"],
    },
]

DEFAULT_GOOGLE_CALENDAR_ACTIONS = [
    {
        "id": "check_calendar",
        "label": "Check calendar",
        "description": "Review upcoming or recent calendar events.",
        "triggers": ["check calendar", "check my calendar", "show calendar", "calendar events"],
    },
    {
        "id": "search_calendar",
        "label": "Search calendar",
        "description": "Search calendar events for a topic or subject.",
        "triggers": ["search calendar", "find meetings", "find calendar event", "calendar search"],
    },
    {
        "id": "calendar_activity",
        "label": "Calendar activity",
        "description": "Summarize recent and upcoming calendar activity.",
        "triggers": ["calendar activity", "recent meetings", "my schedule"],
    },
]

DEFAULT_GOOGLE_DRIVE_ACTIONS = [
    {
        "id": "search_drive",
        "label": "Search drive files",
        "description": "Search Google Drive files beyond Docs and summarize matches.",
        "triggers": ["search drive", "find file", "find files", "search drive files", "drive activity"],
    },
    {
        "id": "recent_drive_activity",
        "label": "Recent drive activity",
        "description": "Show recent Google Drive file activity.",
        "triggers": ["recent drive activity", "drive activity", "recent files"],
    },
]

DEFAULT_GOOGLE_SHEETS_ACTIONS = [
    {
        "id": "search_sheets",
        "label": "Search sheets",
        "description": "Search Google Sheets and summarize matching workbook content.",
        "triggers": ["search sheets", "find sheets", "find spreadsheet", "search spreadsheet"],
    },
    {
        "id": "recent_sheets_activity",
        "label": "Recent sheets activity",
        "description": "Show recently modified spreadsheet activity.",
        "triggers": ["recent sheets", "sheet activity", "spreadsheet activity"],
    },
]

PROVIDER_SPECS: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "label": "Gmail",
        "description": "Read and filter Gmail messages through Zeitgeist.",
        "actions": DEFAULT_GMAIL_ACTIONS,
        "scopes": DEFAULT_GMAIL_SCOPES,
    },
    "google_docs": {
        "label": "Google Docs",
        "description": "Search and summarize Google Docs activity and content.",
        "actions": DEFAULT_GOOGLE_DOCS_ACTIONS,
        "scopes": DEFAULT_GOOGLE_DOCS_SCOPES,
    },
    "google_calendar": {
        "label": "Google Calendar",
        "description": "Search and summarize Google Calendar events and activity.",
        "actions": DEFAULT_GOOGLE_CALENDAR_ACTIONS,
        "scopes": DEFAULT_GOOGLE_CALENDAR_SCOPES,
    },
    "google_drive": {
        "label": "Google Drive",
        "description": "Search and summarize Drive files beyond Docs and Sheets.",
        "actions": DEFAULT_GOOGLE_DRIVE_ACTIONS,
        "scopes": DEFAULT_GOOGLE_DRIVE_SCOPES,
    },
    "google_sheets": {
        "label": "Google Sheets",
        "description": "Search and summarize spreadsheet content and activity.",
        "actions": DEFAULT_GOOGLE_SHEETS_ACTIONS,
        "scopes": DEFAULT_GOOGLE_SHEETS_SCOPES,
    },
}

GMAIL_INTENT_KEYWORDS = ["email", "emails", "gmail", "inbox", "mailbox", "message", "messages", "mail"]
DOCS_INTENT_KEYWORDS = ["doc", "docs", "document", "documents", "drive", "google doc", "google docs"]
CALENDAR_INTENT_KEYWORDS = ["calendar", "calendars", "meeting", "meetings", "schedule", "event", "events"]
DRIVE_INTENT_KEYWORDS = ["drive", "file", "files", "folder", "folders", "pdf", "slide", "slides"]
SHEETS_INTENT_KEYWORDS = ["sheet", "sheets", "spreadsheet", "spreadsheets", "workbook", "tabular"]
ACTIVITY_HINT_KEYWORDS = ["activity", "what have i", "what did i", "what's my activity", "whats my activity", "recent activity"]
JOB_HINT_KEYWORDS = [
    "job",
    "jobs",
    "hiring",
    "recruiter",
    "recruiters",
    "interview",
    "interviews",
    "application",
    "applications",
    "position",
    "positions",
    "role",
    "roles",
]
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "calendar",
    "check",
    "docs",
    "document",
    "documents",
    "email",
    "emails",
    "event",
    "events",
    "file",
    "files",
    "find",
    "for",
    "from",
    "gmail",
    "google",
    "i",
    "in",
    "is",
    "mail",
    "meeting",
    "meetings",
    "messages",
    "my",
    "of",
    "on",
    "or",
    "please",
    "recent",
    "schedule",
    "search",
    "sheet",
    "sheets",
    "show",
    "spreadsheet",
    "the",
    "to",
    "with",
}

_GOOGLE_OAUTH_STATE: Dict[str, Dict[str, Any]] = {}


def _repo_path(path_value: Optional[str], fallback_relative: str) -> Path:
    raw = str(path_value or "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (REPO_ROOT / path)
    return REPO_ROOT / fallback_relative


def _normalize_actions(actions: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in actions or []:
        if not isinstance(raw, dict):
            continue
        out.append(
            {
                "id": str(raw.get("id") or "").strip(),
                "label": str(raw.get("label") or raw.get("id") or "").strip(),
                "description": str(raw.get("description") or "").strip(),
                "triggers": [str(t).strip() for t in (raw.get("triggers") or []) if str(t).strip()],
            }
        )
    return [item for item in out if item.get("id")]


def _plugin_cfg(zeitgeist_cfg: Optional[Dict[str, Any]], plugin_id: str) -> Dict[str, Any]:
    z = zeitgeist_cfg if isinstance(zeitgeist_cfg, dict) else {}
    plugins = z.get("plugins") if isinstance(z.get("plugins"), dict) else {}
    raw = plugins.get(plugin_id) if isinstance(plugins.get(plugin_id), dict) else {}
    spec = PROVIDER_SPECS.get(plugin_id) or {}
    default_actions = spec.get("actions") or []
    default_scopes = spec.get("scopes") or []
    return {
        "enabled": bool(raw.get("enabled")),
        "credentials_path": str(raw.get("credentials_path") or "credentials/gog_credentials.json").strip(),
        "token_path": str(raw.get("token_path") or "credentials/gmail_token.json").strip(),
        "default_query": str(raw.get("default_query") or "").strip(),
        "max_results": int(raw.get("max_results") or 8),
        "actions": raw.get("actions") if isinstance(raw.get("actions"), list) else default_actions,
        "scopes": raw.get("scopes") if isinstance(raw.get("scopes"), list) and raw.get("scopes") else list(default_scopes),
        "filters": _zeitgeist_filters(zeitgeist_cfg),
    }


def _zeitgeist_filters(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, str]:
    z = zeitgeist_cfg if isinstance(zeitgeist_cfg, dict) else {}
    raw = z.get("filters") if isinstance(z.get("filters"), dict) else {}
    return {
        "subject": str(raw.get("subject") or "").strip(),
        "person": str(raw.get("person") or "").strip(),
        "date_range": str(raw.get("date_range") or "").strip(),
        "custom_start": str(raw.get("custom_start") or "").strip(),
        "custom_end": str(raw.get("custom_end") or "").strip(),
    }


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_google_credentials(plugin_cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = _repo_path(plugin_cfg.get("credentials_path"), "credentials/gog_credentials.json")
    raw = _load_json(path)
    block = raw.get("installed") if isinstance(raw.get("installed"), dict) else raw.get("web")
    if not isinstance(block, dict):
        raise ValueError(f"Google credentials not found or invalid at '{path}'")
    return block


def _granted_scopes(token_data: Dict[str, Any]) -> List[str]:
    scope_text = str(token_data.get("scope") or "").strip()
    return [item.strip() for item in scope_text.split(" ") if item.strip()]


def google_provider_status(plugin_id: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, plugin_id)
    credentials_path = _repo_path(cfg.get("credentials_path"), "credentials/gog_credentials.json")
    token_path = _repo_path(cfg.get("token_path"), "credentials/gmail_token.json")
    token_data = _load_json(token_path)
    expires_at = float(token_data.get("expires_at") or 0.0) if isinstance(token_data, dict) else 0.0
    granted = _granted_scopes(token_data if isinstance(token_data, dict) else {})
    scopes_ready = None
    if granted:
        scopes_ready = all(scope in granted for scope in (cfg.get("scopes") or []))
    spec = PROVIDER_SPECS.get(plugin_id) or {}
    return {
        "id": plugin_id,
        "label": str(spec.get("label") or plugin_id),
        "enabled": bool(cfg.get("enabled")),
        "credentials_path": str(credentials_path),
        "token_path": str(token_path),
        "credentials_present": credentials_path.exists(),
        "authorized": bool(isinstance(token_data, dict) and token_data.get("refresh_token")),
        "token_present": bool(isinstance(token_data, dict) and token_data.get("access_token")),
        "token_expires_at": expires_at or None,
        "actions": _normalize_actions(cfg.get("actions")),
        "scopes": list(cfg.get("scopes") or []),
        "granted_scopes": granted,
        "scopes_ready": scopes_ready,
    }


def gmail_plugin_status(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return google_provider_status("gmail", zeitgeist_cfg)


def google_docs_plugin_status(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return google_provider_status("google_docs", zeitgeist_cfg)


def google_calendar_plugin_status(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return google_provider_status("google_calendar", zeitgeist_cfg)


def google_drive_plugin_status(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return google_provider_status("google_drive", zeitgeist_cfg)


def google_sheets_plugin_status(zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return google_provider_status("google_sheets", zeitgeist_cfg)


def get_zeitgeist_plugin_catalog(zeitgeist_cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for plugin_id, spec in PROVIDER_SPECS.items():
        status = google_provider_status(plugin_id, zeitgeist_cfg)
        out.append(
            {
                "id": plugin_id,
                "label": spec.get("label") or plugin_id,
                "description": spec.get("description") or "",
                "enabled": status["enabled"],
                "auth_required": True,
                "authorized": status["authorized"],
                "credentials_present": status["credentials_present"],
                "scopes_ready": status["scopes_ready"],
                "actions": status["actions"],
            }
        )
    return out


def describe_zeitgeist_capabilities(zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[str]:
    z = zeitgeist_cfg if isinstance(zeitgeist_cfg, dict) else {}
    out: List[str] = []
    if z.get("enabled") and z.get("web_search"):
        out.append("web_search")
    if z.get("enabled") and z.get("image_ocr"):
        out.append("image_ocr")
    for plugin_id in PROVIDER_SPECS:
        status = google_provider_status(plugin_id, zeitgeist_cfg)
        if status["enabled"]:
            actions = ", ".join(a.get("id") or "" for a in status["actions"] if isinstance(a, dict))
            out.append(f"{plugin_id}[{actions}]".strip())
    return [item for item in out if item]


def _extract_phrase(text: str, marker: str) -> str:
    parts = text.split(f" {marker} ", 1)
    if len(parts) != 2:
        return ""
    phrase = parts[1].strip()
    for stop in (" in ", " from ", " on ", " with ", " and ", " please ", "?", ".", ","):
        idx = phrase.find(stop)
        if idx > 0:
            phrase = phrase[:idx]
            break
    return phrase.strip(" \"'")


def _keyword_terms(text: str) -> List[str]:
    tokens = []
    for token in re.findall(r"[a-z0-9][a-z0-9._+-]*", str(text or "").lower()):
        if token in STOPWORDS or len(token) < 2:
            continue
        tokens.append(token)
    deduped: List[str] = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _search_terms(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[str]:
    filters = _zeitgeist_filters(zeitgeist_cfg)
    phrase = _extract_phrase(str(user_text or "").lower(), "for") or _extract_phrase(str(user_text or "").lower(), "about")
    base_terms = _keyword_terms(phrase or user_text)
    for extra in (filters.get("subject"), filters.get("person")):
        if extra:
            for token in _keyword_terms(extra):
                if token not in base_terms:
                    base_terms.append(token)
    return base_terms[:10]


def _date_range_bounds(filters: Dict[str, str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    now = datetime.now(timezone.utc)
    mode = str(filters.get("date_range") or "").strip().lower()
    if mode == "last_7d":
        return now - timedelta(days=7), now
    if mode == "last_30d":
        return now - timedelta(days=30), now
    if mode == "last_90d":
        return now - timedelta(days=90), now
    if mode == "upcoming_30d":
        return now, now + timedelta(days=30)
    if mode == "custom":
        start = str(filters.get("custom_start") or "").strip()
        end = str(filters.get("custom_end") or "").strip()
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
        except Exception:
            start_dt = None
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
        except Exception:
            end_dt = None
        return start_dt, end_dt
    return None, None


def _iso_or_none(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_request_for_plugin(low: str, plugin_id: str, cfg: Dict[str, Any]) -> bool:
    keywords = []
    if plugin_id == "gmail":
        keywords = GMAIL_INTENT_KEYWORDS
    elif plugin_id == "google_docs":
        keywords = DOCS_INTENT_KEYWORDS
    elif plugin_id == "google_calendar":
        keywords = CALENDAR_INTENT_KEYWORDS
    elif plugin_id == "google_drive":
        keywords = DRIVE_INTENT_KEYWORDS
    elif plugin_id == "google_sheets":
        keywords = SHEETS_INTENT_KEYWORDS
    if any(k in low for k in keywords):
        return True
    for action in _normalize_actions(cfg.get("actions")):
        for trigger in action.get("triggers") or []:
            if trigger and trigger.lower() in low:
                return True
    return False


def _is_activity_request(low: str) -> bool:
    return any(k in low for k in ACTIVITY_HINT_KEYWORDS)


def match_zeitgeist_actions(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    text = str(user_text or "").strip()
    if not text:
        return []
    low = text.lower()
    matches: List[Dict[str, str]] = []

    gmail = _plugin_cfg(zeitgeist_cfg, "gmail")
    if gmail.get("enabled") and (_is_request_for_plugin(low, "gmail", gmail) or _is_activity_request(low)):
        action_id = "check_email"
        if any(k in low for k in JOB_HINT_KEYWORDS):
            action_id = "job_email_scan"
        elif _is_activity_request(low):
            action_id = "recent_email_activity"
        elif any(k in low for k in ("find", "search", "look through", "show")):
            action_id = "find_email"
        matches.append({"plugin": "gmail", "action": action_id})

    docs = _plugin_cfg(zeitgeist_cfg, "google_docs")
    if docs.get("enabled") and (_is_request_for_plugin(low, "google_docs", docs) or _is_activity_request(low)):
        action_id = "recent_documents" if _is_activity_request(low) and not _is_request_for_plugin(low, "google_docs", docs) else "search_documents"
        if "recent" in low or "activity" in low:
            action_id = "recent_documents"
        matches.append({"plugin": "google_docs", "action": action_id})

    cal = _plugin_cfg(zeitgeist_cfg, "google_calendar")
    if cal.get("enabled") and (_is_request_for_plugin(low, "google_calendar", cal) or _is_activity_request(low)):
        action_id = "calendar_activity" if _is_activity_request(low) and not _is_request_for_plugin(low, "google_calendar", cal) else "check_calendar"
        if any(k in low for k in ("find", "search", "about")):
            action_id = "search_calendar"
        if "activity" in low or "recent" in low:
            action_id = "calendar_activity"
        matches.append({"plugin": "google_calendar", "action": action_id})

    drive = _plugin_cfg(zeitgeist_cfg, "google_drive")
    if drive.get("enabled") and (_is_request_for_plugin(low, "google_drive", drive) or _is_activity_request(low)):
        action_id = "recent_drive_activity" if ("activity" in low or "recent" in low) else "search_drive"
        matches.append({"plugin": "google_drive", "action": action_id})

    sheets = _plugin_cfg(zeitgeist_cfg, "google_sheets")
    if sheets.get("enabled") and (_is_request_for_plugin(low, "google_sheets", sheets) or _is_activity_request(low)):
        action_id = "recent_sheets_activity" if ("activity" in low or "recent" in low) else "search_sheets"
        matches.append({"plugin": "google_sheets", "action": action_id})

    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in matches:
        key = (item.get("plugin"), item.get("action"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def build_gmail_query(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> str:
    cfg = _plugin_cfg(zeitgeist_cfg, "gmail")
    low = str(user_text or "").lower()
    filters = cfg.get("filters") or {}
    parts: List[str] = [cfg.get("default_query") or "in:inbox newer_than:30d"]
    if "unread" in low:
        parts.append("is:unread")
    if "starred" in low:
        parts.append("is:starred")
    from_match = _extract_phrase(low, "from") or str(filters.get("person") or "").strip().lower()
    if from_match:
        parts.append(f"from:{from_match}")
    subject_filter = str(filters.get("subject") or "").strip()
    if subject_filter:
        parts.append(f"subject:({subject_filter})")
    terms = _search_terms(user_text, zeitgeist_cfg)
    if terms:
        parts.extend(terms[:6])
    elif any(k in low for k in JOB_HINT_KEYWORDS):
        parts.extend(["job", "recruiter", "hiring", "interview", "application"])
    start_dt, end_dt = _date_range_bounds(filters)
    if start_dt:
        parts.append(f"after:{start_dt.strftime('%Y/%m/%d')}")
    if end_dt:
        parts.append(f"before:{end_dt.strftime('%Y/%m/%d')}")
    return " ".join(p for p in parts if p).strip()


def _google_redirect_uri(base_url: str) -> str:
    base = str(base_url or "").rstrip("/")
    return f"{base}/api/zeitgeist/plugins/google/auth/callback"


def _enabled_google_scopes(zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[str]:
    scopes: List[str] = []
    for plugin_id in PROVIDER_SPECS:
        cfg = _plugin_cfg(zeitgeist_cfg, plugin_id)
        if not cfg.get("enabled"):
            continue
        for scope in cfg.get("scopes") or []:
            if scope and scope not in scopes:
                scopes.append(scope)
    if not scopes:
        for scope in DEFAULT_GMAIL_SCOPES:
            scopes.append(scope)
    return scopes


def create_google_auth_start(base_url: str, zeitgeist_cfg: Optional[Dict[str, Any]], campfire: str) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "gmail")
    creds = _load_google_credentials(cfg)
    state = secrets.token_urlsafe(24)
    redirect_uri = _google_redirect_uri(base_url)
    _GOOGLE_OAUTH_STATE[state] = {
        "campfire": str(campfire or "").strip(),
        "created_at": time.time(),
        "redirect_uri": redirect_uri,
    }
    params = {
        "client_id": creds.get("client_id") or "",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_enabled_google_scopes(zeitgeist_cfg)),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    auth_url = f"{creds.get('auth_uri') or 'https://accounts.google.com/o/oauth2/auth'}?{urlencode(params)}"
    return {"state": state, "auth_url": auth_url, "redirect_uri": redirect_uri}


def peek_google_auth_state(state: str) -> Dict[str, Any]:
    raw = _GOOGLE_OAUTH_STATE.get(str(state or "").strip()) or {}
    return dict(raw) if isinstance(raw, dict) else {}


async def finish_google_oauth(code: str, state: str, base_url: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    pending = _GOOGLE_OAUTH_STATE.pop(str(state or "").strip(), None)
    if not pending:
        raise ValueError("OAuth state is missing or expired")
    cfg = _plugin_cfg(zeitgeist_cfg, "gmail")
    creds = _load_google_credentials(cfg)
    redirect_uri = str(pending.get("redirect_uri") or _google_redirect_uri(base_url)).strip()
    token_payload = {
        "code": str(code or "").strip(),
        "client_id": creds.get("client_id") or "",
        "client_secret": creds.get("client_secret") or "",
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    token_uri = creds.get("token_uri") or "https://oauth2.googleapis.com/token"
    async with aiohttp.ClientSession() as session:
        async with session.post(token_uri, data=token_payload, timeout=aiohttp.ClientTimeout(total=15.0)) as resp:
            data = await resp.json()
            if resp.status >= 400:
                detail = data.get("error_description") or data.get("error") or f"HTTP {resp.status}"
                raise ValueError(f"Failed to exchange Google auth code: {detail}")
    token_data = _normalize_token_payload(data)
    token_path = _repo_path(cfg.get("token_path"), "credentials/gmail_token.json")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    return {
        "campfire": pending.get("campfire") or "",
        "authorized": True,
        "token_path": str(token_path),
        "expires_at": token_data.get("expires_at"),
        "granted_scopes": _granted_scopes(token_data),
    }


create_gmail_auth_start = create_google_auth_start
peek_gmail_auth_state = peek_google_auth_state
finish_gmail_oauth = finish_google_oauth


def _normalize_token_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    token = dict(data or {})
    expires_in = float(token.get("expires_in") or 0.0)
    token["expires_at"] = time.time() + expires_in if expires_in else 0.0
    return token


async def _google_access_token(plugin_cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    token_path = _repo_path(plugin_cfg.get("token_path"), "credentials/gmail_token.json")
    token = _load_json(token_path)
    access_token = str(token.get("access_token") or "").strip()
    refresh_token = str(token.get("refresh_token") or "").strip()
    expires_at = float(token.get("expires_at") or 0.0)
    if access_token and expires_at > (time.time() + 60.0):
        return access_token, token
    if not refresh_token:
        raise ValueError("Google plugin is not authorized yet")
    creds = _load_google_credentials(plugin_cfg)
    payload = {
        "client_id": creds.get("client_id") or "",
        "client_secret": creds.get("client_secret") or "",
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    token_uri = creds.get("token_uri") or "https://oauth2.googleapis.com/token"
    async with aiohttp.ClientSession() as session:
        async with session.post(token_uri, data=payload, timeout=aiohttp.ClientTimeout(total=15.0)) as resp:
            data = await resp.json()
            if resp.status >= 400:
                detail = data.get("error_description") or data.get("error") or f"HTTP {resp.status}"
                raise ValueError(f"Failed to refresh Google token: {detail}")
    refreshed = dict(token)
    refreshed.update(data or {})
    refreshed["refresh_token"] = refresh_token
    refreshed = _normalize_token_payload(refreshed)
    if "scope" not in refreshed and "scope" in token:
        refreshed["scope"] = token.get("scope")
    token_path.write_text(json.dumps(refreshed, indent=2), encoding="utf-8")
    return str(refreshed.get("access_token") or "").strip(), refreshed


async def _google_get_json(url: str, access_token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=20.0)) as resp:
            data = await resp.json()
            if resp.status >= 400:
                detail = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else data.get("error")
                raise ValueError(f"Google API request failed: {detail or resp.status}")
            return data if isinstance(data, dict) else {}


def _extract_gmail_body(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    mime = str(payload.get("mimeType") or "").lower()
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    data = str(body.get("data") or "").strip()
    if data and ("text/plain" in mime or not mime):
        try:
            pad = "=" * (-len(data) % 4)
            return base64.urlsafe_b64decode((data + pad).encode("ascii")).decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""
    parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []
    for part in parts:
        text = _extract_gmail_body(part if isinstance(part, dict) else {})
        if text:
            return text
    return ""


def _parse_gmail_message(detail: Dict[str, Any]) -> Dict[str, Any]:
    payload = detail.get("payload") if isinstance(detail.get("payload"), dict) else {}
    headers = payload.get("headers") if isinstance(payload.get("headers"), list) else []
    header_map: Dict[str, str] = {}
    for item in headers:
        if not isinstance(item, dict):
            continue
        key = str(item.get("name") or "").strip().lower()
        if key and key not in header_map:
            header_map[key] = str(item.get("value") or "").strip()
    body = _extract_gmail_body(payload)
    return {
        "id": str(detail.get("id") or "").strip(),
        "thread_id": str(detail.get("threadId") or "").strip(),
        "from": header_map.get("from", ""),
        "subject": header_map.get("subject", ""),
        "date": header_map.get("date", ""),
        "snippet": str(detail.get("snippet") or "").strip(),
        "body": body[:4000],
        "labels": detail.get("labelIds") or [],
    }


async def _gmail_list_messages(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "gmail")
    access_token, _ = await _google_access_token(cfg)
    query = build_gmail_query(user_text, zeitgeist_cfg)
    list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    params = {"q": query, "maxResults": max(1, min(int(cfg.get("max_results") or 8), 20))}
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(list_url, params=params, timeout=aiohttp.ClientTimeout(total=15.0)) as resp:
            data = await resp.json()
            if resp.status >= 400:
                detail = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else data.get("error")
                raise ValueError(f"Gmail list failed: {detail or resp.status}")
            items = data.get("messages") or []
        messages: List[Dict[str, Any]] = []
        for item in items[: params["maxResults"]]:
            msg_id = str((item or {}).get("id") or "").strip()
            if not msg_id:
                continue
            detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
            async with session.get(detail_url, params={"format": "full"}, timeout=aiohttp.ClientTimeout(total=15.0)) as resp:
                detail = await resp.json()
                if resp.status >= 400:
                    continue
            parsed = _parse_gmail_message(detail)
            if parsed:
                messages.append(parsed)
    return {"query": query, "messages": messages}


def _doc_text_from_elements(elements: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for elem in elements or []:
        if not isinstance(elem, dict):
            continue
        para = elem.get("paragraph") if isinstance(elem.get("paragraph"), dict) else {}
        for pe in para.get("elements") or []:
            if not isinstance(pe, dict):
                continue
            text_run = pe.get("textRun") if isinstance(pe.get("textRun"), dict) else {}
            content = str(text_run.get("content") or "").strip()
            if content:
                parts.append(content)
        table = elem.get("table") if isinstance(elem.get("table"), dict) else {}
        for row in table.get("tableRows") or []:
            cells = row.get("tableCells") if isinstance(row, dict) else []
            for cell in cells or []:
                content = cell.get("content") if isinstance(cell, dict) else []
                cell_text = _doc_text_from_elements(content if isinstance(content, list) else [])
                if cell_text:
                    parts.append(cell_text)
        toc = elem.get("tableOfContents") if isinstance(elem.get("tableOfContents"), dict) else {}
        toc_content = toc.get("content") if isinstance(toc, dict) else []
        toc_text = _doc_text_from_elements(toc_content if isinstance(toc_content, list) else [])
        if toc_text:
            parts.append(toc_text)
    return " ".join(" ".join(parts).split())


def _docs_search_terms(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[str]:
    return _search_terms(user_text, zeitgeist_cfg)[:8]


def _drive_search_terms(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> List[str]:
    return _search_terms(user_text, zeitgeist_cfg)[:8]


def _drive_file_query(mime_filter: str, user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> str:
    filters = _zeitgeist_filters(zeitgeist_cfg)
    low = str(user_text or "").lower()
    parts = [mime_filter, "trashed=false"]
    start_dt, end_dt = _date_range_bounds(filters)
    if not start_dt and ("recent" in low or _is_activity_request(low)):
        start_dt = datetime.now(timezone.utc) - timedelta(days=30)
    if start_dt:
        parts.append(f"modifiedTime >= '{_iso_or_none(start_dt)}'")
    if end_dt:
        parts.append(f"modifiedTime <= '{_iso_or_none(end_dt)}'")
    person = str(filters.get("person") or "").strip()
    if person:
        safe_person = person.replace("'", "\\'")
        parts.append(f"('{safe_person}' in writers or '{safe_person}' in owners or '{safe_person}' in readers)")
    return " and ".join(p for p in parts if p)


def _score_haystack(haystack: str, terms: List[str], filters: Dict[str, str]) -> int:
    score = 0
    low = haystack.lower()
    for term in terms:
        if term in low:
            score += 1
    subject = str(filters.get("subject") or "").strip().lower()
    if subject and subject in low:
        score += 2
    person = str(filters.get("person") or "").strip().lower()
    if person and person in low:
        score += 1
    return score


async def _google_docs_search(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "google_docs")
    access_token, _ = await _google_access_token(cfg)
    query = _drive_file_query("mimeType='application/vnd.google-apps.document'", user_text, zeitgeist_cfg)
    data = await _google_get_json(
        "https://www.googleapis.com/drive/v3/files",
        access_token,
        params={
            "q": query,
            "pageSize": max(1, min(int(cfg.get("max_results") or 8), 12)),
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,modifiedTime,webViewLink,owners(displayName,emailAddress))",
        },
    )
    terms = _docs_search_terms(user_text, zeitgeist_cfg)
    filters = cfg.get("filters") or {}
    docs: List[Dict[str, Any]] = []
    for item in data.get("files") or []:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("id") or "").strip()
        if not doc_id:
            continue
        body_text = ""
        try:
            detail = await _google_get_json(f"https://docs.googleapis.com/v1/documents/{doc_id}", access_token, params={})
            body = detail.get("body") if isinstance(detail.get("body"), dict) else {}
            body_text = _doc_text_from_elements(body.get("content") if isinstance(body.get("content"), list) else [])
        except Exception:
            body_text = ""
        haystack = f"{item.get('name') or ''}\n{body_text}"
        score = _score_haystack(haystack, terms, filters)
        if terms and score == 0 and not _is_activity_request(str(user_text or "").lower()):
            continue
        docs.append(
            {
                "id": doc_id,
                "name": str(item.get("name") or "").strip(),
                "modified_time": str(item.get("modifiedTime") or "").strip(),
                "web_view_link": str(item.get("webViewLink") or "").strip(),
                "owners": item.get("owners") or [],
                "excerpt": body_text[:2000],
                "score": score,
            }
        )
    docs.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("modified_time") or "")), reverse=True)
    return {"terms": terms, "documents": docs[: max(1, min(int(cfg.get("max_results") or 8), 8))]}


async def _google_drive_search(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "google_drive")
    access_token, _ = await _google_access_token(cfg)
    query = _drive_file_query(
        "mimeType!='application/vnd.google-apps.document' and mimeType!='application/vnd.google-apps.spreadsheet' and mimeType!='application/vnd.google-apps.folder'",
        user_text,
        zeitgeist_cfg,
    )
    data = await _google_get_json(
        "https://www.googleapis.com/drive/v3/files",
        access_token,
        params={
            "q": query,
            "pageSize": max(1, min(int(cfg.get("max_results") or 8), 12)),
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),description)",
        },
    )
    terms = _drive_search_terms(user_text, zeitgeist_cfg)
    filters = cfg.get("filters") or {}
    files: List[Dict[str, Any]] = []
    for item in data.get("files") or []:
        if not isinstance(item, dict):
            continue
        haystack = f"{item.get('name') or ''}\n{item.get('description') or ''}\n{item.get('mimeType') or ''}"
        score = _score_haystack(haystack, terms, filters)
        if terms and score == 0 and not _is_activity_request(str(user_text or "").lower()):
            continue
        files.append(
            {
                "id": str(item.get("id") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "mime_type": str(item.get("mimeType") or "").strip(),
                "modified_time": str(item.get("modifiedTime") or "").strip(),
                "web_view_link": str(item.get("webViewLink") or "").strip(),
                "owners": item.get("owners") or [],
                "description": str(item.get("description") or "").strip(),
                "score": score,
            }
        )
    files.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("modified_time") or "")), reverse=True)
    return {"terms": terms, "files": files[: max(1, min(int(cfg.get("max_results") or 8), 8))]}


async def _google_sheets_search(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "google_sheets")
    access_token, _ = await _google_access_token(cfg)
    query = _drive_file_query("mimeType='application/vnd.google-apps.spreadsheet'", user_text, zeitgeist_cfg)
    data = await _google_get_json(
        "https://www.googleapis.com/drive/v3/files",
        access_token,
        params={
            "q": query,
            "pageSize": max(1, min(int(cfg.get("max_results") or 8), 10)),
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,modifiedTime,webViewLink,owners(displayName,emailAddress))",
        },
    )
    terms = _search_terms(user_text, zeitgeist_cfg)
    filters = cfg.get("filters") or {}
    sheets: List[Dict[str, Any]] = []
    for item in data.get("files") or []:
        if not isinstance(item, dict):
            continue
        sheet_id = str(item.get("id") or "").strip()
        if not sheet_id:
            continue
        spreadsheet = await _google_get_json(
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
            access_token,
            params={"fields": "properties.title,sheets(properties.title)"},
        )
        tabs = []
        for sheet in spreadsheet.get("sheets") or []:
            props = sheet.get("properties") if isinstance(sheet, dict) else {}
            title = str((props or {}).get("title") or "").strip()
            if title:
                tabs.append(title)
        preview_ranges = [f"{tab}!A1:E8" for tab in tabs[:2]] or ["A1:E8"]
        values_payload = await _google_get_json(
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchGet",
            access_token,
            params=[("ranges", rng) for rng in preview_ranges] + [("majorDimension", "ROWS")],
        )
        preview_chunks: List[str] = []
        for vr in values_payload.get("valueRanges") or []:
            if not isinstance(vr, dict):
                continue
            for row in vr.get("values") or []:
                if isinstance(row, list):
                    preview_chunks.append(" | ".join(str(cell) for cell in row[:8]))
        preview_text = "\n".join(preview_chunks)
        haystack = f"{item.get('name') or ''}\n{' '.join(tabs)}\n{preview_text}"
        score = _score_haystack(haystack, terms, filters)
        if terms and score == 0 and not _is_activity_request(str(user_text or "").lower()):
            continue
        sheets.append(
            {
                "id": sheet_id,
                "name": str(item.get("name") or "").strip(),
                "modified_time": str(item.get("modifiedTime") or "").strip(),
                "web_view_link": str(item.get("webViewLink") or "").strip(),
                "owners": item.get("owners") or [],
                "tabs": tabs,
                "preview": preview_text[:2000],
                "score": score,
            }
        )
    sheets.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("modified_time") or "")), reverse=True)
    return {"terms": terms, "sheets": sheets[: max(1, min(int(cfg.get("max_results") or 8), 8))]}


def _calendar_window(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    low = str(user_text or "").lower()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now + timedelta(days=14)
    filters = _zeitgeist_filters(zeitgeist_cfg)
    filtered_start, filtered_end = _date_range_bounds(filters)
    if filtered_start:
        start = filtered_start
    if filtered_end:
        end = filtered_end
    if "today" in low:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif "tomorrow" in low:
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif "this week" in low:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif "next week" in low:
        start = (now - timedelta(days=now.weekday()) + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif not filtered_start and (_is_activity_request(low) or "recent" in low):
        start = now - timedelta(days=14)
        end = now + timedelta(days=2)
    return (_iso_or_none(start), _iso_or_none(end))


def _calendar_terms(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> str:
    terms = _search_terms(user_text, zeitgeist_cfg)
    return " ".join(terms[:6]).strip()


async def _google_calendar_search(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _plugin_cfg(zeitgeist_cfg, "google_calendar")
    access_token, _ = await _google_access_token(cfg)
    time_min, time_max = _calendar_window(user_text, zeitgeist_cfg)
    query_text = _calendar_terms(user_text, zeitgeist_cfg)
    params: Dict[str, Any] = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max(1, min(int(cfg.get("max_results") or 8), 12)),
    }
    if query_text and not _is_activity_request(str(user_text or "").lower()):
        params["q"] = query_text
    data = await _google_get_json("https://www.googleapis.com/calendar/v3/calendars/primary/events", access_token, params=params)
    events: List[Dict[str, Any]] = []
    filters = cfg.get("filters") or {}
    terms = _search_terms(user_text, zeitgeist_cfg)
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        start = item.get("start") if isinstance(item.get("start"), dict) else {}
        end = item.get("end") if isinstance(item.get("end"), dict) else {}
        haystack = f"{item.get('summary') or ''}\n{item.get('description') or ''}\n{item.get('location') or ''}\n{(item.get('organizer') or {}).get('email', '') if isinstance(item.get('organizer'), dict) else ''}"
        score = _score_haystack(haystack, terms, filters)
        if terms and score == 0 and not _is_activity_request(str(user_text or "").lower()) and params.get("q"):
            continue
        events.append(
            {
                "id": str(item.get("id") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "html_link": str(item.get("htmlLink") or "").strip(),
                "start": str(start.get("dateTime") or start.get("date") or "").strip(),
                "end": str(end.get("dateTime") or end.get("date") or "").strip(),
                "organizer": (item.get("organizer") or {}).get("email", "") if isinstance(item.get("organizer"), dict) else "",
                "score": score,
            }
        )
    return {"query": query_text, "time_min": time_min, "time_max": time_max, "events": events}


def _gmail_context_from_result(result: Dict[str, Any], action_id: str) -> str:
    messages = result.get("messages") or []
    query = str(result.get("query") or "").strip()
    if not messages:
        return f"Gmail plugin ({action_id}) found no matching messages for query: {query}"
    lines = [f"Gmail plugin action: {action_id}", f"Gmail search query: {query}", "Recent matching messages:"]
    for idx, msg in enumerate(messages[:10], start=1):
        snippet = " ".join(str(msg.get("snippet") or msg.get("body") or "").split())[:500]
        labels = ", ".join(str(x) for x in (msg.get("labels") or [])[:6])
        lines.append(
            f"{idx}. From: {msg.get('from') or '(unknown)'}\n"
            f"   Subject: {msg.get('subject') or '(no subject)'}\n"
            f"   Date: {msg.get('date') or '(unknown)'}\n"
            f"   Labels: {labels or '(none)'}\n"
            f"   Snippet: {snippet or '(empty)'}"
        )
    return "\n".join(lines)


def _docs_context_from_result(result: Dict[str, Any], action_id: str) -> str:
    docs = result.get("documents") or []
    terms = result.get("terms") or []
    if not docs:
        if terms:
            return f"Google Docs plugin ({action_id}) found no matching documents for terms: {', '.join(terms)}"
        return f"Google Docs plugin ({action_id}) found no recent matching document activity."
    lines = [f"Google Docs plugin action: {action_id}", f"Search terms: {', '.join(terms) if terms else '(recent activity)'}", "Matching documents:"]
    for idx, doc in enumerate(docs[:8], start=1):
        owner = ""
        owners = doc.get("owners") or []
        if owners and isinstance(owners[0], dict):
            owner = str(owners[0].get("displayName") or owners[0].get("emailAddress") or "").strip()
        excerpt = " ".join(str(doc.get("excerpt") or "").split())[:500]
        lines.append(
            f"{idx}. Document: {doc.get('name') or '(untitled)'}\n"
            f"   Modified: {doc.get('modified_time') or '(unknown)'}\n"
            f"   Owner: {owner or '(unknown)'}\n"
            f"   Link: {doc.get('web_view_link') or '(none)'}\n"
            f"   Excerpt: {excerpt or '(empty)'}"
        )
    return "\n".join(lines)


def _drive_context_from_result(result: Dict[str, Any], action_id: str) -> str:
    files = result.get("files") or []
    terms = result.get("terms") or []
    if not files:
        return f"Google Drive plugin ({action_id}) found no matching files." if not terms else f"Google Drive plugin ({action_id}) found no files for terms: {', '.join(terms)}"
    lines = [f"Google Drive plugin action: {action_id}", f"Search terms: {', '.join(terms) if terms else '(recent activity)'}", "Matching files:"]
    for idx, item in enumerate(files[:8], start=1):
        lines.append(
            f"{idx}. File: {item.get('name') or '(untitled)'}\n"
            f"   Type: {item.get('mime_type') or '(unknown)'}\n"
            f"   Modified: {item.get('modified_time') or '(unknown)'}\n"
            f"   Link: {item.get('web_view_link') or '(none)'}\n"
            f"   Description: {item.get('description') or '(empty)'}"
        )
    return "\n".join(lines)


def _sheets_context_from_result(result: Dict[str, Any], action_id: str) -> str:
    sheets = result.get("sheets") or []
    terms = result.get("terms") or []
    if not sheets:
        return f"Google Sheets plugin ({action_id}) found no matching spreadsheets." if not terms else f"Google Sheets plugin ({action_id}) found no spreadsheets for terms: {', '.join(terms)}"
    lines = [f"Google Sheets plugin action: {action_id}", f"Search terms: {', '.join(terms) if terms else '(recent activity)'}", "Matching spreadsheets:"]
    for idx, item in enumerate(sheets[:8], start=1):
        preview = " ".join(str(item.get("preview") or "").split())[:500]
        lines.append(
            f"{idx}. Spreadsheet: {item.get('name') or '(untitled)'}\n"
            f"   Modified: {item.get('modified_time') or '(unknown)'}\n"
            f"   Tabs: {', '.join(item.get('tabs') or []) or '(none)'}\n"
            f"   Link: {item.get('web_view_link') or '(none)'}\n"
            f"   Preview: {preview or '(empty)'}"
        )
    return "\n".join(lines)


def _calendar_context_from_result(result: Dict[str, Any], action_id: str) -> str:
    events = result.get("events") or []
    if not events:
        query = str(result.get("query") or "").strip()
        return f"Google Calendar plugin ({action_id}) found no events for query: {query}" if query else f"Google Calendar plugin ({action_id}) found no events in the selected window."
    lines = [f"Google Calendar plugin action: {action_id}", f"Window: {result.get('time_min')} to {result.get('time_max')}"]
    if result.get("query"):
        lines.append(f"Search terms: {result.get('query')}")
    lines.append("Matching events:")
    for idx, event in enumerate(events[:10], start=1):
        desc = " ".join(str(event.get("description") or "").split())[:400]
        lines.append(
            f"{idx}. Event: {event.get('summary') or '(untitled)'}\n"
            f"   Start: {event.get('start') or '(unknown)'}\n"
            f"   End: {event.get('end') or '(unknown)'}\n"
            f"   Location: {event.get('location') or '(none)'}\n"
            f"   Organizer: {event.get('organizer') or '(unknown)'}\n"
            f"   Description: {desc or '(empty)'}"
        )
    return "\n".join(lines)


def _timestamp_sort_key(value: str) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        if "," in raw and "+" in raw or "GMT" in raw:
            return email.utils.parsedate_to_datetime(raw).timestamp()
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _timeline_entries(plugin: str, result: Dict[str, Any]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    if plugin == "gmail":
        for msg in result.get("messages") or []:
            entries.append(
                {
                    "when": str(msg.get("date") or ""),
                    "source": "gmail",
                    "title": str(msg.get("subject") or "(no subject)"),
                    "person": str(msg.get("from") or ""),
                    "summary": " ".join(str(msg.get("snippet") or msg.get("body") or "").split())[:240],
                    "link": "",
                }
            )
    elif plugin == "google_docs":
        for doc in result.get("documents") or []:
            owner = ""
            owners = doc.get("owners") or []
            if owners and isinstance(owners[0], dict):
                owner = str(owners[0].get("displayName") or owners[0].get("emailAddress") or "")
            entries.append(
                {
                    "when": str(doc.get("modified_time") or ""),
                    "source": "docs",
                    "title": str(doc.get("name") or "(untitled)"),
                    "person": owner,
                    "summary": " ".join(str(doc.get("excerpt") or "").split())[:240],
                    "link": str(doc.get("web_view_link") or ""),
                }
            )
    elif plugin == "google_drive":
        for item in result.get("files") or []:
            entries.append(
                {
                    "when": str(item.get("modified_time") or ""),
                    "source": "drive",
                    "title": str(item.get("name") or "(untitled)"),
                    "person": "",
                    "summary": str(item.get("mime_type") or ""),
                    "link": str(item.get("web_view_link") or ""),
                }
            )
    elif plugin == "google_sheets":
        for item in result.get("sheets") or []:
            entries.append(
                {
                    "when": str(item.get("modified_time") or ""),
                    "source": "sheets",
                    "title": str(item.get("name") or "(untitled)"),
                    "person": "",
                    "summary": " ".join(str(item.get("preview") or "").split())[:240],
                    "link": str(item.get("web_view_link") or ""),
                }
            )
    elif plugin == "google_calendar":
        for event in result.get("events") or []:
            entries.append(
                {
                    "when": str(event.get("start") or ""),
                    "source": "calendar",
                    "title": str(event.get("summary") or "(untitled)"),
                    "person": str(event.get("organizer") or ""),
                    "summary": " ".join(str(event.get("description") or "").split())[:240],
                    "link": str(event.get("html_link") or ""),
                }
            )
    return entries


def _format_activity_timeline(entries: List[Dict[str, str]]) -> str:
    if not entries:
        return ""
    ordered = sorted(entries, key=lambda item: _timestamp_sort_key(item.get("when") or ""), reverse=True)
    lines = ["Unified Google activity timeline:"]
    for idx, item in enumerate(ordered[:20], start=1):
        lines.append(
            f"{idx}. [{item.get('source') or 'google'}] {item.get('when') or '(unknown time)'} :: {item.get('title') or '(untitled)'}\n"
            f"   Person: {item.get('person') or '(unknown)'}\n"
            f"   Summary: {item.get('summary') or '(empty)'}\n"
            f"   Link: {item.get('link') or '(none)'}"
        )
    return "\n".join(lines)


async def _run_plugin_action(plugin: str, action_id: str, user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    if plugin == "gmail":
        result = await _gmail_list_messages(user_text, zeitgeist_cfg)
        return _gmail_context_from_result(result, action_id), result
    if plugin == "google_docs":
        result = await _google_docs_search(user_text, zeitgeist_cfg)
        return _docs_context_from_result(result, action_id), result
    if plugin == "google_drive":
        result = await _google_drive_search(user_text, zeitgeist_cfg)
        return _drive_context_from_result(result, action_id), result
    if plugin == "google_sheets":
        result = await _google_sheets_search(user_text, zeitgeist_cfg)
        return _sheets_context_from_result(result, action_id), result
    if plugin == "google_calendar":
        result = await _google_calendar_search(user_text, zeitgeist_cfg)
        return _calendar_context_from_result(result, action_id), result
    return "", {}


async def build_plugin_context(user_text: str, zeitgeist_cfg: Optional[Dict[str, Any]]) -> str:
    matches = match_zeitgeist_actions(user_text, zeitgeist_cfg)
    if not matches:
        return ""
    blocks: List[str] = []
    timeline: List[Dict[str, str]] = []
    for match in matches:
        plugin = match.get("plugin") or ""
        action = match.get("action") or ""
        try:
            block, result = await _run_plugin_action(plugin, action, user_text, zeitgeist_cfg)
        except Exception as exc:
            block, result = f"{plugin} plugin ({action}) could not run: {exc}", {}
        if block:
            blocks.append(block)
        timeline.extend(_timeline_entries(plugin, result))
    if _is_activity_request(str(user_text or "").lower()):
        merged = _format_activity_timeline(timeline)
        if merged:
            blocks.append(merged)
    return "\n\n".join(b for b in blocks if b).strip()
