#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${SUBAGENT_RUNNER_RUN_ROOT:-$PWD/tmp/iflow-runs}"
KEEP_HOURS=72
DRY_RUN=0
INCLUDE_RUNNING=0

usage() {
  cat <<EOF
Usage:
  $0 [options]

Options:
  --root-dir <path>       Run root to clean (default: $PWD/tmp/iflow-runs)
  --keep-hours <hours>    Keep runs newer than this many hours (default: 72)
  --keep-days <days>      Keep runs newer than this many days (overrides --keep-hours)
  --include-running       Also delete running/starting runs if they are old enough (default: skip running)
  --dry-run               Print what would be deleted without removing anything
  --help                  Show this help

Rules:
  - By default only completed/failed runs older than the retention window are deleted.
  - Directories without status.json fall back to directory mtime.
  - Running/starting runs are skipped unless --include-running is given.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root-dir)
      ROOT_DIR="$2"
      shift 2
      ;;
    --keep-hours)
      KEEP_HOURS="$2"
      shift 2
      ;;
    --keep-days)
      KEEP_HOURS="$(( $2 * 24 ))"
      shift 2
      ;;
    --include-running)
      INCLUDE_RUNNING=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$KEEP_HOURS" in
  ''|*[!0-9]*)
    echo "--keep-hours/--keep-days must be a non-negative integer" >&2
    exit 2
    ;;
esac

if [ ! -d "$ROOT_DIR" ]; then
  echo "root dir not found: $ROOT_DIR" >&2
  exit 1
fi

now_epoch() {
  date +%s
}

file_mtime_epoch() {
  local target="$1"
  if stat -f '%m' "$target" >/dev/null 2>&1; then
    stat -f '%m' "$target"
  else
    stat -c '%Y' "$target"
  fi
}

iso_to_epoch() {
  local iso="$1"
  if [ -z "$iso" ]; then
    return 0
  fi
  node -e 'const raw=process.argv[1]; const ms=Date.parse(raw); if (Number.isFinite(ms)) process.stdout.write(String(Math.floor(ms / 1000)));' "$iso"
}

read_status_info() {
  local status_path="$1"
  node - "$status_path" <<'NODE'
const fs = require('fs');
const statusPath = process.argv[2];
try {
  const status = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
  const state = status.state || '';
  const running = ['starting', 'running'].includes(state);
  const anchor = running
    ? (status.updatedAt || status.lastHeartbeatAt || status.lastActivityAt || status.lastOutputAt || status.startedAt || status.createdAt || '')
    : (status.completedAt || status.updatedAt || status.lastHeartbeatAt || status.lastActivityAt || status.lastOutputAt || status.startedAt || status.createdAt || '');
  process.stdout.write(JSON.stringify({ state, running, anchor }));
} catch (_) {
  process.stdout.write('{}');
}
NODE
}

RETENTION_SEC=$(( KEEP_HOURS * 3600 ))
NOW_EPOCH="$(now_epoch)"
SCAN_COUNT=0
DELETE_COUNT=0
SKIP_RUNNING_COUNT=0
KEEP_COUNT=0

while IFS= read -r -d '' run_dir; do
  SCAN_COUNT=$((SCAN_COUNT + 1))
  status_path="$run_dir/status.json"
  state="unknown"
  running=0
  anchor_epoch=""
  anchor_source="mtime"

  if [ -f "$status_path" ]; then
    status_json="$(read_status_info "$status_path")"
    state="$(printf '%s' "$status_json" | node -e 'const fs=require("fs"); const obj=JSON.parse(fs.readFileSync(0,"utf8")); process.stdout.write(String(obj.state || "unknown"));')"
    running_text="$(printf '%s' "$status_json" | node -e 'const fs=require("fs"); const obj=JSON.parse(fs.readFileSync(0,"utf8")); process.stdout.write(obj.running ? "1" : "0");')"
    if [ "$running_text" = "1" ]; then
      running=1
    fi
    anchor_iso="$(printf '%s' "$status_json" | node -e 'const fs=require("fs"); const obj=JSON.parse(fs.readFileSync(0,"utf8")); process.stdout.write(String(obj.anchor || ""));')"
    anchor_epoch="$(iso_to_epoch "$anchor_iso")"
    if [ -n "$anchor_epoch" ]; then
      anchor_source="status"
    fi
  fi

  if [ -z "$anchor_epoch" ]; then
    anchor_epoch="$(file_mtime_epoch "$run_dir")"
    anchor_source="mtime"
  fi

  age_sec=$(( NOW_EPOCH - anchor_epoch ))
  if [ "$age_sec" -lt 0 ]; then
    age_sec=0
  fi

  if [ "$running" -eq 1 ] && [ "$INCLUDE_RUNNING" -ne 1 ]; then
    echo "SKIP running state=$state ageSec=$age_sec dir=$run_dir"
    SKIP_RUNNING_COUNT=$((SKIP_RUNNING_COUNT + 1))
    continue
  fi

  if [ "$age_sec" -lt "$RETENTION_SEC" ]; then
    echo "KEEP state=$state ageSec=$age_sec source=$anchor_source dir=$run_dir"
    KEEP_COUNT=$((KEEP_COUNT + 1))
    continue
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY-RUN delete state=$state ageSec=$age_sec source=$anchor_source dir=$run_dir"
  else
    rm -rf -- "$run_dir"
    echo "DELETED state=$state ageSec=$age_sec source=$anchor_source dir=$run_dir"
  fi
  DELETE_COUNT=$((DELETE_COUNT + 1))
done < <(find "$ROOT_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

echo "SUMMARY scanned=$SCAN_COUNT kept=$KEEP_COUNT skipped_running=$SKIP_RUNNING_COUNT deleted=$DELETE_COUNT root=$ROOT_DIR retentionSec=$RETENTION_SEC dryRun=$DRY_RUN includeRunning=$INCLUDE_RUNNING"
