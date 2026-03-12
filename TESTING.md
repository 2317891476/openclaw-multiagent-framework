# Testing Guide

> 框架的测试架构遵循分层原则：每一层独立验证，向上组合。

---

## 测试架构

```
┌──────────────────────────────────────────────────────────┐
│                    End-to-End Demo                        │
│             demo.py — 完整生命周期验证                      │
│    注册 → 模拟Worker → Watcher轮询 → 状态检测 → 通知       │
└───────────────────────┬──────────────────────────────────┘
                        │ 依赖
┌───────────────────────┼──────────────────────────────────┐
│              Orchestration Layer Tests                     │
│         test_watcher.py — 轮询/检测/通知逻辑               │
│    check_status_file · notify · poll_once · 过期处理       │
└───────────┬───────────┬──────────────────────────────────┘
            │           │
┌───────────┴──┐  ┌─────┴──────────────────────────────────┐
│  Persistence │  │           Data Model Tests              │
│    Tests     │  │    test_models.py — 纯数据逻辑           │
│ test_store.py│  │  构造 · 谓词 · 序列化 · 边界条件          │
│ CRUD · 锁 ·  │  │  无I/O · 无副作用 · 毫秒级执行           │
│ compact ·    │  │                                         │
│ 容错         │  │                                         │
└──────────────┘  └─────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│              L2 Capability Tests                          │
│       test_l2_capabilities.py — 增强能力验证               │
│  ACK · Handoff · Deliverable · Writer · Bridge · Reflect  │
└──────────────────────────────────────────────────────────┘
```

### 设计理念

1. **模型层**（`test_models.py`）：纯逻辑测试，无文件 I/O，毫秒级完成。验证 Task/StateResult 的构造、谓词（is_terminal/is_expired/state_changed）、JSON 序列化往返、边界条件（无效日期、未知字段、中文内容）。

2. **持久层**（`test_store.py`）：文件 I/O 测试，每个 case 使用独立临时目录。验证 JSONL append-only 语义、文件锁正确性、compact 压缩行为、损坏数据容错。

3. **编排层**（`test_watcher.py`）：集成 models + store + I/O。验证状态文件解析、通知生成、轮询周期行为、过期处理、多任务并行、完整生命周期序列。

4. **L2 增强层**（`test_l2_capabilities.py`）：独立验证每个 L2 能力。ACK 守门（超时/重复/状态转换）、Handoff 模板格式、交付物三层结构、文件锁互斥、Follow-up 生成管线、反思转化管线。

---

## 运行测试

### 运行全部测试

```bash
# mini-watcher 核心测试（79 个）
cd examples/mini-watcher
python3 -m pytest tests/ -v

# L2 能力测试（35 个）
cd examples
python3 -m pytest tests/ -v
```

### 运行单个测试文件

```bash
python3 -m pytest tests/test_models.py -v      # 27 tests — 模型层
python3 -m pytest tests/test_store.py -v        # 30 tests — 持久层
python3 -m pytest tests/test_watcher.py -v      # 22 tests — 编排层
python3 -m pytest tests/test_l2_capabilities.py -v  # 35 tests — L2 增强层
```

### 运行单个测试类

```bash
python3 -m pytest tests/test_store.py::TestStoreCompact -v
python3 -m pytest tests/test_watcher.py::TestPollOnceSequence -v
```

### 不依赖 pytest（标准 unittest）

```bash
cd examples/mini-watcher
python3 -m unittest discover -s tests -v
```

---

## 测试覆盖

| 模块 | 测试文件 | 测试数 | 覆盖范围 |
|------|----------|--------|----------|
| `models.py` | `test_models.py` | 27 | 构造、谓词、序列化、边界 |
| `store.py` | `test_store.py` | 30 | CRUD、锁、compact、容错 |
| `watcher.py` | `test_watcher.py` | 22 | 检测、通知、轮询、过期、生命周期 |
| `l2_capabilities.py` | `test_l2_capabilities.py` | 35 | ACK、Handoff、Deliverable、Writer、Bridge、Reflection |
| **合计** | | **114** | |

### 关键测试场景

**模型层**：
- Task 序列化往返（JSON ↔ dict ↔ Task）
- 终态判断（4 种终态 + 2 种判断路径）
- 过期检测（过去/未来/无效格式/无过期时间）
- 中文内容序列化（ensure_ascii=False）

**持久层**：
- 重复注册防护（抛 ValueError）
- Append-only 语义验证（更新追加行而非覆盖）
- Compact 正确性（压缩后只保留最新版本）
- 损坏行容错（空行/无效 JSON/缺字段 → 跳过不崩溃）
- 路径展开（~ 正确展开为 home）

**编排层**：
- 完整生命周期（registered → started → in_progress → completed）
- 相同状态不重复通知（幂等性）
- 过期任务自动标记 timeout
- 已终止任务不再轮询
- 多任务独立检测
- 缺失/损坏状态文件优雅处理

**L2 增强层**：
- ACK 超时检测（模拟时间推进）
- ACK 去重（已确认的不可重复确认）
- Handoff 三段式格式（request/ack/final）
- 文件锁创建和清理
- Follow-up 追加写入（同日多任务合并）
- 反思→Follow-up 管线端到端

---

## 添加新测试

### 约定

1. **文件命名**：`test_{module}.py`
2. **类命名**：`Test{Feature}{Aspect}`（如 `TestStoreCompact`）
3. **方法命名**：`test_{behavior_under_test}`（如 `test_compact_preserves_latest_state`）
4. **隔离**：每个测试方法使用独立临时目录（`setUp` 中 `tempfile.mkdtemp`）
5. **无外部依赖**：只使用 Python 标准库

### 添加 mini-watcher 测试

```python
# tests/test_my_feature.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from store import TaskStore

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        self.work_dir = tempfile.mkdtemp()
        self.store = TaskStore(os.path.join(self.work_dir, "tasks.jsonl"))

    def test_something(self):
        ...
```

### 添加 L2 能力测试

```python
# examples/tests/test_my_l2.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l2_capabilities import AckGate

class TestMyL2Feature(unittest.TestCase):
    def test_something(self):
        ...
```

---

## CI 集成

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Run mini-watcher tests
        run: |
          cd examples/mini-watcher
          python -m pytest tests/ -v
      - name: Run L2 capability tests
        run: |
          cd examples
          python -m pytest tests/ -v
```

---

*114 个测试，零外部依赖，<0.2 秒完成*
