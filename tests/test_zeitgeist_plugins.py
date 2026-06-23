import json

import campfirevalley.zeitgeist_plugins as zeitgeist_plugins


def test_describe_zeitgeist_capabilities_includes_gmail_actions():
    cfg = {
        "enabled": True,
        "web_search": True,
        "plugins": {
            "gmail": {
                "enabled": True,
            },
            "google_docs": {
                "enabled": True,
            },
            "google_calendar": {
                "enabled": True,
            },
            "google_drive": {
                "enabled": True,
            },
            "google_sheets": {
                "enabled": True,
            }
        },
    }

    caps = zeitgeist_plugins.describe_zeitgeist_capabilities(cfg)

    assert "web_search" in caps
    assert any(cap.startswith("gmail[") for cap in caps)
    assert any("check_email" in cap for cap in caps)
    assert any(cap.startswith("google_docs[") for cap in caps)
    assert any(cap.startswith("google_calendar[") for cap in caps)
    assert any(cap.startswith("google_drive[") for cap in caps)
    assert any(cap.startswith("google_sheets[") for cap in caps)


def test_match_zeitgeist_actions_detects_job_email_request():
    cfg = {
        "enabled": True,
        "plugins": {
            "gmail": {
                "enabled": True,
            }
        },
    }

    matches = zeitgeist_plugins.match_zeitgeist_actions(
        "Check my emails for recruiter messages about Python backend jobs",
        cfg,
    )

    assert {"plugin": "gmail", "action": "job_email_scan"} in matches


def test_build_gmail_query_uses_request_hints():
    cfg = {
        "enabled": True,
        "plugins": {
            "gmail": {
                "enabled": True,
                "default_query": "in:inbox newer_than:14d",
            }
        },
    }

    query = zeitgeist_plugins.build_gmail_query(
        "Check my unread emails for python backend recruiter jobs from linkedin",
        cfg,
    )

    assert "in:inbox" in query
    assert "is:unread" in query
    assert "from:linkedin" in query
    assert "python" in query
    assert "backend" in query


def test_build_gmail_query_uses_saved_filters():
    cfg = {
        "enabled": True,
        "filters": {
            "subject": "contract review",
            "person": "lawyer@example.com",
            "date_range": "last_30d",
        },
        "plugins": {
            "gmail": {
                "enabled": True,
            }
        },
    }

    query = zeitgeist_plugins.build_gmail_query("Check my emails", cfg)

    assert "from:lawyer@example.com" in query
    assert "subject:(contract review)" in query
    assert "after:" in query


def test_match_zeitgeist_actions_detects_docs_calendar_and_activity_requests():
    cfg = {
        "enabled": True,
        "plugins": {
            "gmail": {"enabled": True},
            "google_docs": {"enabled": True},
            "google_calendar": {"enabled": True},
            "google_drive": {"enabled": True},
            "google_sheets": {"enabled": True},
        },
    }

    matches = zeitgeist_plugins.match_zeitgeist_actions(
        "What has my activity been recently across docs and calendar for the API migration?",
        cfg,
    )

    assert {"plugin": "gmail", "action": "recent_email_activity"} in matches
    assert {"plugin": "google_docs", "action": "recent_documents"} in matches
    assert {"plugin": "google_calendar", "action": "calendar_activity"} in matches
    assert {"plugin": "google_drive", "action": "recent_drive_activity"} in matches
    assert {"plugin": "google_sheets", "action": "recent_sheets_activity"} in matches


def test_match_zeitgeist_actions_detects_drive_and_sheets_requests():
    cfg = {
        "enabled": True,
        "plugins": {
            "google_drive": {"enabled": True},
            "google_sheets": {"enabled": True},
        },
    }

    matches = zeitgeist_plugins.match_zeitgeist_actions(
        "Search drive files and spreadsheets for onboarding budget details",
        cfg,
    )

    assert {"plugin": "google_drive", "action": "search_drive"} in matches
    assert {"plugin": "google_sheets", "action": "search_sheets"} in matches


def test_google_provider_status_reports_shared_token_for_docs_and_calendar(tmp_path):
    creds = tmp_path / "gog_credentials.json"
    token = tmp_path / "gmail_token.json"
    creds.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "demo-client",
                    "client_secret": "demo-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    token.write_text(
        json.dumps(
            {
                "access_token": "abc",
                "refresh_token": "def",
                "expires_at": 9999999999,
                "scope": " ".join(
                    [
                        "https://www.googleapis.com/auth/gmail.readonly",
                        "https://www.googleapis.com/auth/drive.readonly",
                        "https://www.googleapis.com/auth/documents.readonly",
                        "https://www.googleapis.com/auth/calendar.readonly",
                    ]
                ),
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "enabled": True,
        "plugins": {
            "google_docs": {
                "enabled": True,
                "credentials_path": str(creds),
                "token_path": str(token),
            },
            "google_calendar": {
                "enabled": True,
                "credentials_path": str(creds),
                "token_path": str(token),
            },
        },
    }

    docs_status = zeitgeist_plugins.google_docs_plugin_status(cfg)
    calendar_status = zeitgeist_plugins.google_calendar_plugin_status(cfg)

    assert docs_status["authorized"] is True
    assert docs_status["scopes_ready"] is True
    assert calendar_status["authorized"] is True
    assert calendar_status["scopes_ready"] is True


def test_google_provider_status_reports_shared_token_for_drive_and_sheets(tmp_path):
    creds = tmp_path / "gog_credentials.json"
    token = tmp_path / "gmail_token.json"
    creds.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "demo-client",
                    "client_secret": "demo-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    token.write_text(
        json.dumps(
            {
                "access_token": "abc",
                "refresh_token": "def",
                "expires_at": 9999999999,
                "scope": " ".join(
                    [
                        "https://www.googleapis.com/auth/drive.readonly",
                        "https://www.googleapis.com/auth/spreadsheets.readonly",
                    ]
                ),
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "enabled": True,
        "plugins": {
            "google_drive": {
                "enabled": True,
                "credentials_path": str(creds),
                "token_path": str(token),
            },
            "google_sheets": {
                "enabled": True,
                "credentials_path": str(creds),
                "token_path": str(token),
            },
        },
    }

    drive_status = zeitgeist_plugins.google_drive_plugin_status(cfg)
    sheets_status = zeitgeist_plugins.google_sheets_plugin_status(cfg)

    assert drive_status["authorized"] is True
    assert drive_status["scopes_ready"] is True
    assert sheets_status["authorized"] is True
    assert sheets_status["scopes_ready"] is True


def test_format_activity_timeline_merges_sources():
    timeline = zeitgeist_plugins._format_activity_timeline(
        [
            {"when": "2026-05-20T10:00:00Z", "source": "docs", "title": "API Plan", "person": "Mike", "summary": "Updated migration notes", "link": "doc-link"},
            {"when": "Wed, 21 May 2026 09:00:00 +0000", "source": "gmail", "title": "Recruiter Follow-up", "person": "recruiter@example.com", "summary": "Interview discussion", "link": ""},
        ]
    )

    assert "Unified Google activity timeline:" in timeline
    assert "[gmail]" in timeline
    assert "[docs]" in timeline


def test_gmail_plugin_status_reports_credentials_and_token(tmp_path):
    creds = tmp_path / "gog_credentials.json"
    token = tmp_path / "gmail_token.json"
    creds.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "demo-client",
                    "client_secret": "demo-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    token.write_text(
        json.dumps(
            {
                "access_token": "abc",
                "refresh_token": "def",
                "expires_at": 9999999999,
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "enabled": True,
        "plugins": {
            "gmail": {
                "enabled": True,
                "credentials_path": str(creds),
                "token_path": str(token),
            }
        },
    }

    status = zeitgeist_plugins.gmail_plugin_status(cfg)

    assert status["enabled"] is True
    assert status["credentials_present"] is True
    assert status["authorized"] is True
    assert status["token_present"] is True
