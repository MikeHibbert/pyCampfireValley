"""CampfireValley kindling dojo - forge, test, and take away a personality.

A chopped-down kindling system for people who want a working AI personality
without building the whole valley:

    campfirevalley dojo generate "a patient code reviewer who explains
    every choice"          ->  a kindling file (system prompt + user template)
    campfirevalley dojo test kindling.json "review this function"  ->  a live reply
    campfirevalley dojo show kindling.json      ->  the copy-paste block

The dojo is deterministic except for the one LLM call that generates the
prompt pair. Everything else (parsing, templating, copy-block formatting,
save/load) is mechanical.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Callable, Optional

GEN_MARKER_SYSTEM = "SYSTEM_PROMPT"
GEN_MARKER_USER = "USER_TEMPLATE"

_GEN_INSTRUCTIONS = (
    "You will be given a brief description of an AI personality. "
    "Reply with EXACTLY two fenced code blocks and nothing else.\n"
    "First block, tagged " + GEN_MARKER_SYSTEM + ": the complete system prompt "
    "for this personality (identity, voice, standards, boundaries). "
    "Second block, tagged " + GEN_MARKER_USER + ": a user-message template with "
    "the single placeholder {request} where the user's actual request goes.\n"
    "No prose before, between, or after the blocks.\n\n"
    "Personality brief: {brief}"
)


@dataclass
class Kindling:
    name: str
    description: str
    system_prompt: str
    user_template: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Kindling":
        return cls(
            name=str(data.get("name") or "kindling"),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            user_template=str(data.get("user_template") or "{request}"),
        )


def _parse_prompt_pair(raw: str) -> tuple[str, str]:
    """Extract the tagged system/user pair from a (possibly messy) reply.

    Tolerates prose around the blocks and both ```tag and ``` tag fences.
    Raises ValueError with a human-readable reason when the pair is missing.
    """
    text = str(raw or "")
    pairs: dict[str, str] = {}
    for marker in (GEN_MARKER_SYSTEM, GEN_MARKER_USER):
        # ```SYSTEM_PROMPT ... ``` or ``` SYSTEM_PROMPT ... ```
        pattern = re.compile(
            r"```" + marker + r"\s*\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            pairs[marker] = match.group(1).strip()
    if GEN_MARKER_SYSTEM not in pairs or GEN_MARKER_USER not in pairs:
        raise ValueError(
            "The reply did not contain the two tagged blocks ("
            + GEN_MARKER_SYSTEM + " and " + GEN_MARKER_USER
            + "). Retry the generation."
        )
    return pairs[GEN_MARKER_SYSTEM], pairs[GEN_MARKER_USER]


def _render_user(template: str, request: str) -> str:
    rendered = str(template or "{request}")
    if "{request}" not in rendered:
        rendered = rendered + "\n\n{request}"
    return rendered.replace("{request}", str(request or ""))


def format_copy(kindling: Kindling) -> str:
    """The take-away block: deterministic, fenced, no commentary."""
    return (
        "# kindling: " + kindling.name + "\n"
        + "SYSTEM PROMPT\n"
        + "```\n" + kindling.system_prompt + "\n```\n\n"
        + "USER TEMPLATE (the {request} placeholder receives the user's message)\n"
        + "```\n" + kindling.user_template + "\n```\n"
    )


class DojoForge:
    """Generate and test kindlings. The LLM is an injected callable.

    llm signature: llm(system: str, user: str) -> str. Use the module-level
    default_llm() for a working default (env-driven Ollama/cloud), or inject
    a fake in tests.
    """

    def __init__(self, llm: Optional[Callable[[str, str], str]] = None):
        self._llm = llm

    def generate(self, description: str, name: str = "") -> Kindling:
        brief = str(description or "").strip()
        if not brief:
            raise ValueError("Describe the personality in plain words first.")
        raw = self._call_llm(
            "You forge AI personalities for a kindling dojo.",
            _GEN_INSTRUCTIONS.replace('{brief}', brief),
        )
        system_prompt, user_template = _parse_prompt_pair(raw)
        return Kindling(
            name=str(name or brief.split(".")[0])[:40].strip() or "kindling",
            description=brief,
            system_prompt=system_prompt,
            user_template=user_template,
        )

    def test(self, kindling: Kindling, sample_request: str) -> str:
        request = str(sample_request or "").strip()
        if not request:
            raise ValueError("Give the kindling something to answer.")
        user_message = _render_user(kindling.user_template, request)
        return self._call_llm(kindling.system_prompt, user_message)

    def _call_llm(self, system: str, user_message: str) -> str:
        if self._llm is not None:
            return self._llm(system, user_message)
        llm = default_llm()
        if llm is None:
            raise ValueError(
                "No LLM available. Set OLLAMA_BASE_URL (local) or "
                "OLLAMA_CLOUD_BASE_URL + OLLAMA_API_KEY (cloud), or pass llm=."
            )
        return llm(system, user_message)


def default_llm() -> Optional[Callable[[str, str], str]]:
    """Env-driven LLM callable: local Ollama or Ollama Cloud (bearer).

    Local: OLLAMA_BASE_URL + OLLAMA_MODEL (e.g. http://localhost:11434).
    Cloud: OLLAMA_CLOUD_BASE_URL + OLLAMA_API_KEY (bearer, openai-style chat).
    """
    import httpx

    cloud_base = os.getenv("OLLAMA_CLOUD_BASE_URL", "").strip()
    if cloud_base:
        api_key = os.getenv("OLLAMA_API_KEY", "").strip()
        model = os.getenv("OLLAMA_MODEL", "gemma3:latest").strip()
        url = cloud_base.rstrip("/") + "/v1/chat/completions"

        def cloud_call(system: str, user_message: str) -> str:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
            }
            headers = {"Authorization": "Bearer " + api_key} if api_key else {}
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")

        return cloud_call

    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    model = os.getenv("OLLAMA_MODEL", "").strip()
    url = base.rstrip("/") + "/api/chat"

    def local_call(system: str, user_message: str) -> str:
        payload = {
            "model": model or "llama3.2",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return str(data.get("message", {}).get("content") or "")

    return local_call


def save(kindling: Kindling, out_path: str) -> str:
    path = str(out_path or "").strip()
    if not path:
        raise ValueError("Give the kindling a file to live in (--out).")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kindling.to_dict(), fh, indent=2, ensure_ascii=False)
    return path


def load(path: str) -> Kindling:
    with open(path, "r", encoding="utf-8") as fh:
        return Kindling.from_dict(json.load(fh))

def _cli_dojo(args) -> None:
    """CLI entry for the dojo subcommands (generate / test / show)."""
    import asyncio
    from rich.console import Console

    console = Console()
    cmd = getattr(args, "dojo_cmd", "")
    if cmd == "generate":
        forge = DojoForge()
        k = forge.generate(args.description, name=args.name or None)
        out = args.out or (k.name + ".kindling.json")
        path = save(k, out)
        console.print("[bold]Kindling forged:[/] " + k.name + " -> " + str(path))
        console.print(format_copy(k))
    elif cmd == "test":
        k = load(args.kindling)
        forge = DojoForge()
        reply = forge.test(k, args.request)
        console.print("[bold]System:[/] " + k.system_prompt[:120])
        console.print("[bold]User:[/] " + _render_user(k.user_template, args.request)[:200])
        console.print("[bold]Reply:[/]")
        console.print(reply)
    elif cmd == "show":
        k = load(args.kindling)
        console.print(format_copy(k))
    else:
        console.print("Specify a dojo action: generate|test|show")
