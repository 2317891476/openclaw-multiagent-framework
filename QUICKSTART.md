# OpenClaw 多 Agent 协作框架 — 快速开始指南

<!-- 阅读顺序: 2/5 -->
<!-- 前置: README.md -->
<!-- 后续: AGENT_PROTOCOL.md -->

> Version: 2026-03-12-v2
> 适用对象：已有 OpenClaw 部署，想要引入多 Agent 协作规范

---

## 前置条件

| 依赖 | 版本 | 检查命令 |
|------|------|----------|
| Python | 3.10+ | `python3 --version` |
| OpenClaw Gateway | 运行中 | `launchctl list \| grep openclaw` |
| 目录权限 | 可写 | `mkdir -p ./shared-context && touch ./shared-context/.test` |

**无外部依赖**——框架和示例全部基于 Python 标准库。

---

## 5 分钟快速部署

### 步骤 1：创建必要目录（1 分钟）

```bash
export FRAMEWORK_HOME=${FRAMEWORK_HOME:-~/.openclaw}

mkdir -p $FRAMEWORK_HOME/shared-context/{job-status,monitor-tasks,dispatches,intel,followups,archive/protocol-history}
```

### 步骤 2：复制框架文档（1 分钟）

```bash
export FRAMEWORK_HOME=${FRAMEWORK_HOME:-~/.openclaw}

git clone https://github.com/lanyasheng/openclaw-multiagent-framework.git
cp -r openclaw-multiagent-framework/* $FRAMEWORK_HOME/shared-context/
```

### 步骤 3：运行端到端演示（1 分钟）

```bash
cd openclaw-multiagent-framework/examples/mini-watcher
python3 demo.py
```

你应该看到完整的生命周期：

```
==============================================================
  Mini-Watcher End-to-End Demo
==============================================================

[1/3] Task registered: demo-001
[2/3] Background worker started (will take ~12s)
[3/3] Watcher polling every 2 seconds...
------------------------------------------------------------
22:42:01 [watcher] INFO [UPDATE] [demo-001] registered -> started | Worker initialized
22:42:05 [watcher] INFO [UPDATE] [demo-001] started -> in_progress | Analyzing data...
22:42:11 [watcher] INFO [OK] [demo-001] in_progress -> completed | Analysis complete
------------------------------------------------------------

Task reached terminal state: completed
```

> 这不是模拟脚本——`demo.py` 使用了和生产环境同构的 JSONL 存储、文件锁、状态检测和通知机制。

### 步骤 4：配置你的 Agent 团队（2 分钟）

编辑 `$FRAMEWORK_HOME/shared-context/AGENT_PROTOCOL.md`，替换为你的团队配置：

```markdown
## 你的 Agent 团队

| Agent | 职责 | Channel |
|-------|------|---------|
| main | 协调与决策 | #general |
| research | 信息搜集 | #research |
| writing | 内容创作 | #writing |
| review | 质量审查 | #review |
```

---

## 核心概念：3 分钟理解

```
注册任务  →  Worker 执行  →  Watcher 轮询  →  检测状态变化  →  通知
  │              │              │                │              │
  ▼              ▼              ▼                ▼              ▼
tasks.jsonl   status.json   poll_once()    state_changed?   notify()
```

**整个框架围绕一个核心循环**：
1. 任何 Agent 注册一个任务（写入 `tasks.jsonl`）
2. 后台 Worker 执行任务，把进度写入状态文件（JSON）
3. Watcher 定期轮询所有活跃任务的状态文件
4. 检测到状态变化时，触发通知
5. 任务到达终态（completed/failed/timeout）后从监控中移除

`examples/mini-watcher/` 用 ~300 行 Python 实现了这个完整循环。

---

## 端到端可运行示例

### 示例 1：最小 Watcher（推荐先跑这个）

```bash
cd examples/mini-watcher
python3 demo.py
```

包含 4 个文件，零外部依赖：

| 文件 | 作用 |
|------|------|
| `models.py` | Task 和 StateResult 数据模型 |
| `store.py` | JSONL 持久化 + 文件锁 |
| `watcher.py` | 轮询循环 + 状态检测 + 通知 |
| `demo.py` | 端到端演示（注册 → 模拟执行 → 监控） |

详见 [examples/mini-watcher/README.md](examples/mini-watcher/README.md)。

### 示例 2：协议消息交互

验证 request/ACK/final 三段式消息格式：

```bash
python3 examples/protocol_messages.py
```

### 示例 3：状态机

独立运行状态机，理解任务生命周期中合法的状态转换：

```bash
python3 examples/task_state_machine.py
```

### 示例 4：手动注册 + 监控一个真实任务

```bash
cd examples/mini-watcher

# 1. 注册一个任务
python3 -c "
from models import Task
from store import TaskStore
t = Task(task_id='my-task', owner='main', subject='测试任务',
         status_file='/tmp/my-task-status.json')
TaskStore('/tmp/my-tasks.jsonl').register(t)
print('注册完成:', t.task_id)
"

# 2. 模拟 Worker 写入状态
echo '{"state": "completed", "summary": "分析完成"}' > /tmp/my-task-status.json

# 3. 运行一次 Watcher 检查
python3 watcher.py --once --tasks-file /tmp/my-tasks.jsonl
```

---

## 状态文件 Schema

### 最小状态文件

```json
{
  "state": "completed",
  "summary": "任务已完成"
}
```

### 完整 Schema

```json
{
  "task_id": "task-YYYYMMDD-NNN",
  "state": "completed",
  "summary": "简短描述（用于通知）",
  "report_file": "报告文件路径",
  "error": "错误信息（如果有）",
  "started_at": "2026-03-12T12:00:00",
  "completed_at": "2026-03-12T12:05:00",
  "metadata": {}
}
```

### 状态值

| 状态 | 终态？ | 说明 |
|------|--------|------|
| `started` | 否 | 任务已启动 |
| `running` / `in_progress` | 否 | 执行中 |
| `completed` | **是** | 成功完成 |
| `failed` | **是** | 执行失败 |
| `timeout` | **是** | 超时终止 |
| `cancelled` | **是** | 手动取消 |

---

## 作为 Cron 运行 Watcher

```bash
# 每 3 分钟轮询一次
*/3 * * * * cd /path/to/examples/mini-watcher && python3 watcher.py --once --tasks-file ~/.openclaw/shared-context/monitor-tasks/tasks.jsonl >> /var/log/watcher.log 2>&1
```

持续轮询模式：

```bash
python3 watcher.py --loop --interval 30 --tasks-file ~/.openclaw/shared-context/monitor-tasks/tasks.jsonl
```

---

## 自定义扩展

### 替换通知后端

`watcher.py` 中的 `notify()` 函数默认写 JSON 文件。替换成任何你需要的：

```python
def notify(task, old_state, new_state, summary=""):
    # Slack
    requests.post(WEBHOOK, json={"text": f"[{task.task_id}] {old_state} → {new_state}"})
    # 或 Discord / 邮件 / sessions_send / ...
    return True
```

### 替换状态检测源

默认读 JSON 文件。替换 `check_status_file()` 可接入 API、数据库等：

```python
def check_github_pr(task):
    resp = requests.get(f"https://api.github.com/repos/.../pulls/{task.metadata['pr']}")
    merged = resp.json().get("merged", False)
    return StateResult(state="completed" if merged else "open", terminal=merged)
```

---

## 故障排查

### 任务完成但没收到通知

```bash
export FRAMEWORK_HOME=${FRAMEWORK_HOME:-~/.openclaw}

# 1. 任务是否注册？
grep "your_task_id" $FRAMEWORK_HOME/shared-context/monitor-tasks/tasks.jsonl

# 2. 状态文件是否存在且格式正确？
cat $FRAMEWORK_HOME/shared-context/job-status/your_task_id.json
# 必须包含 {"state": "completed"} 而不是 {"status": "done"}

# 3. Watcher 日志
tail -50 $FRAMEWORK_HOME/shared-context/monitor-tasks/watcher.log

# 4. 通知文件是否已生成？
ls $FRAMEWORK_HOME/shared-context/monitor-tasks/notifications/ | grep your_task_id
```

### 常见错误

| 症状 | 原因 | 修复 |
|------|------|------|
| `ModuleNotFoundError` | 不在 mini-watcher 目录 | `cd examples/mini-watcher` |
| 任务未检测到 | status_file 路径不对 | 检查注册时的 `status_file` 是否指向实际文件 |
| state 检测不到终态 | 字段名错误 | 用 `"state"` 不是 `"status"`；值用 `"completed"` 不是 `"done"` |
| 重复通知 | Watcher 未更新 last_notified_state | 确认 store 写入成功（检查文件锁） |

---

## 首次派单测试

### 短任务（< 10 秒）

```text
[Request] ack_id=test-001 | topic=测试短任务 | ask=回复"收到" | due=1 分钟

预期流程：
1. Agent 回复 [ACK] ack_id=test-001 state=confirmed
2. Agent 执行
3. Agent 回复 [Final] ack_id=test-001 state=final
```

### 长任务（> 10 秒）

```text
[Request] ack_id=test-002 | topic=测试长任务 | ask=执行后台任务 | due=5 分钟

预期流程：
1. 接收方回复 ACK
2. 注册 task-watcher
3. sessions_spawn(mode="run") 启动后台任务
4. 任务完成后写 status_file + report_file
5. Watcher 推送 terminal 通知
```

---

## 验证清单

- [ ] `python3 examples/mini-watcher/demo.py` 运行成功
- [ ] 所有 Agent 已阅读 AGENT_PROTOCOL.md
- [ ] 必要目录已创建（`shared-context/{job-status,monitor-tasks,...}`）
- [ ] 首次短任务派单测试通过
- [ ] 首次长任务异步测试通过
- [ ] Watcher cron/loop 已配置
- [ ] 团队配置已更新

---

## 下一步

1. **跑完 demo** → 理解核心循环
2. **阅读完整协议** → [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md)
3. **理解架构** → [ARCHITECTURE.md](ARCHITECTURE.md)
4. **能力分层** → [CAPABILITY_LAYERS.md](CAPABILITY_LAYERS.md)（L1/L2/L3 区分）
5. **扩展 Watcher** → 替换 notify/check 函数，接入你的通知后端

---

*最后更新：2026-03-12*
