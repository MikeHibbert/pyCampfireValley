import types

import pytest

import campfirevalley.web.api as api


class DummyValley:
    def __init__(self, plan_text: str = ""):
        self.name = "Local Valley"
        self.campfires = {}
        self.plan_text = plan_text
        self.provisioned = []
        self.workflows = {}

    async def provision_campfire(self, cfg):
        self.campfires[cfg.name] = cfg
        self.provisioned.append(cfg.name)
        return True

    async def process_torch(self, _torch):
        return types.SimpleNamespace(data={"text": self.plan_text})

    def set_workflow(self, parent, steps):
        self.workflows[parent] = {"steps": steps}
        return True

    def get_workflow(self, parent):
        return self.workflows.get(parent)


@pytest.fixture(autouse=True)
def restore_api_state(monkeypatch):
    previous_valley = api.current_valley
    previous_parent_map = dict(api.campfire_parent)
    monkeypatch.setattr(api, "_append_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(api, "parse_intent", lambda text: {"content": text})
    yield
    api.current_valley = previous_valley
    api.campfire_parent.clear()
    api.campfire_parent.update(previous_parent_map)


@pytest.mark.asyncio
async def test_create_camper_from_generic_auditor_creates_parent_campfire():
    valley = DummyValley()
    api.current_valley = valley
    api.campfire_parent.clear()

    response = await api.voice_ingest(
        {
            "campfire": "Auditor",
            "text": "create camper Intake Camper",
        }
    )

    assert response["response"]["created_campfire"] == "Intake Campfire"
    assert api.campfire_parent["Intake Camper"] == "Intake Campfire"
    assert valley.provisioned == ["Intake Campfire", "Intake Camper"]


@pytest.mark.asyncio
async def test_new_team_plan_does_not_use_camper_name_as_parent():
    valley = DummyValley(
        """{
            "campfire_to_create": {"name": "Intake Camper"},
            "campers_to_create": [
                {"name": "Intake Camper"},
                {"name": "Auditor Camper"}
            ],
            "task_plan": [
                {"camper": "Intake Camper", "task": "Triage incoming work"},
                {"camper": "Auditor Camper", "task": "Review the work"}
            ],
            "message_to_user": "Ready."
        }"""
    )
    valley.campfires["Workspace Campfire"] = object()
    api.current_valley = valley
    api.campfire_parent.clear()

    response = await api.voice_ingest(
        {
            "campfire": "Workspace Campfire",
            "auditor_mode": True,
            "text": "create a separate team with Intake Camper and Auditor Camper",
        }
    )

    assert response["response"]["created_campfire"] == "Intake Campfire"
    assert api.campfire_parent["Intake Camper"] == "Intake Campfire"
    assert api.campfire_parent["Auditor Camper"] == "Intake Campfire"
    assert "Intake Camper" in valley.campfires
    assert "Intake Campfire" in valley.campfires


@pytest.mark.asyncio
async def test_configuring_current_campfire_only_adds_missing_campers():
    valley = DummyValley(
        """{
            "campers_to_create": [
                {"name": "Intake Camper"},
                {"name": "Auditor Camper"}
            ],
            "task_plan": [
                {"camper": "Intake Camper", "task": "Triage incoming work"},
                {"camper": "Auditor Camper", "task": "Review the work"}
            ],
            "message_to_user": "Ready."
        }"""
    )
    valley.campfires["Hiring Campfire"] = object()
    valley.campfires["Intake Camper"] = object()
    api.current_valley = valley
    api.campfire_parent.clear()
    api.campfire_parent["Intake Camper"] = "Hiring Campfire"

    response = await api.voice_ingest(
        {
            "campfire": "Hiring Campfire",
            "auditor_mode": True,
            "text": "create a campfire team with Intake Camper and Auditor Camper",
        }
    )

    assert response["response"]["parent"] == "Hiring Campfire"
    assert response["response"]["created"] == ["Auditor Camper"]
    assert "Hiring Campfire" not in valley.provisioned
    assert valley.provisioned == ["Auditor Camper"]
    assert api.campfire_parent["Intake Camper"] == "Hiring Campfire"
    assert api.campfire_parent["Auditor Camper"] == "Hiring Campfire"
