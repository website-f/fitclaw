FROM golang:1.24 AS memorycore-builder

WORKDIR /src/memorycore_cli

COPY memorycore_cli/go.mod ./
COPY memorycore_cli/main.go ./

RUN mkdir -p /out/windows-x64 /out/macos-x64 /out/macos-arm64 \
    && CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o /out/windows-x64/memorycore.exe . \
    && CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -o /out/macos-x64/memorycore . \
    && CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -o /out/macos-arm64/memorycore .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY . /app
COPY --from=memorycore-builder /out /app/memorycore_dist

RUN mkdir -p /data \
    && chmod +x /app/docker/ollama/entrypoint.sh

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
