# OpenClaw Multi-Agent + iFlow Runner 最小使用手册

> 适用于当前这套：OpenClaw + spawn-interceptor + `examples/subagent-iflow-runner/`

## 这套方案是什么

核心思路：

- **OpenClaw** 负责任务编排
- **spawn-interceptor** 负责生命周期追踪
- **iFlow runner** 负责执行长任务

也就是：

> OpenClaw 管调度，spawn-interceptor 管跟踪，iFlow runner 管执行。

---

## 关键路径

### 仓库路径

```bash
/home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
```

### iFlow runner 路径

```bash
examples/subagent-iflow-runner/
```

### shared-context 路径

```bash
/home/illya/.openclaw/shared-context
```

---

## 最常用命令

### 1. 直接跑一个 iFlow 子任务

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
bash examples/subagent-iflow-runner/run_v1.sh "分析这个仓库" repo-summary
```

含义：
- `"分析这个仓库"`：任务内容
- `repo-summary`：本次任务 label

---

### 2. 直接调用底层 runner

```bash
node examples/subagent-iflow-runner/runner.js \
  --cwd "$PWD" \
  --label repo-summary \
  --task "分析这个仓库"
```

---

### 3. 检查插件是否已加载

```bash
openclaw plugins list | grep -A2 -B1 spawn-interceptor
```

你要看到：

```text
loaded
```

---

### 4. 检查 gateway 状态

```bash
systemctl --user is-active openclaw-gateway
```

正常结果：

```text
active
```

---

## 任务结果去哪里看

每次 adapter 执行都会生成一个任务目录，位置类似：

```bash
runs/JOB-001/task-001
```

### 最重要的文件

#### `status.json`

查看任务当前状态：

```bash
cat tmp/iflow-runs/<run-dir>/status.json
```

重点字段：
- `state`
- `failureKind`
- `timedOut`
- `lastActivityAt`

#### `final-summary.json`

查看最终摘要：

```bash
cat tmp/iflow-runs/<run-dir>/final-summary.json
```

重点字段：
- `state: completed | failed`
- `exitCode`
- `error`
- `stdoutTail`
- `stderrTail`

#### `final-report.md`

查看人类可读报告：

```bash
cat tmp/iflow-runs/<run-dir>/final-report.md
```

#### `iflow.stdout.log`

查看主要输出：

```bash
cat tmp/iflow-runs/<run-dir>/iflow.stdout.log
```

#### `iflow.stderr.log`

查看执行信息/报错：

```bash
cat tmp/iflow-runs/<run-dir>/iflow.stderr.log
```

---

## 怎么判断成功/失败

### 成功

`final-summary.json` 中：

```json
"state": "completed"
```

通常同时有：

```json
"exitCode": 0
```

### 失败

```json
"state": "failed"
```

重点看：
- `failureKind`
- `error`
- `stderrTail`

---

## 常见失败类型

### 1. iFlow 认证问题

现象：
- iFlow 没输出
- stderr 中有认证错误

先试：

```bash
iflow --help
iflow -y -p "只回复 OK"
```

如果这里都不通，先修 iFlow 登录态。

### 2. stall timeout

现象：

```json
"failureKind": "timeout"
```

并且 reason 类似：

```text
No activity for ...
```

说明：
- 进程启动了
- 但长时间没输出、没文件活动
- 被 watchdog 判定卡住

可以调大超时参数：

```bash
SUBAGENT_IFLOW_TIMEOUT_S=1800 \
SUBAGENT_IFLOW_IDLE_TIMEOUT_S=300 \
SUBAGENT_IFLOW_STALL_GRACE_S=120 \
 bash examples/subagent-iflow-runner/run_v1.sh "你的任务" long-run
```

### 3. 插件没加载

```bash
openclaw plugins list | grep spawn-interceptor
```

如果不是 `loaded`，说明插件没生效。

---

## 推荐使用姿势

### 方式 A：先本地直接跑 runner

适合：
- 验证任务
- 调试 iFlow
- 看 run-dir 产物

```bash
bash examples/subagent-iflow-runner/run_v1.sh "任务内容" label
```

这是目前最稳的入口。

### 方式 B：作为 OpenClaw 多代理框架的一部分使用

适合：
- 多任务编排
- 子代理协作
- 生命周期追踪

这时：
- OpenClaw 负责编排
- spawn-interceptor 负责跟踪
- iFlow runner 负责真正执行长任务

---

## 最短工作流

### 跑任务

```bash
cd /home/illya/.openclaw/workspace/repos/openclaw-multiagent-framework
JOB_ID=JOB-001 AGENT_TYPE=generic bash adapters/iflow/run_v1.sh "分析这个仓库" task-001
```

### 看结果

```bash
cat tmp/iflow-runs/<run-dir>/final-summary.json
cat tmp/iflow-runs/<run-dir>/final-report.md
```

### 看日志

```bash
cat tmp/iflow-runs/<run-dir>/iflow.stdout.log
cat tmp/iflow-runs/<run-dir>/iflow.stderr.log
```
report.md
```

### 看日志

```bash
cat tmp/iflow-runs/<run-dir>/iflow.stdout.log
cat tmp/iflow-runs/<run-dir>/iflow.stderr.log
```
