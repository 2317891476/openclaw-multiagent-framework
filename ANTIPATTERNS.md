# Anti-Patterns 踩坑实录

> 从内部多 Agent 团队运营中提炼的真实踩坑案例。
> 每条都是"交了学费"后总结的——读完可以少走弯路。

---

## 1. 把 task-watcher 当聊天通道用

**症状**：Agent A 想让 Agent B "马上看一下"，于是往 `tasks.jsonl` 注册了一个 "task" 来传话。

**为什么错**：
- task-watcher 的轮询间隔是分钟级（通常 2-5 分钟），不是实时通道
- 注册的 task 没有 status_file → watcher 检测不到终态 → 永远不会通知
- 消息积压在 tasks.jsonl 中，变成永不收割的死任务

**正确做法**：
- 短任务 / 实时通信 → `sessions_send`（控制面）
- 长任务 / 异步执行 → `sessions_spawn` + task-watcher（异步回执面）
- 对外播报 → `message`（展示面）

**一句话**：watcher 是"回执系统"，不是"聊天工具"。

---

## 2. timeout 就是失败，疯狂重试

**症状**：`sessions_send` 返回 `timeout` 后，Agent 立刻用相同 `ack_id` 重发，导致对方收到 2-3 条重复消息。

**为什么错**：
- `timeout` ≠ 消息没送达。消息可能已入队，对方可能正在工作
- 相同 `ack_id` 重发会被对方收到多次（如果没有幂等处理）
- 带 `[Final]` 标签的消息重发尤其危险——可能触发重复结算或状态回滚

**正确做法**：
```
timeout → 视为 ambiguous success → 查路径/回执
  ├─ 有 ack_id → 禁止重发相同 ack_id
  ├─ 无 ack_id → 同内容最多重试 1 次
  └─ 是 [Final] → 绝不重发
```

**一句话**：timeout 时先调查，不要先重试。

---

## 3. 在 message 路径上跑内部协作

**症状**：Agent 之间的工作交接通过 Discord channel `message` 发送，结果因为 "mention gating" 或 channel 解析失败而丢消息。

**为什么错**：
- `message` 是对外播报通道（给人看的），没有回执机制
- Discord 的 mention gating 会静默丢弃未授权的消息
- 排查时无法确认"到底发没发出去"

**正确做法**：
```
内部协作 → sessions_send（有回执、有 ack_id、有 timeout 语义）
对外播报 → message（给人看的面板/通知）
```

**一句话**：`message` 是广播喇叭，不是对讲机。

---

## 4. 状态文件用错字段名

**症状**：Worker 写了 `{"status": "done"}`，watcher 检测不到终态，任务一直挂着。

**为什么错**：
- watcher 检测的是 `"state"` 字段，不是 `"status"`
- 终态值必须是 `completed` / `failed` / `timeout` / `cancelled`，不是 `done` / `success` / `finished`
- 这类 bug 不报错，只是静默不通知——最难排查

**正确 Schema**：
```json
{
  "state": "completed",
  "summary": "任务已完成"
}
```

**检查命令**：
```bash
# 验证你的状态文件格式
python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert 'state' in d, 'Missing field: state'
assert d['state'] in ('completed','failed','timeout','cancelled','started','in_progress','running'), f'Unknown state: {d[\"state\"]}'
print('OK:', d['state'])
" /path/to/status.json
```

**一句话**：用 `"state"` 不是 `"status"`，用 `"completed"` 不是 `"done"`。

---

## 5. 注册任务时 status_file 指向不存在的路径

**症状**：任务注册成功，Worker 也写了结果，但 watcher 说"文件不存在"。

**为什么错**：
- 注册时的 `status_file` 路径和 Worker 实际写入的路径不一致
- 常见原因：相对路径 vs 绝对路径、路径中有 `~` 但没展开、typo

**正确做法**：
```python
import os
status_file = os.path.expanduser("~/.openclaw/shared-context/job-status/my-task.json")
# 注册和写入使用同一个展开后的绝对路径
```

**一句话**：路径务必用 `os.path.expanduser()` 展开后再传。

---

## 6. 幽灵 Adapter：代码引用了但实际不存在

**症状**：verify 脚本通过了，但 bridge 运行时没有数据流入 `agent-requests/`。

**真实案例**：`AcpSessionCompletionAdapter` 在验证脚本中被引用，但实际代码文件不存在。导致整个 completion bridge 静默无输出——ACP session 已经完成，但 task_callback_bus 完全不知道。

**为什么危险**：
- 没有运行时错误（import 在 try/except 中）
- 验证脚本只检查了"名字存在"，没检查"功能可用"
- 问题只在 E2E 测试中才暴露

**正确做法**：
```python
# 验证 adapter 时，不只检查 import，还要检查功能
adapter = AcpSessionCompletionAdapter()
result = adapter.check()  # 必须实际调用
assert result is not None, "Adapter returned None — likely stub"
```

**一句话**：验证脚本要跑真实功能，不要只检查名字。

---

## 7. 复制 main 身份绕过路径错误

**症状**：Agent 发现联系不上 main，于是自己开了一个 "main 的 subagent" 代替 main 执行操作。

**为什么错**：
- 同一身份出现多个实例 → 状态分裂、决策矛盾
- 其他 Agent 不知道哪个 "main" 是真的
- 后续审计时无法追溯真实决策链

**正确做法**：
```
联系不上 main → 停止
  ├─ 检查路径是否正确（sessions_send vs message）
  ├─ 若路径正确但 session 不可达 → 等待主会话确认
  └─ 显式报告："session 不可达，暂停等待"
```

**一句话**：联系不上就等，不要自己"变成"对方。

---

## 8. JSONL 文件无限增长

**症状**：`tasks.jsonl` 越来越大（几 MB），watcher 启动变慢，`_read_all()` 扫描全文件耗时明显。

**为什么**：
- append-only 设计的代价——同一个 task 的每次更新都追加一行
- 100 个任务各更新 10 次 = 1000 行，但只有 100 个有效

**正确做法**：
```python
from store import TaskStore
store = TaskStore("tasks.jsonl")
saved = store.compact()
print(f"Reclaimed {saved} bytes")
```

定期 compact（建议：每天一次，或文件超过 1MB 时）：
```bash
# cron: 每天凌晨 compact
0 3 * * * cd /path/to/mini-watcher && python3 -c "from store import TaskStore; TaskStore('tasks.jsonl').compact()"
```

**一句话**：定期 compact，别让 JSONL 无限膨胀。

---

## 9. 没有给长任务设 expires_at

**症状**：Worker 挂了，任务永远停在 `in_progress`。没人注意到，直到手动巡检。

**为什么错**：
- 没有超时 = 没有兜底
- watcher 只检测状态变化，不会主动判断"太久没变化"

**正确做法**：
```python
from datetime import datetime, timedelta

task = Task(
    task_id="long-running-001",
    expires_at=(datetime.now() + timedelta(hours=2)).isoformat(),
    # ...
)
```

然后在 watcher 中检测 `task.is_expired()` 并自动标记为 timeout。

**一句话**：所有长任务必须设超时时间。

---

## 10. 通知发送失败但没有重试机制

**症状**：网络抖动导致 Slack/Discord 通知发送失败，任务状态正确更新了但没人收到通知。

**为什么**：
- `notify()` 返回 False 后，watcher 已经把 `last_notified_state` 更新了
- 下次轮询时，状态没变化 → 不会重新触发通知
- 结果：状态更新了，通知丢了

**正确做法**：
```python
def poll_one(task, store):
    new_state = check_status(task)
    if new_state and task.state_changed():
        ok = notify(task, old, new, summary)
        if ok:
            store.update(task.task_id, last_notified_state=new_state)
        else:
            # 不更新 last_notified_state → 下次还会重试
            log.warning("Notify failed, will retry next poll")
```

**一句话**：通知失败时不要更新 `last_notified_state`，让下次轮询重试。

---

---

## 11. 文件轮询做异步编排

**症状**：cron 每 5 分钟扫描 status_file 检测任务完成，watcher 报 degraded，notifications_sent: 0

**为什么是反模式**：
- 行业共识：文件轮询用于多 Agent 编排是反模式（Confluent, Zylos 等均有论述）
- 社区无人使用此方式：Lobster 用确定性 YAML、MFS Corp 用 Discord 实时通信
- 延迟高（最坏 5 分钟）、空轮询浪费、难以扩展

**正确做法**：
- 用 plugin hook (`before_tool_call`) 自动追踪任务
- 用 prompt 注入让 ACP 完成时主动 `sessions_send` 通知
- 或等 OpenClaw Core 修复 ACP notifyChannel (Issue #40272)

**一句话**：别轮询文件，让任务完成时主动通知你。

---

## 12. 文档约束代替系统约束

**症状**：AGENT_PROTOCOL.md 明确写了"必须用 wrapper"，但 Agent 仍然裸 spawn

**为什么是反模式**：
- LLM 的"肌肉记忆"指向 L1 原生工具 (`sessions_spawn`)
- 文档规则写在 AGENT_PROTOCOL.md 深处，LLM 注意力有限
- "请你记住做 X" ≠ "系统自动做 X"

**正确做法**：
- 用 `before_tool_call` plugin hook 自动拦截
- Agent 继续用 `sessions_spawn`（保留肌肉记忆）
- 系统透明地完成注册和回调注入

**一句话**：如果一个行为是强制的，它就不应该是可选的。

---

## 更新后的踩坑检查清单

部署前过一遍：

- [ ] 安装了 `spawn-interceptor` plugin？
- [ ] 内部协作用 `sessions_send`，不是 `message`？
- [ ] 有 `completion-listener` 在运行（cron 或 loop）？
- [ ] 长任务设了超时？
- [ ] timeout 处理是"先调查"而不是"先重试"？
- [ ] 没有用文件轮询做异步编排？
- [ ] 没有依赖文档约束让 Agent "记住"额外步骤？

---

*基于 2026-03-08 ~ 2026-03-12 内部团队运营经验整理*
*2026-03-12 更新：新增反模式 #11 (文件轮询) 和 #12 (文档约束)*
