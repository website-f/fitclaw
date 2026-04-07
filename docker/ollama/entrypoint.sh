#!/bin/sh
set -eu

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
OLLAMA_MODELS="${OLLAMA_MODELS:-$OLLAMA_MODEL}"
OLLAMA_VISION_MODELS="${OLLAMA_VISION_MODELS:-}"
ALL_MODELS="$OLLAMA_MODEL,$OLLAMA_MODELS"
if [ -n "$OLLAMA_VISION_MODELS" ]; then
  ALL_MODELS="$ALL_MODELS,$OLLAMA_VISION_MODELS"
fi

ollama serve &
OLLAMA_PID=$!

cleanup() {
  kill "$OLLAMA_PID" >/dev/null 2>&1 || true
  wait "$OLLAMA_PID" >/dev/null 2>&1 || true
}

trap cleanup INT TERM EXIT

until ollama list >/dev/null 2>&1; do
  echo "Waiting for Ollama server to become ready..."
  sleep 2
done

IFS=','
for model in $ALL_MODELS; do
  model="$(echo "$model" | xargs)"
  if [ -z "$model" ]; then
    continue
  fi

  if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model"; then
    echo "Pulling Ollama model: $model"
    ollama pull "$model"
  else
    echo "Ollama model already available: $model"
  fi
done
unset IFS

wait "$OLLAMA_PID"
