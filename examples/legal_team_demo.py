#!/usr/bin/env python3
"""
Runnable legal team demo using real provisioned campfires.

This example provisions a legal intake campfire plus specialist legal campers,
loads a real agreement PDF, and sends a normal user torch through the watch
workflow. Use --setup-only to verify provisioning, workflow registration, and
PDF extraction without requiring a live LLM backend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

from campfirevalley.llm_defaults import get_default_ollama_model
from campfirevalley.models import CampfireConfig, Torch
from campfirevalley.valley import Valley


logger = logging.getLogger(__name__)


DEFAULT_PDF = (
    Path(__file__).resolve().parents[1]
    / "inspiration"
    / "Software Development Agreement - Hibbert IT Solutions (1).pdf"
)


def _path_to_file_url(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    try:
        return Path(path_value).resolve().as_uri()
    except Exception:
        return None


def _extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise ValueError(f"No extractable text found in PDF: {pdf_path}")
    return text


def _choose_llm(provider: Optional[str], model: Optional[str], base_url: Optional[str]) -> Dict[str, str]:
    selected_provider = (provider or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if not selected_provider:
        selected_provider = "openrouter" if os.getenv("OPENROUTER_API_KEY") else "ollama"

    if selected_provider == "openrouter":
        selected_model = (model or os.getenv("OPENROUTER_MODEL") or "anthropic/claude-3.5-sonnet").strip()
        return {
            "provider": "openrouter",
            "model": selected_model,
            "base_url": "https://openrouter.ai/api/v1",
        }

    selected_model = (model or os.getenv("OLLAMA_MODEL") or get_default_ollama_model()).strip()
    selected_base_url = (base_url or os.getenv("OLLAMA_HOST") or "http://host.docker.internal:11434").strip()
    return {
        "provider": "ollama",
        "model": selected_model,
        "base_url": selected_base_url,
    }


def _make_llm_campfire_config(
    name: str,
    llm: Dict[str, str],
    system_prompt: str,
    description: str,
    watch_enabled: bool,
    watch_settings: Optional[Dict[str, Any]] = None,
    temperature: float = 0.2,
    max_tokens: int = 2400,
) -> CampfireConfig:
    watch_block: Dict[str, Any] = {"enabled": watch_enabled}
    if isinstance(watch_settings, dict):
        watch_block.update(watch_settings)
    return CampfireConfig(
        name=name,
        type="LLMCampfire",
        description=description,
        config={
            "llm": {
                "provider": llm["provider"],
                "model": llm["model"],
                "base_url": llm["base_url"],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            "prompts": {"system": system_prompt},
            "behavior": {
                "watch": watch_block
            },
        },
    )


def _legal_campfire_configs(llm: Dict[str, str], watch_max_retries: int) -> List[CampfireConfig]:
    return [
        _make_llm_campfire_config(
            name="Legal Team Auditor",
            llm=llm,
            description="Auditor that plans, verifies, and improves legal review workflows.",
            watch_enabled=False,
            temperature=0.05,
            max_tokens=1800,
            system_prompt=(
                "You are the Legal Team Auditor. You do not deliver the final legal answer directly. "
                "You orchestrate the legal workflow, decide which specialist campers should handle discover and execute, "
                "verify the quality of the result, and capture improvements for future runs. "
                "Prefer specialist non-auditor campers for discover and execute whenever they are available. "
                "When you are planning, produce compact, usable orchestration. "
                "When you are verifying, approve the result if it is client-ready and it covers: parties, payment/commercial terms, "
                "IP ownership, IR35 or contractor-status implications, key risks, and practical next steps. "
                "Do not reroute for minor stylistic issues. Reroute only if a material topic is missing, the result is unusable, or the answer ignores the document. "
                "If the source text appears truncated, treat an explicit recommendation for manual confirmation as sufficient rather than forcing another retry. "
                "When asked to verify, return only the requested JSON."
            ),
        ),
        _make_llm_campfire_config(
            name="Legal Team",
            llm=llm,
            description="Entry-point legal campfire for contract review requests.",
            watch_enabled=True,
            watch_settings={"max_retries": max(0, int(watch_max_retries))},
            temperature=0.1,
            max_tokens=1800,
            system_prompt=(
                "You are the legal intake campfire for contract and commercial document review. "
                "When watch orchestration is active, let the legal specialists research, analyze, and draft the final answer. "
                "Focus on concise, practical legal and commercial guidance."
            ),
        ),
        _make_llm_campfire_config(
            name="Contract Researcher",
            llm=llm,
            description="Specialist in extracting clauses, facts, obligations, and commercial terms from agreements.",
            watch_enabled=False,
            temperature=0.1,
            max_tokens=2200,
            system_prompt=(
                "You are a contract researcher. Extract the important factual and contractual details from agreements. "
                "Identify the parties, payment terms, IP provisions, confidentiality obligations, substitution rights, "
                "termination mechanics, and other key clauses. "
                "Return concise, reliable findings grounded in the provided text. "
                "If a section looks truncated or unreadable, say so explicitly instead of guessing."
            ),
        ),
        _make_llm_campfire_config(
            name="Contract Analyst",
            llm=llm,
            description="Specialist in legal and commercial contract risk analysis.",
            watch_enabled=False,
            temperature=0.15,
            max_tokens=2200,
            system_prompt=(
                "You are a contract analyst. Assess legal and commercial risk in agreements using the provided text and prior findings. "
                "Highlight unclear drafting, one-sided terms, payment risk, IP ownership implications, contractor-status issues, "
                "and any provisions that deserve negotiation or manual review. "
                "Prioritize the highest-value issues and explain why they matter in practice."
            ),
        ),
        _make_llm_campfire_config(
            name="Legal Reporter",
            llm=llm,
            description="Specialist in drafting final client-facing legal review summaries.",
            watch_enabled=False,
            temperature=0.05,
            max_tokens=2600,
            system_prompt=(
                "You are a legal reporter. Produce a concise client-facing legal review that synthesizes prior specialist outputs. "
                "Be practical, clearly structured, and explicit about the main findings, risks, and recommended next steps. "
                "Always include clear sections for: Executive Summary, Key Clauses, Main Risks, Recommended Next Steps, and Role Contributions. "
                "Treat the answer as ready to send to a client. Do not ask follow-up questions. Do not mention internal orchestration."
            ),
        ),
    ]


def _legal_workflow_steps() -> List[Dict[str, str]]:
    return [
        {
            "camper": "Contract Researcher",
            "task": (
                "Read the agreement text, extract the key commercial and legal clauses, and summarize the core facts, "
                "obligations, and any sections that appear truncated or need manual confirmation. "
                "At minimum cover: parties, scope, payment, confidentiality, IP, IR35/independent contractor terms, substitution, working arrangements, and termination."
            ),
        },
        {
            "camper": "Contract Analyst",
            "task": (
                "Using the agreement text and previous findings, identify the main legal and commercial risks, "
                "points that favor one party, and items worth renegotiating or validating manually. "
                "Focus on the most important practical issues rather than every possible observation."
            ),
        },
        {
            "camper": "Legal Reporter",
            "task": (
                "Prepare the final client-facing review. Explain the key findings, major risks, and practical next steps "
                "without exposing internal orchestration details. "
                "Use these exact section headings: Executive Summary, Key Clauses, Main Risks, Recommended Next Steps, Role Contributions. "
                "In Role Contributions, connect each prior specialist contribution to the final recommendations."
            ),
        },
    ]


class LegalTeamDemo:
    def __init__(
        self,
        pdf_path: Path,
        workspace: Path,
        manifest_path: Path,
        config_dir: Path,
        llm: Dict[str, str],
        watch_max_retries: int,
        setup_only: bool = False,
        show_watch: bool = False,
    ):
        self.pdf_path = pdf_path
        self.workspace = workspace
        self.manifest_path = manifest_path
        self.config_dir = config_dir
        self.llm = llm
        self.watch_max_retries = max(0, int(watch_max_retries))
        self.setup_only = setup_only
        self.show_watch = show_watch
        self.valley: Optional[Valley] = None

    def _prepare_workspace(self) -> Tuple[Path, Path]:
        self.workspace.mkdir(parents=True, exist_ok=True)
        workflow_dir = self.workspace / "configs"
        reports_dir = self.workspace / "reports"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        os.environ["CONFIG_DIR"] = str(workflow_dir)
        os.environ["REPORTS_DIR"] = str(reports_dir)
        return workflow_dir, reports_dir

    async def _start_valley(self) -> None:
        self.valley = Valley(
            name="legal-demo",
            manifest_path=str(self.manifest_path),
            mcp_broker="",
            config_dir=str(self.config_dir),
        )
        await self.valley.start()

    async def _provision_campfires(self) -> None:
        assert self.valley is not None
        for campfire_config in _legal_campfire_configs(self.llm, self.watch_max_retries):
            if campfire_config.name in self.valley.campfires:
                continue
            success = await self.valley.provision_campfire(campfire_config)
            if not success:
                raise RuntimeError(f"Failed to provision campfire '{campfire_config.name}'.")
        if not self.valley.set_workflow("Legal Team", _legal_workflow_steps()):
            raise RuntimeError("Failed to register Legal Team workflow.")

    def _build_request_torch(self, agreement_text: str) -> Torch:
        return Torch(
            claim="voice_text",
            source_campfire="voice",
            channel="voice",
            sender_valley="demo-user",
            target_address="legal-demo:Legal Team",
            data={
                "text": (
                    "Review this software development agreement. Research the important clauses, decide how to approach the review, "
                    "and return a concise client-facing legal assessment with the main risks and recommended next steps. "
                    "The final answer must be ready to send to a client and should cover parties, commercial terms, IP, IR35/contractor status, key risks, and next steps.\n\n"
                    f"Source document: {self.pdf_path}\n\n"
                    f"Agreement text:\n{agreement_text}"
                )
            },
            attachments=[str(self.pdf_path)],
            signature="demo_placeholder",
        )

    async def run(self) -> Dict[str, Any]:
        _, reports_dir = self._prepare_workspace()
        agreement_text = _extract_pdf_text(self.pdf_path)
        await self._start_valley()
        assert self.valley is not None

        try:
            await self._provision_campfires()
            request_torch = self._build_request_torch(agreement_text)

            if self.setup_only:
                return {
                    "ok": True,
                    "mode": "setup_only",
                    "pdf_path": str(self.pdf_path),
                    "pdf_characters": len(agreement_text),
                    "campfires": list(self.valley.campfires.keys()),
                    "workflow": self.valley.get_workflow("Legal Team") or {},
                    "reports_dir": str(reports_dir),
                    "reports_dir_url": _path_to_file_url(str(reports_dir)),
                }

            response = await self.valley.process_torch(request_torch)
            if response is None or not isinstance(getattr(response, "data", None), dict):
                raise RuntimeError("The legal team demo returned no response.")

            result = {
                "ok": bool(response.data.get("ok", True)),
                "campfire": response.data.get("campfire", "Legal Team"),
                "text": response.data.get("text", ""),
                "watch": response.data.get("watch", {}),
                "learning": dict(self.valley._watch_learnings.get("Legal Team") or {}),
                "pdf_path": str(self.pdf_path),
                "pdf_characters": len(agreement_text),
                "llm": self.llm,
            }
            out_path = self.workspace / "legal_team_demo_result.json"
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
            result["result_path"] = str(out_path)
            result["result_url"] = _path_to_file_url(str(out_path))
            report_path = str((result.get("watch") or {}).get("report_path") or "")
            result["watch_report_url"] = _path_to_file_url(report_path)
            return result
        finally:
            await self.valley.stop()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CampfireValley legal team demo with a real agreement PDF.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Path to the agreement PDF to review.")
    parser.add_argument(
        "--workspace",
        default=str(Path("demo_workspace") / "legal_team"),
        help="Workspace directory for workflow and report artifacts.",
    )
    parser.add_argument("--manifest", default="manifest.yaml", help="Valley manifest path.")
    parser.add_argument("--config-dir", default="config", help="CampfireValley config directory.")
    parser.add_argument("--provider", default=None, help="LLM provider override, e.g. ollama or openrouter.")
    parser.add_argument("--model", default=None, help="LLM model override.")
    parser.add_argument("--base-url", default=None, help="Optional LLM base URL override.")
    parser.add_argument(
        "--watch-max-retries",
        type=int,
        default=1,
        help="Maximum watch reruns after verifier rejection during the demo.",
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Provision the legal team, extract the PDF, and register the workflow without sending the final request.",
    )
    parser.add_argument(
        "--show-watch",
        action="store_true",
        help="Print the watch history JSON after a full run.",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    demo = LegalTeamDemo(
        pdf_path=pdf_path,
        workspace=Path(args.workspace).resolve(),
        manifest_path=Path(args.manifest).resolve(),
        config_dir=Path(args.config_dir).resolve(),
        llm=_choose_llm(args.provider, args.model, args.base_url),
        watch_max_retries=args.watch_max_retries,
        setup_only=bool(args.setup_only),
        show_watch=bool(args.show_watch),
    )
    result = await demo.run()

    print(f"Mode: {result.get('mode', 'full_run')}")
    print(f"PDF: {result.get('pdf_path')}")
    print(f"PDF characters: {result.get('pdf_characters')}")
    print(f"LLM provider: {demo.llm['provider']}")
    print(f"LLM model: {demo.llm['model']}")

    if args.setup_only:
        print("Provisioned campfires:")
        for name in result.get("campfires", []):
            print(f"- {name}")
        print(f"Reports dir: {result.get('reports_dir')}")
        if result.get("reports_dir_url"):
            print(f"Reports dir link: {result['reports_dir_url']}")
        return 0

    print("\nFinal response:\n")
    print(result.get("text", ""))
    watch = result.get("watch") or {}
    if watch.get("report_path"):
        print(f"\nWatch report: {watch['report_path']}")
    if result.get("watch_report_url"):
        print(f"Watch report link: {result['watch_report_url']}")
    learning = result.get("learning") or {}
    if learning:
        print(
            "Learning summary: "
            f"runs={learning.get('runs')}, passes={learning.get('passes')}, "
            f"failures={learning.get('failures')}, total_retries={learning.get('total_retries')}"
        )
        averages = learning.get("average_effectiveness") or {}
        if averages:
            print(
                "Average effectiveness: "
                f"task_fit={averages.get('task_fit')}, quality={averages.get('quality')}, "
                f"efficiency={averages.get('efficiency')}, coordination={averages.get('coordination')}"
            )
    if result.get("result_path"):
        print(f"Saved result: {result['result_path']}")
    if result.get("result_url"):
        print(f"Saved result link: {result['result_url']}")
    if args.show_watch and watch:
        print("\nWatch payload:\n")
        print(json.dumps(watch, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
