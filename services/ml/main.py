"""ML microservice — scaffolding.

Intentionally small. This is where TensorFlow / OpenCV / torch code lives
*when you actually write it*. The main AI-ops platform talks to this over
HTTP and never imports ML deps directly — that's the whole point of
splitting it out (3+ GB of deps don't belong in every container).

Endpoints:
  GET  /health           → liveness
  GET  /models           → list loaded models (stub)
  POST /infer            → run inference (stub)
  POST /embeddings       → produce text embeddings (stub)

When you add a real model, put the loading logic in `services/ml/models/`
and expose it through one of the endpoints above. Keep the HTTP surface
small and stable; change the backend freely.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="ML service",
    version="0.0.1",
    description="Isolated ML inference service for the Personal AI Ops Platform.",
)


class InferRequest(BaseModel):
    model: str
    inputs: Any


class InferResponse(BaseModel):
    model: str
    outputs: Any
    note: str | None = None


class EmbedRequest(BaseModel):
    model: str = "placeholder-embed"
    texts: list[str]


class EmbedResponse(BaseModel):
    model: str
    embeddings: list[list[float]]
    dim: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
def list_models() -> dict[str, list[str]]:
    # Populate this when you wire real model loaders.
    return {"loaded": [], "available": []}


@app.post("/infer", response_model=InferResponse)
def infer(payload: InferRequest) -> InferResponse:
    if payload.model != "echo":
        raise HTTPException(
            status_code=501,
            detail=(
                f"Model '{payload.model}' is not implemented yet. "
                "This service is a scaffold — add a loader under services/ml/models/ "
                "and dispatch here."
            ),
        )
    return InferResponse(model=payload.model, outputs=payload.inputs, note="echo placeholder")


@app.post("/embeddings", response_model=EmbedResponse)
def embed(payload: EmbedRequest) -> EmbedResponse:
    # Stub: return deterministic fake embeddings so callers can wire up
    # pipelines before the real model exists.
    fake_dim = 8
    embeddings: list[list[float]] = []
    for text in payload.texts:
        seed = sum(ord(c) for c in text) % 997
        embeddings.append([((seed + i) % 100) / 100.0 for i in range(fake_dim)])
    return EmbedResponse(model=payload.model, embeddings=embeddings, dim=fake_dim)
