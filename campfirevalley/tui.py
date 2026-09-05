"""CampfireValley TUI - the valley front door.

A terminal UI that subscribes to a valley event stream (the dev-event SSE
endpoint shipped with the event bus) and renders it as live panels: an
activity feed, the current torch/task, and a chat strip where the valley
leader speaks. The leader is whoever the valley says it is (config-assigned
role - Andrew for an Andrew-class valley, the Timberwolf for a steward-run
product valley).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Optional

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

EVENT_URL = "{base}/events"

LEADER_TYPES = {"leader_say", "agent_say", "steward_patrol"}
ACTIVITY_MAX = 200


class TuiState:
    """Rolling state the panels render from."""

    def __init__(self, leader_name: str = "the valley") -> None:
        self.activity = []  # (time, text)
        self.current_torch = None
        self.leader_lines = []
        self.leader_name = leader_name
        self.leader_introduced = False

    def observe(self, ev: dict) -> None:
        etype = ev.get("type") or "agent_say"
        ts = (ev.get("ts") or "")[11:19] or "--:--:--"
        campfire = ev.get("campfire") or ""
        text = (ev.get("text") or "").strip()
        if not text:
            return
        if etype == "torch_received":
            self.current_torch = str(ev.get("torch_id") or "torch") + " - " + text[:80]
        elif etype == "torch_completed":
            self.current_torch = None
        if etype in LEADER_TYPES:
            self.leader_lines.append(text)
            self.leader_lines = self.leader_lines[-8:]
        label = campfire or etype
        self.activity.append((ts, "[" + label + "] " + text))
        self.activity = self.activity[-ACTIVITY_MAX:]


def _render(state: TuiState):
    feed = Text()
    if not state.activity:
        feed.append("(no events yet - waiting for the valley to speak)\n", style="dim")
    for ts, line in state.activity[-12:]:
        feed.append(ts + "  ")
        feed.append(line + "\n")
    activity_panel = Panel(feed, title="Activity", border_style="dim")

    task_text = Text(state.current_torch or "(idle - no torch in flight)",
                     style="cyan" if state.current_torch else "dim")
    task_panel = Panel(task_text, title="Current work", border_style="dim")

    chat = Text()
    if not state.leader_introduced:
        intro = ("Good evening. I am " + state.leader_name +
                 " — leader of this valley. I will speak here as the work happens.")
        chat.append(state.leader_name + ": " + intro + "\n", style="bold magenta")
    for line in state.leader_lines[-5:]:
        chat.append(state.leader_name + ": " + line + "\n", style="bold magenta")
    if not state.leader_lines:
        chat.append("(the leader will speak here)\n", style="dim")
    chat_panel = Panel(chat, title="By the fire", border_style="dim")

    return Group(activity_panel, task_panel, chat_panel)


async def run_tui(base_url: str, folder: str = "") -> None:
    """Consume the valley SSE stream and render live panels."""
    console = Console()
    state = TuiState()
    state.leader_name = await _fetch_leader_name(base_url) or state.leader_name
    url = EVENT_URL.format(base=base_url.rstrip("/"))
    console.print("[bold]CampfireValley TUI[/] - listening to " + url)
    if folder:
        console.print("[bold green]Bound to folder:[/] " + folder + "  (type a request + Enter to send it as a torch)")
    input_queue: asyncio.Queue = asyncio.Queue()

    import threading

    def _reader() -> None:
        while True:
            try:
                line = input()
                input_queue.put_nowait(line)
            except EOFError:
                return

    threading.Thread(target=_reader, daemon=True).start()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with Live(_render(state), refresh_per_second=4, screen=False) as live:
                    async for line in resp.aiter_lines():
                        # drain any typed requests without stalling the stream
                        while not input_queue.empty():
                            request = input_queue.get_nowait()
                            if folder and request.strip():
                                status = await _send_folder_torch(base_url, folder, request)
                                console.print("[dim]" + status + "[/]")
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        try:
                            ev = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        state.observe(ev)
                        live.update(_render(state))
    except KeyboardInterrupt:
        console.print("\n[dim]TUI closed - the valley carries on.[/]")
    except httpx.HTTPError as e:
        console.print("[red]Could not reach the valley event stream at " + url + ": " + str(e) + "[/]")


async def _send_folder_torch(base_url: str, folder: str, request: str) -> str:
    """Send a folder torch: typed request + bound folder context. Returns a status line."""
    import os

    body = {
        "objective": request.strip()[:400],
        "folder": folder,
        "context": "bound folder: " + folder + " (cwd files visible to the campfire)",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(base_url.rstrip("/") + "/torchs", json=body)
            if resp.status_code == 200:
                torch_id = (resp.json() or {}).get("torch_id", "")
                return "torch sent - " + str(torch_id)
            return "send failed (" + str(resp.status_code) + ") - " + resp.text[:120]
    except Exception as e:
        return "send failed: " + str(e)


async def _fetch_leader_name(base_url: str) -> Optional[str]:
    """Ask the valley who fronts (leader role). Falls back to None silently."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(base_url.rstrip("/") + "/events/leader")
            if resp.status_code == 200:
                name = (resp.json() or {}).get("leader")
                return str(name) if name else None
    except Exception:
        return None
    return None


def register(parser: argparse.ArgumentParser, subparsers) -> None:
    """Register the tui subcommand on the CampfireValley CLI."""
    tui_parser = subparsers.add_parser(
        "tui",
        help="Open the valley TUI (live event stream panels)",
    )
    tui_parser.add_argument(
        "--url",
        default="http://localhost:8020",
        help="Valley events endpoint base (default: http://localhost:8020)",
    )
    tui_parser.add_argument(
        "--folder",
        default="",
        help="Bind a local project folder - typed requests are sent as folder torches",
    )
    tui_parser.set_defaults(func=lambda a: asyncio.run(run_tui(a.url, folder=a.folder)))