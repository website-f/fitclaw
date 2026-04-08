#!/bin/sh
set -eu

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
OLLAMA_MODELS="${OLLAMA_MODELS:-$OLLAMA_MODEL}"
OLLAMA_OPTIONAL_MODELS="${OLLAMA_OPTIONAL_MODELS:-}"
OLLAMA_VISION_MODELS="${OLLAMA_VISION_MODELS:-}"
ALL_MODELS="$OLLAMA_MODEL,$OLLAMA_MODELS"
if [ -n "$OLLAMA_VISION_MODELS" ]; then
  ALL_MODELS="$ALL_MODELS,$OLLAMA_VISION_MODELS"
fi
if [ -n "$OLLAMA_OPTIONAL_MODELS" ]; then
  ALL_MODELS="$ALL_MODELS,$OLLAMA_OPTIONAL_MODELS"
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

has_model() {
  model_name="$1"
  ollama list | tr -s ' ' | cut -d ' ' -f1 | tail -n +2 | grep -Fxq "$model_name"
}

pull_model() {
  model_name="$1"
  optional_flag="$2"

  if has_model "$model_name"; then
    echo "Ollama model already available: $model_name"
    return 0
  fi

  echo "Pulling Ollama model: $model_name"
  if ollama pull "$model_name"; then
    return 0
  fi

  if [ "$optional_flag" = "true" ]; then
    echo "Optional model pull failed, continuing startup: $model_name"
    return 0
  fi

  echo "Required model pull failed: $model_name"
  return 1
}

IFS=','
for model in $ALL_MODELS; do
  model="$(echo "$model" | xargs)"
  if [ -z "$model" ]; then
    continue
  fi
  case ",$OLLAMA_OPTIONAL_MODELS," in
    *,"$model",*)
      pull_model "$model" "true"
      ;;
    *)
      pull_model "$model" "false"
      ;;
  esac
done
unset IFS

wait "$OLLAMA_PID"
