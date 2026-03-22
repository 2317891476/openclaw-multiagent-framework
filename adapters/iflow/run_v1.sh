#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 \"task prompt\" [task_id]" >&2
  echo "env overrides: JOB_ID / TASK_ID / AGENT_TYPE / SUBAGENT_RUNNER_BIN / SUBAGENT_RUNNER_WORKDIR / SUBAGENT_IFLOW_TIMEOUT_S / SUBAGENT_IFLOW_IDLE_TIMEOUT_S / SUBAGENT_IFLOW_STALL_GRACE_S / SUBAGENT_IFLOW_KILL_GRACE_MS" >&2
  exit 2
fi

TASK="$1"
TASK_ID_INPUT="${2:-${TASK_ID:-task-001}}"
JOB_ID_VALUE="${JOB_ID:-JOB-001}"
AGENT_TYPE_VALUE="${AGENT_TYPE:-generic}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RUNNER="${SUBAGENT_RUNNER_BIN:-$SCRIPT_DIR/runner.js}"
WORKDIR="${SUBAGENT_RUNNER_WORKDIR:-$PWD}"
TIMEOUT_S="${SUBAGENT_IFLOW_TIMEOUT_S:-3600}"
IDLE_TIMEOUT_S="${SUBAGENT_IFLOW_IDLE_TIMEOUT_S:-900}"
STALL_GRACE_S="${SUBAGENT_IFLOW_STALL_GRACE_S:-300}"
KILL_GRACE_MS="${SUBAGENT_IFLOW_KILL_GRACE_MS:-5000}"

if [ ! -f "$RUNNER" ]; then
  echo "runner script not found: $RUNNER" >&2
  exit 1
fi

if [ ! -d "$WORKDIR" ]; then
  echo "workdir not found: $WORKDIR" >&2
  exit 1
fi

RUNNER_OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$RUNNER_OUTPUT_FILE"' EXIT

set +e
node "$RUNNER" \
  --job-id "$JOB_ID_VALUE" \
  --task-id "$TASK_ID_INPUT" \
  --agent-type "$AGENT_TYPE_VALUE" \
  --cwd "$WORKDIR" \
  --timeout-s "$TIMEOUT_S" \
  --idle-timeout-s "$IDLE_TIMEOUT_S" \
  --stall-grace-s "$STALL_GRACE_S" \
  --kill-grace-ms "$KILL_GRACE_MS" \
  --task "$TASK" >"$RUNNER_OUTPUT_FILE"
RUNNER_EXIT=$?
set -e

RUNNER_LINES=()
while IFS= read -r line || [ -n "$line" ]; do
  RUNNER_LINES+=("$line")
done <"$RUNNER_OUTPUT_FILE"

if [ "${#RUNNER_LINES[@]}" -lt 1 ] || [ -z "${RUNNER_LINES[0]}" ]; then
  echo "runner did not output run dir" >&2
  exit "${RUNNER_EXIT:-1}"
fi

RUN_DIR="${RUNNER_LINES[0]}"
FINAL_SUMMARY_PATH=""
FINAL_SUMMARY_JSON=""

for ((i = 1; i < ${#RUNNER_LINES[@]}; i++)); do
  line="${RUNNER_LINES[$i]}"
  case "$line" in
    FINAL_SUMMARY_PATH=*)
      FINAL_SUMMARY_PATH="${line#FINAL_SUMMARY_PATH=}"
      ;;
    FINAL_SUMMARY_JSON=*)
      FINAL_SUMMARY_JSON="${line#FINAL_SUMMARY_JSON=}"
      ;;
  esac
done

STATUS_PATH="$RUN_DIR/status.json"
STDOUT_PATH="$RUN_DIR/stdout.log"
STDERR_PATH="$RUN_DIR/stderr.log"
FINAL_REPORT_PATH="$RUN_DIR/final-report.md"
PROMPT_PATH="$RUN_DIR/prompt.txt"
META_PATH="$RUN_DIR/meta.json"

if [ -z "$FINAL_SUMMARY_PATH" ] && [ -f "$RUN_DIR/final_summary.json" ]; then
  FINAL_SUMMARY_PATH="$RUN_DIR/final_summary.json"
fi

if [ -z "$FINAL_SUMMARY_JSON" ] && [ -n "$FINAL_SUMMARY_PATH" ] && [ -f "$FINAL_SUMMARY_PATH" ]; then
  FINAL_SUMMARY_JSON="$(tr -d '\n' <"$FINAL_SUMMARY_PATH")"
fi

echo "RUN_DIR=$RUN_DIR"
echo "JOB_ID=$JOB_ID_VALUE"
echo "TASK_ID=$TASK_ID_INPUT"
echo "AGENT_TYPE=$AGENT_TYPE_VALUE"
echo "WORKDIR=$WORKDIR"
echo "PROMPT=$PROMPT_PATH"
echo "META=$META_PATH"
echo "STATUS=$STATUS_PATH"
echo "STDOUT=$STDOUT_PATH"
echo "STDERR=$STDERR_PATH"
echo "TIMEOUT_S=$TIMEOUT_S"
echo "IDLE_TIMEOUT_S=$IDLE_TIMEOUT_S"
echo "STALL_GRACE_S=$STALL_GRACE_S"
echo "KILL_GRACE_MS=$KILL_GRACE_MS"

if [ -n "$FINAL_SUMMARY_PATH" ]; then
  echo "FINAL_SUMMARY_PATH=$FINAL_SUMMARY_PATH"
fi

if [ -f "$FINAL_REPORT_PATH" ]; then
  echo "FINAL_REPORT=$FINAL_REPORT_PATH"
fi

if [ -n "$FINAL_SUMMARY_JSON" ]; then
  echo "FINAL_SUMMARY_JSON=$FINAL_SUMMARY_JSON"
fi

exit "$RUNNER_EXIT"
