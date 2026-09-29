# 小科架构说明

> 给想读懂代码的人。先看这张图，再按"一次消息的旅程"往下读。

---

## 一、四层结构

```
┌──────────────────────────────────────────────────────────────┐
│  交互层                                                       │
│  桌面 Web 三列工作台 · 手机流程卡 · 实时语音（QwenAudio）· 终端  │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP / SSE / WebSocket
┌───────────────────────────▼──────────────────────────────────┐
│  智能体层（web/agent/、web/agent_harness.py）                  │
│  · stream_agent     流式主循环（模型 ↔ 工具多轮）               │
│  · 工具兜底          白名单 / schema / 超时重试 / 熔断 / 步数上限 │
│  · Agent Harness     心跳、反思子智能体的编排                    │
└───────────────────────────┬──────────────────────────────────┘
                            │ 只暴露"工具名 + 参数"
┌───────────────────────────▼──────────────────────────────────┐
│  能力层（web/lab_tools*.py、web/tool_router.py）               │
│  55+ 插件式工具：计算 / 试剂 / 计时 / 知识库 / 储存库 / 方案 / 通知 │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  数据层（web/database/、data/）                                │
│  SQLite（会话/记录/知识库/储存库）· JSONL（留痕/事件）· 知识库文件 │
└──────────────────────────────────────────────────────────────┘
```

**核心边界**：模型只能通过"工具"接触业务；工具内部才碰状态和数据库。
模型负责**理解与建议**，程序负责**状态、权限与落盘**。

---

## 二、一次消息的旅程（trace_id 贯穿）

用户说一句话，系统内部是这样走的：

```
① 前端发送
   桌面：streaming_chat_v2.js → POST /chat/stream
   手机：mobile_cards.js → 同一后端

② stream_agent 接手（web/agent/core.py）
   生成 trace_id ──────────────────────────────┐
   组装上下文（_messages）                      │
   · INSTRUCTIONS（人格与纪律）                 │
   · policy（实验记录 / 对话 / 方案等模式策略）    │  trace.jsonl
   · _memory_context()（长期记忆）              │  每个节点写一行
   · build_harness_context()（当前实验状态）      │
                                               │
③ 循环：最多 12 轮                              │
   ├─ 调模型（带工具列表 = 核心工具 + 命中的 skill 组）
   ├─ 记录 intent 节点 ─────────────────────────┤
   ├─ 模型返回 tool_calls？                      │
   │   ├─ 否 → 输出正文，记录 generate 节点 ──────┤  结束
   │   └─ 是 → 记录 tool_select 节点 ────────────┤
   │        ├─ 工具名白名单校验（不通过 → 回灌错误让模型重选）
   │        ├─ 参数 schema 校验（不通过 → 回灌）
   │        ├─ 熔断检查（连续失败 3 次 → 拒绝执行）
   │        ├─ 超时执行（10s）+ 重试（2 次）
   │        ├─ 记录 tool_exec 节点 ──────────────┤
   │        └─ 结果回灌给模型，进入下一轮
   └─ 12 轮耗尽 → 记录 step_limit 节点，降级回复

④ 前端渲染
   [[LABCARD]] → 工具卡片（present_call / present_result 生成的统一视图）
   [[LABTHINK]] → 可折叠的思考行
   正文 → 聊天流 + 语音播报（voice_delivery 合同）
```

**为什么记 trace**：出了问题不用复现，`python -m scripts.trace_show <trace_id>` 直接回放每一步输入输出。

---

## 三、关键模块职责

### 智能体层

| 文件 | 职责 | 关键设计 |
|------|------|---------|
| `agent/core.py` | 三个入口：`stream_agent`（流式，主路径）、`run_agent`（非流式）、`_run_skill_agent`（模板/储存库专用） | 工具兜底在这里：`_valid_tool_names` / `_validate_tool_args` / `_circuit_broken` / `_execute_tool_with_timeout` |
| `agent_harness.py` | 心跳与反思循环：组装上下文 → 多轮工具 → 决定是否打扰用户 | `heartbeat_respond` / `reflection_respond` 作为终止工具；`notify=false` 静默 |
| `agent_loop.py` | `EmbeddedAgentRunner`（多轮工具循环）+ `MultiAgentRouter`（按任务类型选子智能体） | 参考 OpenClaw 的 agent loop |
| `harness_context.py` | 分层上下文组装：方案状态 / 实验状态 / 试剂流程 / 活跃实验 | 每部分独立格式化函数，缺数据不报错 |
| `compaction.py` | 超长会话压缩：超阈值 → 模型摘要 + 保留最近 tail | 阈值触发，摘要存 `conversation_compactions` |
| `tracing.py` | trace_id 生成、JSONL 写入、读取回放 | 写失败静默降级（打包环境只读目录） |

### 能力层（拆分后）

```
lab_tools_registry.py   @tool 注册机制 + 展示层（present_call/present_result）+ 共享状态
lab_tools.py            facade：导入各功能模块触发注册
├── lab_tools_project.py    通用项目/研发调研工具（只读）
├── lab_tools_protocol.py   实验方案（搜索/选择/创建/改步骤）
├── lab_tools_record.py     实验记录（record_observation）
├── lab_tools_time.py       时间/计时/时间引擎
├── lab_tools_reagent.py    试剂安全
├── lab_tools_kb.py         知识库检索（引物表等）
├── lab_tools_calc.py       分子量/比例/溶液计算
├── lab_tools_storage.py    储存库
├── lab_tools_community.py  社区
└── lab_tools_prep.py       试剂配置流程
```

**注册机制**：`@tool(name, description, parameters, kind, title, present, experiment_command)` 把函数写进 `_REGISTRY`。展示层读 `_REGISTRY` 生成卡片视图，不需要为每个工具写前端特例。

**动态注入**（`tool_router.py`）：不把 55 个工具全发给模型。
- `_CORE`：每次必带的 ~18 个核心工具
- `SKILL_GROUPS`：按关键词命中才注入（储存库/方案编辑/配方编辑/时间规划/实验管理）
- `activate_skill`：模型可主动申请解锁某组

### 数据层

| 存储 | 内容 |
|------|------|
| `database/turn_store.py` | 统一 Turn（请求/结果/消息块）与实验状态快照 |
| `database/crud.py` | 会话、记忆、实验 |
| `database/lab_record_store.py` | 实验记录（原始口述 + 结构化事件） |
| `api/knowledge_base.py` | 知识库表（`kb_tables` / `kb_rows` + FTS5） |
| `data/` | 知识库资产：试剂安全库、Protocol 库、配方库（外部 Protocol 见 LICENSE_LEDGER） |
| `logs/trace.jsonl` | 执行留痕 |

---

## 四、几个关键设计取舍

### 1. 为什么用"工具"而不是"让模型直接操作状态"

模型输出不稳定。让它直接改数据库，一个幻觉就能写坏数据。
所以：模型只能**提议**（调工具），工具内部做校验和落盘，结果回灌给模型看。

### 2. 为什么工具名要白名单 + schema 校验

模型会发明工具名、会漏参数。没有兜底时表现为"报错崩掉"或"静默什么都不做"。
现在的兜底链：**白名单 → schema → 熔断 → 超时重试 → 步数上限**，失败都回灌结构化错误让模型自己改。

### 3. 为什么限制轮数（12 轮）

防死循环。模型可能反复调同一个工具。12 轮后强制降级，用最后的工具结果兜底回复。

### 4. 为什么原始记录优先

模型的结构化推断**永不覆盖**原始口述。结构化失败时提示"原始记录已保存"，不谎称"已记录"。
这是实验场景的底线——数据可追溯比"看起来智能"重要。

### 5. 为什么上下文分层（harness_context）

把"当前实验状态""操作手顺""试剂流程""活跃实验"分开组装，各自独立容错。
好处：某一块查不到数据时不影响其他块，也不会把整个上下文撑爆。

### 6. 为什么用关键词检索而不是向量

知识库以表格为主（引物表、抗体表），查询多是**精确术语**（基因名、引物号、CAS）。
FTS5 / 子串匹配对这类查询更准，且零 embedding 成本、零模型依赖、离线可用。
（如果将来要支持论文全文语义检索，再引入 embedding 也不冲突。）

---

## 五、如何扩展

### 加一个工具

1. 找到对应功能模块（比如实验相关 → `lab_tools_protocol.py`）
2. 加一个 `@tool(...)` 装饰的函数，返回 dict 或 `PresentedToolResult`
3. 如果要进"实验模式可调用"集合，加 `experiment_command=True`
4. 如果它属于某个 skill 组，在 `tool_router.SKILL_GROUPS` 里登记
5. 跑测试：`python -m pytest tests/test_experiment_tool_command.py -q`（校验注册与目录派生）

### 加一个 skill 组

在 `tool_router.SKILL_GROUPS` 加一项：`description` + `keywords` + `tools`。模型看到 `activate_skill` 的枚举就会自动知道。

### 加一个心跳任务

在 `agent_harness.py` 的 `_build_tools` 和 `MultiAgentRouter`（`agent_loop.py`）部署一个新的 `task_kind`，参考 `heartbeat` / `reflection` 的写法。

---

## 六、调试与评测

```bash
# 回放某条 trace（bad case 排查）
python -m scripts.trace_show --list
python -m scripts.trace_show <trace_id>

# 固定回归集 + 运行统计
python -m scripts.eval_report
# 输出：任务成功率 / 工具调用正确率 / 平均步数 / P50 时延 / 平均 token / 降级率
```

## 七、测试

```bash
python -m pytest tests/ -q
```

- 全量 1500+ 测试
- `tests/conftest.py` 里有**隔离区**（QUARANTINED）：架构迁移后断言过时的测试集中登记并 skip，原因写在文件里。修复后从集合移除，不要直接删除。
