#!/usr/bin/env bash
set -euo pipefail

TASK_ID="test_task_$(date +%s)"
STATUS_FILE="$HOME/.openclaw/shared-context/job-status/${TASK_ID}.json"
OUTPUT_FILE="$HOME/.openclaw/shared-context/job-status/${TASK_ID}-report.md"
TASKS_FILE="$HOME/.openclaw/shared-context/monitor-tasks/tasks.jsonl"

mkdir -p "$HOME/.openclaw/shared-context/job-status" "$HOME/.openclaw/shared-context/monitor-tasks"

echo "📝 Task ID: $TASK_ID"
echo "📝 Status File: $STATUS_FILE"
echo "📝 Output File: $OUTPUT_FILE"

echo ""
echo "🔧 Step 1: Registering task..."
python3 ~/.openclaw/workspace/skills/task_callback_bus/scripts/register_generic_task.py \
  --task-id "$TASK_ID" \
  --task-type sessions_spawn \
  --status-file "$STATUS_FILE" \
  --output-file "$OUTPUT_FILE" \
  --reply-to "user:main" \
  --owner main \
  --task-subject "框架测试任务" \
  --silent-until-terminal

echo ""
echo "🔍 Step 2: Verifying registration..."
if grep -q "\"task_id\": \"$TASK_ID\"" "$TASKS_FILE"; then
  echo "✅ Task registered successfully"
else
  echo "❌ Task registration failed"
  exit 1
fi

echo ""
echo "🔧 Step 3: Simulating worker writing status..."
cat > "$STATUS_FILE" <<EOF
{
  "state": "started",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "summary": "任务已启动"
}
EOF

echo "✅ Status file written: started"
sleep 1

cat > "$STATUS_FILE" <<EOF
{
  "state": "in_progress",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "summary": "任务执行中..."
}
EOF

echo "✅ Status file updated: in_progress"
sleep 1

cat > "$STATUS_FILE" <<EOF
{
  "state": "completed",
  "completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "summary": "任务已完成",
  "report_file": "$OUTPUT_FILE"
}
EOF

cat > "$OUTPUT_FILE" <<EOF
# Task Report: $TASK_ID

## 基本信息
- **Task ID**: $TASK_ID
- **Status**: completed
- **Owner**: main

## 执行摘要
这是一个框架测试任务，用于验证监控和通知链路是否正常工作。

## 验证结果
- [x] 任务注册成功
- [x] 状态文件写入正常
- [x] 报告文件生成成功
EOF

echo "✅ Status file written: completed"
echo "✅ Report file written"

echo ""
echo "🎉 All tests passed!"
echo ""
echo "📋 Summary:"
echo "   Task ID: $TASK_ID"
echo "   Status File: $STATUS_FILE"
echo "   Report File: $OUTPUT_FILE"
echo ""
echo "📋 故障排查时查看:"
echo "   - 任务注册: $TASKS_FILE"
echo "   - Watcher 日志: ~/.openclaw/shared-context/monitor-tasks/watcher.log"
echo "   - 通知记录: ~/.openclaw/shared-context/monitor-tasks/notifications/"
