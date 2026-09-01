#!/usr/bin/env bash
set -e

# Record metadata
TIMESTAMP=$(date +"%Y-%m-%dT%H:%M:%S%z")
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "not-a-git-repo")
OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "ollama-not-found")

# Models to test
MODELS=(
    "qwen3.5:9b"
    "deepseek-r1:7b"
    "phi4-mini:3.8b-q4_K_M"
)

# Configuration
TEMPERATURE="0.0"
MAX_TOKENS="2048"
CONTEXT_LENGTH="8192"

mkdir -p benchmark_results

echo "======================================"
echo "Starting Benchmark at $TIMESTAMP"
echo "Commit: $GIT_COMMIT"
echo "Ollama: $OLLAMA_VERSION"
echo "======================================"

for MODEL in "${MODELS[@]}"; do
    echo ""
    echo "Running benchmark for: $MODEL"
    # Note: Family name is derived from the model name for the logs
    FAMILY=$(echo "$MODEL" | cut -d':' -f1 | tr 'a-z' 'A-Z')
    
    LOG_FILE="benchmark_results/${FAMILY}_run.log"
    
    export BENCH_GIT_COMMIT=$GIT_COMMIT
    export BENCH_OLLAMA_VERSION=$OLLAMA_VERSION
    export BENCH_TIMESTAMP=$TIMESTAMP
    export BENCH_TEMP=$TEMPERATURE
    export BENCH_MAX_TOKENS=$MAX_TOKENS
    export BENCH_CONTEXT_LENGTH=$CONTEXT_LENGTH
    
    uv run python scripts/benchmark.py \
        --family "$FAMILY" \
        --artifact "$MODEL" \
        --quantization "auto" > "$LOG_FILE" 2>&1
        
    echo "Completed $MODEL. Results saved to $LOG_FILE"
done

echo ""
echo "All benchmarks finished!"
