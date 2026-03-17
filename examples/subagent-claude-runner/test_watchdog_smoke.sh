#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/runner.js"
WATCHER="$SCRIPT_DIR/watcher.js"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/subagent-runner-smoke.XXXXXX")"
MOCK_BIN_DIR="$TEST_ROOT/mock-bin"
RUNS_DIR="$TEST_ROOT/runs"
WORKDIR_QUIET="$TEST_ROOT/workdir-quiet"
WORKDIR_STALL="$TEST_ROOT/workdir-stall"

cleanup() {
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

mkdir -p "$MOCK_BIN_DIR" "$RUNS_DIR" "$WORKDIR_QUIET" "$WORKDIR_STALL"

assert_json() {
  local file="$1"
  local expr="$2"
  local msg="$3"
  node -e '
const fs = require("fs");
const [file, expr, msg] = process.argv.slice(1);
const data = JSON.parse(fs.readFileSync(file, "utf8"));
let ok = false;
try {
  ok = Boolean(Function("data", `return (${expr});`)(data));
} catch (error) {
  console.error(`ASSERT EVAL ERROR: ${msg}: ${error.message}`);
  process.exit(1);
}
if (!ok) {
  console.error(`ASSERT FAIL: ${msg}`);
  console.error(JSON.stringify(data, null, 2));
  process.exit(1);
}
' "$file" "$expr" "$msg"
}

cat > "$MOCK_BIN_DIR/claude-quiet-workdir.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${WORKDIR_ACTIVITY_FILE:?missing WORKDIR_ACTIVITY_FILE}"
echo 'MILESTONE: quiet-started'
(
  for i in 1 2 3 4 5; do
    sleep 1
    printf 'tick-%s\n' "$i" >> "$WORKDIR_ACTIVITY_FILE"
  done
) &
worker_pid=$!
sleep 6
wait "$worker_pid"
echo 'MILESTONE: quiet-finished'
EOF
chmod +x "$MOCK_BIN_DIR/claude-quiet-workdir.sh"

cat > "$MOCK_BIN_DIR/claude-hard-stall.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo 'MILESTONE: stall-started'
sleep 30
EOF
chmod +x "$MOCK_BIN_DIR/claude-hard-stall.sh"

echo '[smoke] case1 quiet-but-workdir-active'
CASE1_RUN_DIR="$RUNS_DIR/case1"
CASE1_OUTPUT_FILE="$TEST_ROOT/case1.out"
WORKDIR_ACTIVITY_FILE="$WORKDIR_QUIET/activity.log" \
CLAUDE_BIN="$MOCK_BIN_DIR/claude-quiet-workdir.sh" \
node "$RUNNER" \
  --label smoke-case1 \
  --cwd "$WORKDIR_QUIET" \
  --run-dir "$CASE1_RUN_DIR" \
  --timeout-s 40 \
  --idle-timeout-s 2 \
  --stall-grace-s 4 \
  --task 'mock quiet workdir activity' > "$CASE1_OUTPUT_FILE"
CASE1_SUMMARY="$CASE1_RUN_DIR/final-summary.json"
CASE1_WATCHER_OUT="$TEST_ROOT/case1.watcher.out"
node "$WATCHER" --run-dir "$CASE1_RUN_DIR" --once > "$CASE1_WATCHER_OUT"
assert_json "$CASE1_SUMMARY" "data.state === 'completed'" 'case1 should complete'
assert_json "$CASE1_SUMMARY" "data.timedOut === false" 'case1 should not timeout'
assert_json "$CASE1_SUMMARY" "(data.activity?.workdirEventCount || 0) >= 3" 'case1 should record workdir activity'
assert_json "$CASE1_SUMMARY" "data.lastActivitySource === 'stdout' || data.lastActivitySource === 'workdir'" 'case1 should end with workdir or stdout activity'
grep -q 'STARTED' "$CASE1_WATCHER_OUT"
grep -q 'COMPLETED' "$CASE1_WATCHER_OUT"
node -e 'const fs=require("fs"); const data=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); console.log(JSON.stringify({case:"case1",state:data.state,timedOut:data.timedOut,lastActivitySource:data.lastActivitySource,workdirEventCount:data.activity.workdirEventCount,runDir:data.runDir},null,2));' "$CASE1_SUMMARY"

echo '[smoke] case2 hard-stall-timeout'
CASE2_RUN_DIR="$RUNS_DIR/case2"
CASE2_OUTPUT_FILE="$TEST_ROOT/case2.out"
set +e
CLAUDE_BIN="$MOCK_BIN_DIR/claude-hard-stall.sh" \
node "$RUNNER" \
  --label smoke-case2 \
  --cwd "$WORKDIR_STALL" \
  --run-dir "$CASE2_RUN_DIR" \
  --timeout-s 40 \
  --idle-timeout-s 2 \
  --stall-grace-s 2 \
  --kill-grace-ms 500 \
  --task 'mock hard stall' > "$CASE2_OUTPUT_FILE"
CASE2_EXIT=$?
set -e
if [ "$CASE2_EXIT" -eq 0 ]; then
  echo 'ASSERT FAIL: case2 expected non-zero exit' >&2
  exit 1
fi
CASE2_SUMMARY="$CASE2_RUN_DIR/final-summary.json"
CASE2_WATCHER_OUT="$TEST_ROOT/case2.watcher.out"
node "$WATCHER" --run-dir "$CASE2_RUN_DIR" --once > "$CASE2_WATCHER_OUT"
assert_json "$CASE2_SUMMARY" "data.state === 'failed'" 'case2 should fail'
assert_json "$CASE2_SUMMARY" "data.failureKind === 'timeout'" 'case2 should be timeout failure'
assert_json "$CASE2_SUMMARY" "data.timeout?.type === 'stall'" 'case2 timeout type should be stall'
assert_json "$CASE2_SUMMARY" "data.timedOut === true" 'case2 should be marked timedOut'
assert_json "$CASE2_SUMMARY" "Boolean(data.stall?.suspectedAt)" 'case2 should record suspected stall timestamp'
assert_json "$CASE2_SUMMARY" "Boolean(data.stall?.hardTimeoutAt)" 'case2 should record hard timeout timestamp'
grep -q 'STALL' "$CASE2_WATCHER_OUT"
grep -q 'FAILED' "$CASE2_WATCHER_OUT"
node -e 'const fs=require("fs"); const data=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); console.log(JSON.stringify({case:"case2",state:data.state,failureKind:data.failureKind,timeoutType:data.timeout.type,timedOut:data.timedOut,suspectedAt:data.stall.suspectedAt,hardTimeoutAt:data.stall.hardTimeoutAt,runDir:data.runDir},null,2));' "$CASE2_SUMMARY"

echo '[smoke] PASS all watchdog smoke cases'
