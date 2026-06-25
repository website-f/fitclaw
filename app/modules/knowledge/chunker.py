"""Text chunker — splits a long document into overlap-windowed segments.

Targets ~800 chars per chunk with 100-char overlap so a passage that
straddles a chunk boundary is recoverable from at least one chunk.
"""
from __future__ import annotations

import re

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_WHITESPACE = re.compile(r"[ \t]+")


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def chunk_text(raw: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = _normalize(raw)
    if not text:
        return []
    if len(text) <= size:
        return [text]

    # Prefer paragraph boundaries; fall back to char windows.
    paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= size:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if len(paragraph) <= size:
            buffer = paragraph
        else:
            # Single long paragraph — slice with overlap.
            start = 0
            while start < len(paragraph):
                end = min(start + size, len(paragraph))
                chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = max(0, end - overlap)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


def estimate_tokens(text: str) -> int:
    """Rough heuristic: ~4 chars per token."""
    return max(1, len(text) // 4)
