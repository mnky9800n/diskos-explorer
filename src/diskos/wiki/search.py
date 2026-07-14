"""Local search over the wiki markdown (self-contained BM25, no dependencies).

At small scale the index.md catalog is enough, but a real ranked search over page
bodies is cheap to provide. This is a compact BM25 with no external services. For
larger wikis, swap in qmd (hybrid BM25 + vector + LLM re-rank) or the referenced
local-search-agent; the CLI surface can stay the same.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Navigation files, not content pages.
_SKIP = {"index.md", "log.md"}

_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def iter_pages(wiki_dir: str | Path) -> list[tuple[Path, str]]:
    """Return (path, text) for every content markdown page under ``wiki_dir``."""
    pages = []
    for path in sorted(Path(wiki_dir).rglob("*.md")):
        if path.name in _SKIP:
            continue
        pages.append((path, path.read_text(encoding="utf-8")))
    return pages


def _snippet(text: str, query_terms: set[str]) -> str:
    """Return the first non-empty line containing a query term, else the first heading."""
    heading = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("---"):
            continue
        if not heading and stripped.startswith("#"):
            heading = stripped.lstrip("# ").strip()
        if query_terms & set(_tokenize(stripped)):
            return stripped.lstrip("# ").strip()[:160]
    return heading[:160]


def search(wiki_dir: str | Path, query: str, top_k: int = 5) -> list[dict]:
    """Rank wiki pages against ``query`` with BM25. Returns dicts with path/score/snippet."""
    pages = iter_pages(wiki_dir)
    if not pages:
        return []

    docs = [_tokenize(text) for _, text in pages]
    doc_len = [len(d) for d in docs]
    avgdl = sum(doc_len) / len(docs) if docs else 0.0
    tfs = [Counter(d) for d in docs]

    n_docs = len(docs)
    df: Counter = Counter()
    for tf in tfs:
        df.update(tf.keys())

    q_terms = _tokenize(query)
    q_set = set(q_terms)

    scored = []
    for i, (path, text) in enumerate(pages):
        score = 0.0
        for term in q_terms:
            if term not in tfs[i]:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            freq = tfs[i][term]
            denom = freq + _K1 * (1 - _B + _B * (doc_len[i] / avgdl if avgdl else 0))
            score += idf * (freq * (_K1 + 1)) / denom
        if score > 0:
            scored.append({"path": path, "score": round(score, 4), "snippet": _snippet(text, q_set)})

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]
