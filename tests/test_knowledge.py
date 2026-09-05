"""Offline tests for domain knowledge ingest (no network, no chromadb).

Run DIRECT: python tests/test_knowledge.py  (chromadb absent -> JSON fallback path).
"""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, ".")

from campfirevalley.knowledge import (  # noqa: E402
    Chunk, chunk_markdown, DomainStore, ingest_file, ask,
)


DOC = """# Getting started
Install the valley and run onboard.

## Setup
Create the manifest and call start.

## Advanced tuning
Watch rounds can run in parallel when configured.

# Troubleshooting
If the dock is down, torches queue until it returns.
"""


def test_chunk_by_heading():
    chunks = chunk_markdown(DOC, source="doc.md")
    assert len(chunks) >= 3, "expected heading-based sections"
    headings = [c.heading for c in chunks]
    assert any("Getting started" in h for h in headings)
    assert any("Troubleshooting" in h for h in headings)
    assert all(c.source == "doc.md" for c in chunks)
    assert all(c.index >= 0 for c in chunks)


def test_long_section_split_with_overlap():
    para = " ".join(["word"] * 300)
    doc = "# Big section\n\n" + ("\n\n" + para) * 6
    chunks = chunk_markdown(doc, source="big.md", max_chars=400, overlap=50)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 400 + 60 for c in chunks)  # body + tail tolerance


def test_hash_embed_deterministic():
    from campfirevalley.knowledge import embed_texts
    a = embed_texts(["alpha beta"])[0]
    b = embed_texts(["alpha beta"])[0]
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 0.01  # normalized


def test_store_roundtrip_and_retrieve(tmp_path=None):
    tmp = Path(tempfile.mkdtemp())
    store = DomainStore(str(tmp / "kb"))
    chunks = chunk_markdown(DOC, source="doc.md")
    n = store.add(chunks)
    assert n == len(chunks)
    assert store.count() >= len(chunks)
    hits = ask(store, "how do I run watch rounds in parallel?", k=3)
    assert hits, "expected grounding"
    top = hits[0]
    assert top.get("source") == "doc.md"
    assert top.get("heading") is not None


def test_ingest_file_with_digest(tmp_path=None):
    tmp = Path(tempfile.mkdtemp())
    doc = tmp / "guide.md"
    doc.write_text(DOC, encoding="utf-8")
    store = DomainStore(str(tmp / "kb2"))
    n = ingest_file(str(doc), store)
    assert n >= 2
    hits = ask(store, "troubleshooting dock", k=2)
    assert hits
    assert any(h.get("source", "").endswith("guide.md") for h in hits)


if __name__ == "__main__":
    test_chunk_by_heading()
    test_long_section_split_with_overlap()
    test_hash_embed_deterministic()
    test_store_roundtrip_and_retrieve()
    test_ingest_file_with_digest()
    print("ALL KNOWLEDGE TESTS PASS (5/5)")