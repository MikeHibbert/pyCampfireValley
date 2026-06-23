from functools import lru_cache
from pathlib import Path
import types

import pytest
from pypdf import PdfReader

from campfirevalley.models import Torch
from campfirevalley.valley import Valley


class _DummyMonitoring:
    async def log(self, *args, **kwargs):
        return None


@lru_cache(maxsize=1)
def _load_agreement_pdf() -> tuple[Path, str]:
    pdf_path = (
        Path(__file__).resolve().parents[1]
        / "inspiration"
        / "Software Development Agreement - Hibbert IT Solutions (1).pdf"
    )
    reader = PdfReader(str(pdf_path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise AssertionError("Expected extractable text from the agreement PDF.")
    return pdf_path, text


class _PassiveCampfire:
    def __init__(self, config=None):
        self.config = config or {}
        self.calls = []

    async def process_torch(self, torch):
        self.calls.append(torch)
        return types.SimpleNamespace(data={"text": "passive"})


class _LegalAuditorCampfire:
    def __init__(self):
        self.calls = []
        self.verify_calls = 0
        self.improve_calls = 0
        self.plan_json = (
            '{"rounds": {'
            '"discover": {"goal": "Extract the commercial and contractor terms from the agreement.", "campers": ["Contract Researcher"]}, '
            '"plan": {"goal": "Decide how to review the agreement.", "campers": ["Legal Team Auditor"]}, '
            '"execute": {"goal": "Produce a client-facing legal review.", "campers": ["Contract Analyst", "Legal Reporter"], '
            '"steps": ['
            '{"camper": "Contract Analyst", "task": "Review the agreement text, identify the key legal/commercial clauses, and call out the main risks or negotiation points."}, '
            '{"camper": "Legal Reporter", "task": "Prepare the final client-facing review using the input and the previous step outputs."}'
            ']}, '
            '"verify": {"goal": "Check that the legal review is ready to send.", "campers": ["Legal Team Auditor"], '
            '"pass_criteria": ["Identifies the parties and payment terms", "Explains the IP and IR35 clauses", "Highlights negotiation risks and next steps"]}, '
            '"improve": {"goal": "Capture learning for future contract reviews.", "campers": ["Legal Team Auditor"], '
            '"focus_areas": ["camper selection", "task wording", "legal issue coverage"]}'
            '}, "failure_policy": {"default_reroute_to": "execute", "rules": {"missing_context": "discover", "bad_plan": "plan", "weak_result": "execute"}}}'
        )

    async def process_torch(self, torch):
        self.calls.append(torch)
        claim = getattr(torch, "claim", "")
        text = ((getattr(torch, "data", None) or {}).get("text") or "")
        if claim == "watch_plan":
            if "Available campers:" in text:
                assert "Contract Researcher" in text
                assert "Contract Analyst" in text
                assert "Legal Reporter" in text
            return types.SimpleNamespace(data={"text": self.plan_json})
        if claim == "watch_verify":
            self.verify_calls += 1
            assert "VoxFlo AI Ltd" in text
            assert "Hibbert IT Solutions Limited" in text
            assert "Role Contributions" in text
            return types.SimpleNamespace(
                data={
                    "text": '{"pass": true, "reason": "pass", "feedback": "", "reroute_to": "execute"}'
                }
            )
        if claim == "watch_improve":
            self.improve_calls += 1
            return types.SimpleNamespace(
                data={
                    "text": (
                        '{"outcome_summary": "The legal review completed successfully.", '
                        '"effectiveness": {"task_fit": 5, "quality": 4, "efficiency": 4, "coordination": 4}, '
                        '"strengths": ["The specialist campers covered the commercial and IR35 terms."], '
                        '"weaknesses": ["Termination wording should still be validated manually."], '
                        '"recommendations": ["Keep the contract researcher in discover.", "Keep the reporter as the final step."], '
                        '"camper_feedback": [{"campfire": "Contract Researcher", "rating": "helpful", "notes": "Extracted the main clauses clearly."}], '
                        '"learned_policy": {"prefer_campers": ["Contract Researcher", "Contract Analyst", "Legal Reporter"]}}'
                    )
                }
            )
        return types.SimpleNamespace(data={"text": self.plan_json})


class _ContractResearcherCampfire:
    def __init__(self):
        self.calls = []

    async def process_torch(self, torch):
        self.calls.append(torch)
        prompt = ((getattr(torch, "data", None) or {}).get("text") or "")
        assert "Software Development Agreement" in prompt
        assert "VoxFlo AI Ltd" in prompt
        assert "Hibbert IT Solutions Limited" in prompt
        return types.SimpleNamespace(
            data={
                "text": (
                    "Agreement facts:\n"
                    "- Client: VoxFlo AI Ltd.\n"
                    "- Supplier: Hibbert IT Solutions Limited.\n"
                    "- Monthly rate: GBP 3,750, payable within 30 days of invoice.\n"
                    "- IP clause: deliverables vest in the Client upon creation.\n"
                    "- IR35 clause: supplier acts as an independent contractor and indemnifies the client for misclassification.\n"
                    "- Substitution: supplier may appoint a suitably qualified substitute at its own expense, subject to reasonable approval.\n"
                )
            }
        )


class _ContractAnalystCampfire:
    def __init__(self):
        self.calls = []

    async def process_torch(self, torch):
        self.calls.append(torch)
        prompt = ((getattr(torch, "data", None) or {}).get("text") or "")
        assert "Software Development Agreement" in prompt
        assert "Agreement facts:" in prompt
        return types.SimpleNamespace(
            data={
                "text": (
                    "Legal analysis:\n"
                    "- The agreement identifies VoxFlo AI Ltd as client and Hibbert IT Solutions Limited as supplier.\n"
                    '- "Payment shall be made within 30 days of invoice submission." This is commercially clear but could create cash-flow lag for the supplier.\n'
                    '- "All intellectual property rights in the Deliverables shall vest in the Client upon creation." This strongly favors the client and should be checked against any unpaid work risk.\n'
                    "- The IR35 wording pushes tax-status responsibility and indemnity risk to the supplier.\n"
                    "- The substitution clause supports contractor status, but practical approval and onboarding behavior should match the papered terms.\n"
                    "- The termination section should be manually checked in the source PDF because the extracted text is truncated near that heading.\n"
                )
            }
        )


class _LegalReporterCampfire:
    def __init__(self):
        self.calls = []

    async def process_torch(self, torch):
        self.calls.append(torch)
        prompt = ((getattr(torch, "data", None) or {}).get("text") or "")
        assert "Legal analysis:" in prompt
        assert "Agreement facts:" in prompt
        return types.SimpleNamespace(
            data={
                "text": (
                    "## Final Report\n"
                    "This agreement is a contractor-style software development agreement between VoxFlo AI Ltd and Hibbert IT Solutions Limited. "
                    "It clearly covers the service scope, sets payment at GBP 3,750 per month with 30-day invoice terms, and gives the client immediate ownership of deliverables.\n\n"
                    "Key findings:\n"
                    "- The commercial terms are straightforward, but a 30-day payment window may be longer than the supplier wants.\n"
                    "- The intellectual property clause is very client-favorable because ownership vests on creation rather than on payment.\n"
                    "- The IR35 and substitution clauses are drafted to support independent-contractor treatment, but day-to-day working practices must match that wording.\n"
                    "- The extracted text cuts off near the termination heading, so termination notice and exit obligations should be checked in the signed PDF before relying on the agreement.\n\n"
                    "Recommended next steps:\n"
                    "- Confirm the missing termination wording directly in the PDF.\n"
                    "- Decide whether IP transfer should remain on creation or move to payment/acceptance.\n"
                    "- Confirm whether the supplier is comfortable with the IR35 indemnity wording.\n\n"
                    "## Role Contributions\n"
                    '- Step 1 (Contract Analyst): "Payment shall be made within 30 days" - this established the main cash-flow point to raise in the final review.\n'
                )
            }
        )


@pytest.mark.asyncio
async def test_user_can_send_agreement_pdf_to_legal_campfire_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    pdf_path, agreement_text = _load_agreement_pdf()

    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.monitoring = _DummyMonitoring()
    valley._watch_runs = {}
    valley._watch_learnings = {}
    valley._workflow_cache = {}

    legal_team = _PassiveCampfire(config={})
    auditor = _LegalAuditorCampfire()
    researcher = _ContractResearcherCampfire()
    analyst = _ContractAnalystCampfire()
    reporter = _LegalReporterCampfire()

    valley.campfires = {
        "Legal Team": legal_team,
        "Legal Team Auditor": auditor,
        "Contract Researcher": researcher,
        "Contract Analyst": analyst,
        "Legal Reporter": reporter,
    }
    valley.get_workflow = lambda name: {
        "steps": [
            {"camper": "Contract Researcher", "task": "Extract the main clauses from the agreement."},
            {"camper": "Contract Analyst", "task": "Assess legal and commercial risk."},
            {"camper": "Legal Reporter", "task": "Draft the final client-facing review."},
        ]
    }

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Legal Team",
        data={
            "text": (
                "Review this software development agreement, research the important clauses, decide how to approach the legal review, "
                "and return a concise client-facing assessment with the main risks and next steps.\n\n"
                f"Source document: {pdf_path}\n\n"
                f"Agreement text:\n{agreement_text}"
            )
        },
        attachments=[str(pdf_path)],
        signature="voice_placeholder",
    )

    result = await Valley._process_target_campfire(valley, "Legal Team", torch)

    assert result is not None
    assert result.data["ok"] is True
    assert result.data["campfire"] == "Legal Team"
    assert "VoxFlo AI Ltd" in result.data["text"]
    assert "Hibbert IT Solutions Limited" in result.data["text"]
    assert "GBP 3,750" in result.data["text"]
    assert "30-day" in result.data["text"]
    assert "IR35" in result.data["text"]
    assert "Role Contributions" in result.data["text"]

    history = result.data["watch"]["history"]
    assert [entry.get("round") for entry in history] == ["discover", "plan", "execute", "verify", "improve"]
    assert history[0]["campers_used"] == ["Contract Researcher"]
    assert history[2]["campers_used"] == ["Contract Analyst", "Legal Reporter"]
    assert auditor.verify_calls == 1
    assert auditor.improve_calls == 1
    assert valley._watch_learnings["Legal Team"]["passes"] == 1
    assert result.data["watch"]["report_path"].endswith(".html")
