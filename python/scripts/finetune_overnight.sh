#!/bin/bash
# Fine-tune the AI engine on one grading round, then score it on the
# held-out random draw, unattended:
#
#   finetune_overnight.sh ROUND_DIR RUN_DIR BASE_WEIGHTS TRAIN_ENV [ITERS]
#
# RUN_DIR/data is the exporter's output (extract_text.finetune). The adapter,
# logs, and scores land in RUN_DIR, which must be governed storage: a model
# trained on court records can repeat names and addresses from them, so
# nothing here goes to a hub or a server. ITERS caps training for a timing
# trial; without it the run is EPOCHS passes over the training rows.
#
# Each step's exit code goes to RUN_DIR/status.txt, so a morning reader can
# see where a run stopped without reading the logs.
set -u
ROUND=$1 RUN=$2 BASE=$3 ENV=$4 ITERS=${5:-}
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
PY=$ENV/bin/python
EPOCHS=3
mkdir -p "$RUN/logs"
STATUS=$RUN/status.txt
step() { echo "$(date '+%F %T') $1 exit=$2" >> "$STATUS"; }

# keep the machine awake for as long as this script runs
caffeinate -dims -w $$ &

# free the memory Ollama holds; the run needs all of it
ollama stop qwen3.5:9b >/dev/null 2>&1

if [ -n "$ITERS" ]; then LENGTH=(--iters "$ITERS"); else LENGTH=(--epochs "$EPOCHS"); fi
echo "$(date '+%F %T') start ${LENGTH[*]}" >> "$STATUS"
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 "$PY" -m mlx_vlm.train \
  --model "$BASE" --data "$RUN/data" \
  --train-type lora --lora-rank 16 --lora-alpha 32 --lora-dropout 0.05 \
  --learning-rate 1e-4 --batch-size 1 --gradient-accumulation-steps 4 \
  "${LENGTH[@]}" --seed 42 \
  --train-on-completions --max-seq-length 4096 --grad-checkpoint \
  --steps-per-report 10 --steps-per-eval 100 --val-batches -1 --steps-per-save 50 \
  --output-path "$RUN/adapters" > "$RUN/logs/train.log" 2>&1
code=$?; step train $code
[ $code -ne 0 ] && exit $code
[ -n "$ITERS" ] && exit 0

HF_HUB_OFFLINE=1 "$PY" "$SCRIPTS/finetune_eval.py" --scan "$ROUND" --run "$RUN" \
  --engine mlx --model "$BASE" --adapter "$RUN/adapters" --label lists_mlx_tuned \
  > "$RUN/logs/eval_tuned.log" 2>&1
step eval_tuned $?

HF_HUB_OFFLINE=1 "$PY" "$SCRIPTS/finetune_eval.py" --scan "$ROUND" --run "$RUN" \
  --engine mlx --model "$BASE" --label lists_mlx_untuned \
  > "$RUN/logs/eval_untuned.log" 2>&1
step eval_untuned $?

cat "$RUN"/eval/*_score.txt > "$RUN/eval/summary.txt" 2>/dev/null
step done 0
