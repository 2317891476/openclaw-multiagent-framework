# 贡献指南

> Version: 2026-03-12-v2

## 贡献范围

当前仓库包含：

| 类型 | 路径 | 说明 |
|------|------|------|
| **Plugin 代码** | `plugins/spawn-interceptor/` | Node.js OpenClaw plugin |
| **Python 工具** | `examples/completion-relay/` | 完成通知监听器 |
| **Python 演示** | `examples/l2_capabilities.py` | L2 能力参考实现 |
| **单元测试** | `examples/*/tests/` | 50 个测试用例 |
| **协议文档** | `*.md` | 多 Agent 协作规范 |

欢迎对以上所有内容提 PR。

---

## 如何贡献

### 1. Fork & Clone

```bash
git clone https://github.com/<your-fork>/openclaw-multiagent-framework.git
cd openclaw-multiagent-framework
```

### 2. 开发

- **Plugin 修改**：编辑 `plugins/spawn-interceptor/index.js`
- **Listener 修改**：编辑 `examples/completion-relay/completion_listener.py`
- **文档修改**：编辑对应 `.md` 文件

### 3. 测试

```bash
# completion-relay 测试
cd examples/completion-relay && python3 -m pytest tests/ -v

# L2 能力测试
cd examples && python3 -m pytest tests/test_l2_capabilities.py -v
```

### 4. 提交

- **Commit 格式**：`<type>: <description>`
  - `feat:` 新功能
  - `fix:` Bug 修复
  - `docs:` 文档更新
  - `test:` 测试补充
  - `refactor:` 重构
- **PR 描述**：说明改了什么、为什么改、如何验证

---

## 代码规范

### Python

- Python 3.10+
- 仅使用标准库（无外部依赖）
- Type hints 推荐
- docstring 推荐

### Node.js (Plugin)

- CommonJS（`module.exports`）
- 遵循 OpenClaw plugin API（`register(api)` 导出）
- 无外部 npm 依赖

### 文档

- Markdown 格式
- 包含 `Version:` 标记
- 代码块指定语言

---

## 反馈

- **Bug 报告**：GitHub Issues，包含复现步骤
- **功能建议**：GitHub Issues，包含使用场景
- **问题讨论**：GitHub Discussions
