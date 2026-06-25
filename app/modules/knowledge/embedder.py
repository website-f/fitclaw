"""Lightweight text embedding without external dependencies.

Strategy: hashed character-trigram + token bag-of-words counts, projected
into a 256-dim fixed-size vector via Python's built-in hash. Good enough
for "is this chunk relevant to that query" cosine ranking on small
corpora (< a few thousand chunks). Swap for sentence-transformers or a
real embedding API later — the rest of the pipeline doesn't care.

`embed(text) -> list[float]` is the only public contract.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

EMBED_DIM = 256
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vec))
    if norm <= 0:
        return vec
    return [value / norm for value in vec]


def _hash_bucket(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % EMBED_DIM


def _trigrams(text: str) -> Iterable[str]:
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if len(cleaned) < 3:
        return [cleaned] if cleaned else []
    return (cleaned[i : i + 3] for i in range(len(cleaned) - 2))


def embed(text: str) -> list[float]:
    """Return a 256-dim L2-normalized embedding for `text`."""
    vec = [0.0] * EMBED_DIM
    if not text:
        return vec

    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < 2:
            continue
        # Tokens carry more weight than trigrams.
        vec[_hash_bucket(token)] += 2.0
        # Token prefix captures word-stem variants.
        vec[_hash_bucket(token[:4])] += 1.0

    for tri in _trigrams(text):
        vec[_hash_bucket(tri)] += 0.5

    return _normalize(vec)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def keywords(text: str, *, limit: int = 8) -> list[str]:
    """Cheap keyword extraction — frequency-ranked tokens minus stopwords."""
    counts: dict[str, int] = {}
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < 4 or token in _STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [word for word, _ in ranked[:limit]]


_STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "another", "around", "because", "been",
    "before", "being", "below", "between", "both", "could", "doing", "during", "each", "either",
    "every", "from", "further", "having", "having", "here", "hers", "herself", "himself", "into",
    "itself", "just", "more", "most", "myself", "neither", "noone", "other", "ours", "ourselves",
    "over", "should", "some", "such", "than", "that", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "under", "until", "very", "were",
    "what", "when", "where", "which", "while", "with", "would", "your", "yours", "yourself",
    "yourselves", "have", "shall", "will", "want", "kind", "like", "make", "made", "much", "many",
    "only", "same", "still", "yet",
}
