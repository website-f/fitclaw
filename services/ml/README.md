# ML service

Isolated Python microservice for ML inference. Intentionally small today
— it's a scaffold. Grows as you add real models.

## Why a separate service?

The main AI-ops platform's Docker image is ~400 MB. Adding TensorFlow
alone pushes that to ~2.5 GB. Adding OpenCV + torch + model weights gets
to ~6 GB. That's too heavy to rebuild on every app change, and too
expensive to duplicate across worker/bot/api containers.

Splitting ML out means:
- Main app stays small and fast to rebuild.
- ML container starts slow (loads models) but only restarts on ML changes.
- When you eventually want GPUs, you attach them to *this* container only.

## Running

Not started by default — it lives behind the `ml` compose profile:

```bash
docker compose --profile ml up -d ml
curl http://localhost:9000/health
curl http://localhost:9000/models
```

Standalone dev (skip Docker entirely):

```bash
cd services/ml
pip install -r requirements.txt
uvicorn main:app --reload --port 9000
```

## Adding a real model

1. Create `services/ml/models/your_model.py` with a `load()` + `predict()`
   function. Keep it synchronous; FastAPI handles concurrency.
2. Uncomment the corresponding dep in `requirements.txt` (tensorflow /
   opencv-python-headless / torch).
3. Wire it into `main.py`'s `/infer` dispatch:
   ```python
   if payload.model == "your-model":
       return InferResponse(model=payload.model, outputs=your_model.predict(payload.inputs))
   ```
4. Rebuild: `docker compose build ml`.

## What goes where

| Location | Purpose |
|---|---|
| `main.py` | HTTP surface — keep stable, callers depend on it |
| `models/` (you'll create) | Model loaders — one file per model, load once at import |
| `preprocessing/` (you'll create) | Image/text/audio prep shared across models |
| Model weights | **Not in git.** Mount a volume or pull from HF/S3 at startup. |

## GPU (later)

On a GPU-capable host:
```yaml
# docker-compose.yml — in the ml service
deploy:
  resources:
    reservations:
      devices:
        - capabilities: [gpu]
```
Plus `nvidia-container-toolkit` installed on the host. Not required today.
