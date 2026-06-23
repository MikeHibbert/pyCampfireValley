import types

import pytest

from campfirevalley.valley import Valley


@pytest.mark.asyncio
async def test_process_torch_prefers_exact_campfire_name_over_route_parsing():
    valley = Valley.__new__(Valley)
    valley._running = True
    valley.name = "Local Valley"
    valley.dock = None
    exact_name = "that can get the headlines from http://www.bbc.co.uk"
    valley.campfires = {exact_name: object()}

    async def fake_process_round_chain(_torch):
        return None

    async def fake_process_target_campfire(name, _torch):
        return {"routed_to": name}

    valley.process_round_chain = fake_process_round_chain
    valley._process_target_campfire = fake_process_target_campfire

    torch = types.SimpleNamespace(
        target_address=exact_name,
        torch_id="voice_test",
        sender_valley="Local Valley",
    )

    result = await Valley.process_torch(valley, torch)

    assert result == {"routed_to": exact_name}
