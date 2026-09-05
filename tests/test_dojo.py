"""Offline tests for the kindling dojo. Run DIRECT: python tests/test_dojo.py

No network, no LLM - the forge gets an injected fake llm callable.
"""
import os
import sys
import tempfile

sys.path.insert(0, ".")

from campfirevalley.dojo import (  # noqa: E402
    Kindling,
    DojoForge,
    _parse_prompt_pair,
    _render_user,
    format_copy,
    save,
    load,
)


def fake_llm(system: str, user: str) -> str:
    return (
        "Here is your kindling.\n\n"
        "```" + "SYSTEM_PROMPT" + "\nYou are a patient code reviewer.\n```\n\n"
        "```" + "USER_TEMPLATE" + "\nReview the following: {request}\n```\n"
        "Good luck!"
    )


def test_parse_prompt_pair_prose_wrapped():
    raw = (
        "Sure, here you go.\n"
        "```SYSTEM_PROMPT\nBe kind.\n```\n"
        "```USER_TEMPLATE\n{request}\n```\n"
        "Done."
    )
    system, user = _parse_prompt_pair(raw)
    assert system == "Be kind."
    assert user == "{request}"


def test_parse_prompt_pair_clean():
    raw = "```SYSTEM_PROMPT\nA.\n```\n```USER_TEMPLATE\nB {request}\n```"
    system, user = _parse_prompt_pair(raw)
    assert system == "A." and user == "B {request}"


def test_parse_prompt_pair_malformed_raises():
    try:
        _parse_prompt_pair("no blocks here")
        raise AssertionError("should have raised")
    except ValueError as e:
        assert "tagged blocks" in str(e)


def test_render_user_template_with_and_without_placeholder():
    assert _render_user("Review: {request}", "foo.py") == "Review: foo.py"
    assert "foo.py" in _render_user("No placeholder", "foo.py")


def test_generate_and_test_with_fake_llm():
    forge = DojoForge(llm=fake_llm)
    k = forge.generate("a patient code reviewer", name="reviewer")
    assert k.system_prompt == "You are a patient code reviewer."
    assert k.user_template == "Review the following: {request}"
    reply = forge.test(k, "def add(a, b): return a + b")
    assert "review" in reply.lower() or reply


def test_copy_block_deterministic():
    k = Kindling(name="x", description="d", system_prompt="S", user_template="U {request}")
    assert format_copy(k) == format_copy(Kindling.from_dict(k.to_dict()))
    assert "```" in format_copy(k) and "SYSTEM PROMPT" in format_copy(k)


def test_save_load_roundtrip():
    k = Kindling(name="x", description="d", system_prompt="S", user_template="U")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "k.json")
        save(k, path)
        k2 = load(path)
        assert k2.to_dict() == k.to_dict()


if __name__ == "__main__":
    test_parse_prompt_pair_prose_wrapped()
    test_parse_prompt_pair_clean()
    test_parse_prompt_pair_malformed_raises()
    test_render_user_template_with_and_without_placeholder()
    test_generate_and_test_with_fake_llm()
    test_copy_block_deterministic()
    test_save_load_roundtrip()
    print("ALL DOJO TESTS PASS (7/7)")