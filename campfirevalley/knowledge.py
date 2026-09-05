"""Domain knowledge for the valley - teach a domain from documents.

Never loads a whole corpus into context: documents are chunked by heading
(with overlap), embedded, and stored with per-chunk provenance (source file,
heading, chunk index). At question time a small number of chunks are
retrieved as grounding. A per-file digest is embedded alongside so retrieval
can find the right document even before finding the right chunk.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_CHUNK_CHARS = 1200
OVERLAP_CHARS = 150
DIGEST_CHARS = 600


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    heading: str
    index: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Chunk":
        return Chunk(
            id=d.get("id") or "",
            text=d.get("text") or "",
            source=d.get("source") or "",
            heading=d.get("heading") or "",
            index=int(d.get("index") or 0),
        )


def chunk_markdown(text: str, source: str = "", max_chars: int = MAX_CHUNK_CHARS,
                   overlap: int = OVERLAP_CHARS) -> List[Chunk]:
    """Split a markdown document into heading-based chunks with overlap.

    Heading lines (# ...) open a new chunk. Long sections are split on
    paragraph boundaries, each keeping a small tail of the previous chunk
    for context. Never returns an empty list for non-empty input.
    """
    lines = (text or "").splitlines()
    sections: List[tuple] = []  # (heading, list_of_lines)
    heading = ""
    buf: List[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s+", line):
            if buf and any(x.strip() for x in buf):
                sections.append((heading, buf))
            heading = line.strip()[:120]
            buf = []
        buf.append(line)
    if buf and any(x.strip() for x in buf):
        sections.append((heading, buf))
    if not sections:
        return []

    chunks: List[Chunk] = []
    base_hash = hashlib.sha256((source or "inline").encode("utf-8")).hexdigest()[:8]
    for heading, sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue
        # split long sections on paragraph boundaries; oversized paragraphs
        # are hard-split on word boundaries with overlap
        def _split_oversized(para: str) -> List[str]:
            if len(para) <= max_chars:
                return [para]
            parts: List[str] = []
            pos = 0
            step = max_chars - overlap if max_chars > overlap else max_chars
            while pos < len(para):
                end = min(pos + step, len(para))
                # prefer a word boundary
                sp = para.rfind(" ", pos, end)
                if sp > pos:
                    end = sp
                parts.append(para[pos:end].strip())
                pos = max(end - overlap, end, pos + 1) if overlap else end
            return [p for p in parts if p]

        paras: List[str] = []
        for p in re.split(r"\n\s*\n", sec_text):
            if not p.strip():
                continue
            paras.extend(_split_oversized(p.strip()))
        cur: List[str] = []
        cur_len = 0
        idx = 0
        for p in paras:
            if cur and cur_len + len(p) + 2 > max_chars:
                body = "\n\n".join(cur).strip()
                tail = body[-overlap:] if overlap and len(body) > overlap else ""
                chunks.append(Chunk(
                    id=f"{base_hash[:8]}-{len(chunks)}",
                    text=(tail + "\n" + body).strip() if tail else body,
                    source=source,
                    heading=heading,
                    index=idx,
                ))
                idx += 1
                cur = []
                cur_len = 0
            cur.append(p)
            cur_len += len(p) + 2
        if cur:
            body = "\n\n".join(cur).strip()
            chunks.append(Chunk(
                id=f"{base_hash[:8]}-{len(chunks)}",
                text=body,
                source=source,
                heading=heading,
                index=idx,
            ))
    return chunks


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Env-driven embedding: local ollama nomic-embed-text, OpenRouter, or hash fallback."""
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            return _embed_openrouter(texts)
        except Exception:
            pass
    base = (os.getenv("OLLAMA_BASE_URL") or "").strip().rstrip("/")
    if base:
        try:
            return _embed_ollama(base, texts)
        except Exception:
            pass
    return _hash_embed(texts)


def _embed_ollama(base: str, texts: List[str]) -> List[List[float]]:
    import httpx
    model = (os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text").strip()
    out: List[List[float]] = []
    with httpx.Client(timeout=30) as client:
        for t in texts:
            r = client.post(base + "/api/embed", json={"model": model, "input": t})
            r.raise_for_status()
            data = r.json()
            emb = data.get("embeddings") or [[0.0]]
            out.append(list(emb[0]))
    return out


def _embed_openrouter(texts: List[str]) -> List[List[float]]:
    import httpx
    key = os.getenv("OPENROUTER_API_KEY", "")
    model = (os.getenv("OPENROUTER_EMBED_MODEL") or "openai/text-embedding-3-small").strip()
    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": "Bearer " + key},
            json={"model": model, "input": texts},
        )
        r.raise_for_status()
        data = r.json()
        return [d["embedding"] for d in data.get("data", [])]


def _hash_embed(texts: List[str], dims: int = 384) -> List[List[float]]:
    vectors: List[List[float]] = []
    for t in texts:
        v = [0.0] * dims
        for token in re.findall(r"[a-zA-Z0-9']+", (t or "").lower()):
            idx = (hash(token) & 0x7FFFFFFF) % dims
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        vectors.append([x / norm for x in v])
    return vectors


def _cosine(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return num / (na * nb)


class DomainStore:
    """Store + retrieve domain chunks with provenance.

    Prefers chromadb when importable (collection 'domain_docs'); otherwise a
    deterministic JSON vector store (cosine in pure python, bounded files).
    """

    COLLECTION = "domain_docs"

    def __init__(self, path: str = ""):
        self.path = path or os.getenv("KNOWLEDGE_DB", "./knowledge")
        self._client = None
        self._col = None
        try:
            import chromadb  # noqa: F401
            import chromadb.config as _cfg
            self._client = _cfg.get_or_create_client("chromadb")
        except Exception:
            self._client = None

    # --- chroma path -----------------------------------------------------
    def _chroma_col(self):
        if self._col is not None:
            return self._col
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.path)
            self._col = self._client.get_or_create_collection(self.COLLECTION)
            return self._col
        except Exception:
            self._col = None
            return None

    # --- json fallback ---------------------------------------------------
    def _json_file(self) -> Path:
        return Path(self.path + ".json")

    def _json_load(self) -> List[dict]:
        f = self._json_file()
        if not f.exists():
            return []
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _json_save(self, rows: List[dict]) -> None:
        f = self._json_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rows[-5000:], ensure_ascii=False), encoding="utf-8")

    # --- api --------------------------------------------------------------
    def add(self, chunks: List[Chunk], texts_for_embed: Optional[List[str]] = None) -> int:
        """Embed + store chunks (with provenance metadata). Returns count added."""
        if not chunks:
            return 0
        payloads = texts_for_embed or [c.text for c in chunks]
        vecs = embed_texts(payloads)
        col = self._chroma_col()
        if col is not None:
            col.upsert(
                ids=[c.id for c in chunks],
                documents=[c.text for c in chunks],
                embeddings=vecs,
                metadatas=[{"source": c.source, "heading": c.heading, "chunk_index": c.index} for c in chunks],
            )
            return len(chunks)
        rows = self._json_load()
        known = {r["id"] for r in rows}
        added = 0
        for pos, (c, v) in enumerate(zip(chunks, vecs)):
            if c.id in known:
                continue
            rows.append({"id": c.id, "vector": v, "chunk": c.to_dict()})
            added += 1
        self._json_save(rows)
        return added

    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Top-k chunks as grounding, each with provenance."""
        qv = embed_texts([query])[0]
        col = self._chroma_col()
        if col is not None:
            res = col.query(query_embeddings=[qv], n_results=max(1, k),
                            include=["documents", "metadatas", "distances"])
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            out: List[Dict[str, Any]] = []
            for d, m in zip(docs, metas):
                out.append({"text": d, "source": (m or {}).get("source", ""),
                            "heading": (m or {}).get("heading", ""),
                            "chunk_index": (m or {}).get("chunk_index", 0)})
            return out
        rows = self._json_load()
        scored = []
        for r in rows:
            vec = r.get("vector") or []
            if not vec:
                continue
            scored.append((_cosine(qv, vec), r))
        scored.sort(key=lambda x: -x[0])
        return [r["chunk"] | {"score": round(s, 4)} for s, r in scored[:max(1, k)]]

    def count(self) -> int:
        col = self._chroma_col()
        if col is not None:
            return int(col.count())
        return len(self._json_load())


def ingest_file(path: str, store: DomainStore) -> int:
    """Ingest one file: chunks + per-file digest (embedded alongside)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_markdown(text, source=str(p))
    if not chunks:
        return 0
    digest = text[:DIGEST_CHARS]
    dchunk = Chunk(
        id="digest-" + hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:10],
        text=digest,
        source=str(p),
        heading="[file digest]",
        index=-1,
    )
    all_chunks = chunks + [dchunk]
    payloads = [c.text for c in all_chunks]
    return store.add(all_chunks, payloads)


def ingest_path(path: str, store: DomainStore) -> int:
    """Ingest a file or directory (markdown/text files)."""
    p = Path(path)
    if p.is_file():
        return ingest_file(str(p), store)
    total = 0
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".md", ".markdown", ".txt"):
            total += ingest_file(str(f), store)
    return total


def ask(store: DomainStore, question: str, k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve grounding chunks for a question (provenance included)."""
    return store.retrieve(question, k=max(1, min(10, k)))

def _cli_learn(args) -> None:
    from rich.console import Console
    console = Console()
    store = DomainStore(args.db)
    n = ingest_path(args.path, store)
    console.print("[bold]Learned[/] " + str(n) + " chunk(s) from " + args.path + " into " + store.path)


def _cli_ask(args) -> None:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    store = DomainStore(args.db)
    hits = ask(store, args.question, k=args.k)
    if not hits:
        console.print("[dim]No grounding found - teach me first with 'campfirevalley learn'.[/]")
        return
    for h in hits:
        title = (h.get("source") or "?") + " | " + (h.get("heading") or "?") + (" #" + str(h.get("chunk_index")) if h.get("chunk_index", 0) >= 0 else "")
        console.print(Panel((h.get("text") or "")[:800], title=title, border_style="dim"))
