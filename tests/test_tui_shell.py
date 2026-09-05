"""Offline smoke tests for the TUI shell (no SSE, no network).

TuiState.observe shapes + _render smoke. Run DIRECT (python tests/test_tui_shell.py)
- pytest's SSE/TestClient paths hang under PS, and these tests never need it.
"""
import sys

sys.path.insert(0, ".")

from campfirevalley.tui import TuiState, _render  # noqa: E402


def test_torch_sets_and_clears():
    st = TuiState()
    st.observe({"type": "torch_received", "torch_id": "t1", "text": "fix the bug", "campfire": "dev"})
    assert st.current_torch and "t1" in st.current_torch
    st.observe({"type": "torch_completed", "torch_id": "t1", "text": "done"})
    assert st.current_torch is None


def test_leader_lines_cap():
    st = TuiState()
    for i in range(12):
        st.observe({"type": "leader_say", "text": f"line {i}"})
    assert len(st.leader_lines) == 8
    assert st.leader_lines[-1] == "line 11"


def test_activity_cap_and_label():
    st = TuiState()
    for i in range(250):
        st.observe({"type": "tool_started", "campfire": "dev", "text": f"tool {i}"})
    assert len(st.activity) == 200
    assert "[dev]" in st.activity[-1][1]


def test_empty_text_ignored():
    st = TuiState()
    st.observe({"type": "agent_say", "text": "   "})
    assert st.activity == [] and st.leader_lines == []


def test_render_smoke():
    st = TuiState()
    st.observe({"type": "torch_received", "torch_id": "t9", "text": "build docs", "campfire": "scribe"})
    st.observe({"type": "steward_patrol", "text": "patrol clean"})
    group = _render(st)
    assert group is not None


if __name__ == "__main__":
    test_torch_sets_and_clears()
    test_leader_lines_cap()
    test_activity_cap_and_label()
    test_empty_text_ignored()
    test_render_smoke()
    print("ALL TUI SHELL TESTS PASS (5/5)")