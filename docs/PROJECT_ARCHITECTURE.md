# asr_demo 项目架构设计文档

## 一、项目概览

**asr_demo** 是一个语音驱动的实验记录助手。实验人员用自然语言口述操作步骤（"将溶液加热到60摄氏度"、"加入5毫升试剂"），系统通过 ASR 转录、LLM 结构化理解、追问机制补齐缺失字段，最终将结构化实验记录持久化为 JSONL 证据文件。

当前阶段：**文本终端交互**，无 TTS 语音输出（P3 远期规划）。

> 2026-08-12 实现状态说明：统一理解链已经在真实会话中接管主要处理，但代码仍保留
> shadow 命名、双 flag 和旧 `SegmentProcessor.submit()` 回退路径。因此下图同时包含
> 当前过渡实现和目标边界，不能把它理解为清理已经完成。

---

## 二、总体架构哲学

### 2.1 设计原则

| 原则 | 含义 | 为什么 |
|---|---|---|
| **数据不可变性** | 跨模块边界的合同全部用 `frozen=True` dataclass，构造时校验 | 一旦通过校验，下游可以无条件信任；避免"半成品"数据在模块间传播 |
| **纯逻辑与副作用分离** | Planner/Acceptor 纯计算，不访问文件、网络、状态机 | 可独立单元测试；行为可预测；不会因为外部资源状态产生意外 |
| **协议注入 + 工厂** | 业务代码依赖 `Protocol`，工厂函数创建具体实现 | 测试时可替换 Fake；真实后端更换不影响业务逻辑 |
| **失败降级，不崩溃** | LLM 调用失败 → 降级为 NOTE 事件，不抛异常中断会话 | 实验人员正在做实验，崩了就是数据丢失 |
| **先存原始数据，后推断** | ASR 原文先写入 JSONL，LLM 结构化结果后写入 | 原始证据永远可回溯；模型推断错误不会覆盖原始事实 |
| **版本化证据格式** | ASRResult v2 可读 v1，但只写 v2 | 格式演进不破坏历史数据 |

### 2.2 分层架构

```
┌─────────────────────────────────────────────┐
│  main.py  —— 组合根 + 会话循环               │
│  负责：创建对象、连接依赖、控制主循环          │
├─────────────────────────────────────────────┤
│  src/core/  —— 领域逻辑层                      │
│  纯数据合同 + 纯规划器 + 状态管理              │
│  不访问文件、网络、麦克风、模型               │
├─────────────────────────────────────────────┤
│  src/asr/   │ src/llm/   │ src/audio/       │
│  src/wakeword/          │ src/storage/      │
│  基础设施层 —— 有副作用的适配器               │
└─────────────────────────────────────────────┘
```

**核心约束**：领域层（`src/core/`）不导入基础设施层的具体实现。领域层的 Planner、Acceptor、Coordinator 只操作不可变数据合同，副作用由 `main.py` 和 Executor 在边界执行。

---

## 三、数据流全景

### 3.1 完整链路

```
用户说话
  │
  ▼
WakeWordDetector  ──→  "小科小科" 唤醒
  │
  ▼
VadAudioRecorder  ──→  Silero VAD + 0.5s 预录制 → vad_segment_*.wav
  │
  ▼
SenseVoiceBackend  ──→  FunASR SenseVoiceSmall → ASRResult (v2 证据)
  │
  ▼
InteractionCommandParser  ──→  精确规则匹配
  │                              ├─ 控制命令 → 快速路径（零 LLM）
  │                              └─ 其他文本 → 进入统一理解
  ▼
UnifiedUnderstandingRouter
  │                              ┌─ experiment  → 实验记录链路
  ├─ UnifiedUnderstandingProcessor (一次 LLM) ──┼─ control     → 风险策略与控制候选
  │                              └─ uncertain   → 弃权，不伪装成事实
  ▼
UnifiedDispatchPlanner  ──→  纯规则规划，产出 DispatchPlan
  │
  ▼
采用合同 / 当前 main 过渡接线  ──→  副作用边界：
  │                     - 写入 ASR 到 JSONL
  │                     - 结构化事件写入 JSONL
  │                     - 更新 ReplyCoordinator 状态
  ▼
ReplyCoordinator  ──→  管理待确认问题
  │                     - 追问缺失字段
  │                     - 确认 ASR 误识别
  │                     - 版本守卫防并发冲突
  ▼
终端输出（未来：TTS 语音输出）
```

### 3.2 当前实现与目标架构的差距

| 差距 | 当前表现 | 目标 |
|---|---|---|
| 配置不变量 | 两个 shadow flag 可形成非法组合 | 配置加载时拒绝非法组合，最终删除过渡 flag |
| 证据提交顺序 | 部分澄清动作可能先改内存、后写 ASR | 统一采用 prepare → persist → commit |
| 会话上下文 | 新链没有传入或更新 `SessionContext` | 每段读取提交前快照，事件落盘成功后更新上下文 |
| 执行边界 | main、observer、executor 共同承担过渡接线 | main 只组合依赖，正式执行器负责原子提交 |
| 错误恢复 | 唤醒/会话异常统一立即重试 | 区分暂时性与不可恢复错误，增加退避和退出边界 |

这些问题不会否定已有合同设计，但必须在接入查询、安全或 RAG 前修复，否则新能力会继承
不一致的证据顺序和空会话上下文。

### 3.3 三条处理路径

| 路径 | 触发条件 | LLM 调用 | 示例 |
|---|---|---|---|
| **精确命令快速路径** | 文本匹配到控制命令词表 | 0 次 | "结束实验记录"、"问题1 60度" |
| **统一理解路径** | 文本不是控制命令 | 1 次 | "将溶液加热到60摄氏度" |
| **降级路径** | LLM 调用失败或格式非法 | 0 次有效 | 网络超时 → NOTE 事件 |

---

## 四、模块职责与设计决策

### 4.1 `src/asr/` — 语音识别层

**核心决策：Protocol 隔离 + 版本化证据格式**

```python
# 业务代码只依赖这个协议，不导入 FunASR
class ASRBackend(Protocol):
    def recognize(self, audio_path, *, language="auto") -> ASRResult: ...
```

**ASRResult v2 的关键区分**：
- `asr_transcript`：经过去情绪、去标点后处理的可信转录文本——**全链路消费这个字段**
- `asr_model_raw_text`：模型原始输出（含情绪标签如 `<|HAPPY|>`）——**仅用于调试回溯**

**为什么这样设计**：
- SenseVoice 的 `rich_transcription_postprocess` 会做情绪标签转换和 ITN（逆文本归一化），结果才是"用户实际说的内容"
- 保留原始输出是为了防止后处理 bug 导致信息丢失——出问题时可以回溯
- v1/v2 共存读写保证了历史数据不会被新代码破坏

### 4.2 `src/llm/` — 模型访问层

**核心决策：两代处理器共存 + 统一路由 + 降级策略**

**旧链（`ExperimentLLMProcessor`）**：
- 两次 LLM 调用：`analyze_segment` → `summarize`（可选）
- 通过 `SegmentProcessor` → `SessionProcessingQueue` 在后台单线程执行
- 优点：经过大量验收，稳定可靠
- 缺点：两次调用延迟高；分析和控制命令分离，需要额外协调

**新链（`UnifiedUnderstandingProcessor` + `UnifiedUnderstandingRouter`）**：
- **一次 LLM 调用**同时完成：意图分类 + 实体提取 + 控制命令识别
- `UnifiedUnderstandingRouter.route()` 决策逻辑：
  1. 先用 `InteractionCommandParser` 做精确规则匹配（零 LLM）
  2. 匹配到控制命令 → 快速路径返回
  3. 没匹配到 → 调用一次 `UnifiedUnderstandingProcessor`
- 输出严格三选一：`experiment` XOR `control` XOR `uncertain`

**为什么从两次调用改为一次**：
- 减少延迟：一次 LLM 往返替代两次
- 降低不一致风险：分析和意图分类在同一上下文中完成
- 降低成本：token 消耗减半

**降级策略**：
- `OpenAICompatibleLLMClient` 只在 429/5xx/超时 时重试
- 最终失败 → `UnavailableLLMClient` 兜底
- 上层 `UnifiedUnderstandingProcessor.understand()` 捕获所有异常 → `build_degraded_understanding()` 生成 NOTE 事件
- **核心原则：LLM 挂了，实验记录不丢**

### 4.3 `src/core/` — 领域逻辑层

这是项目架构最密集的部分，26 个文件遵循严格的职责分离。

#### 4.3.1 意图识别与风险策略

**三层识别机制**：

```
Layer 1: InteractionCommandParser (精确规则，零 LLM)
  ├─ 硬编码词表匹配（"结束实验记录" → END_SESSION）
  ├─ 正则模式匹配（"问题3 60度" → TARGETED_ANSWER）
  └─ 安全前缀/后缀匹配（防误触发："跳过过滤步骤" ≠ DEFER）

Layer 2: IntentClassifier (语义分类，可选 LLM)
  └─ 对 Layer 1 无法匹配的文本做意图分类

Layer 3: UnifiedUnderstandingProcessor (统一 LLM)
  └─ 同时完成意图 + 实体 + 控制分支识别
```

**IntentPolicy — 风险分级策略**：

| 意图类型 | 风险等级 | 精确规则命中 | LLM 候选 |
|---|---|---|---|
| NORMAL | NONE | → 实验链路 | → 实验链路 |
| REVIEW_PENDING | LOW | → 需要上下文 | → 需要上下文 |
| DEFER_CURRENT | MEDIUM | → 需要上下文 | 不可逆 → 不执行 |
| AFFIRM/DENY | MEDIUM | → 需要上下文 | 不可逆 → 不执行 |
| TARGETED_ANSWER | MEDIUM | → 需要上下文 | 不可逆 → 不执行 |
| END_SESSION | HIGH | → 直接执行 | → **必须二次确认** |

**为什么这样设计**：
- 精确规则优先：能确定的事不浪费 LLM 调用，且不会产生 LLM 幻觉
- 风险越高，证据要求越严格：HIGH 风险操作即使是 LLM 候选也要用户确认
- 可逆性影响决策：可逆操作允许语义容错，不可逆操作必须更谨慎

#### 4.3.2 分派系统

**UnifiedDispatchPlanner** — 纯规则规划器：

```
UnifiedRouteResult
  │
  ▼
UnifiedDispatchPlanner.plan()
  │
  ├─ 降级      → DEGRADED_NOTE     (保存口述但不结构化)
  ├─ 弃权      → ABSTENTION        (模型说不理解，不伪装)
  ├─ 实验理解  → EXPERIMENT_PIPELINE (进入结构化存储)
  ├─ 需要上下文 → CLARIFICATION_CONTEXT (等用户回答追问)
  ├─ 结束执行  → END_SESSION_EXECUTION (精确命令，直接结束)
  ├─ 结束确认  → END_SESSION_CONFIRMATION (LLM候选，二次确认)
  └─ 不执行    → ABSTENTION        (证据不足)
```

**关键设计**：
- Planner 是纯函数，不持有任何状态、文件句柄、网络连接
- 产出 `UnifiedDispatchPlan` 后，由 `DispatchExecutor` 执行副作用
- 每个 destination 对应唯一的最小权限（`UnifiedDispatchPermission`）——下游只能做分派允许的事

#### 4.3.3 追问协调系统

**ReplyCoordinator** — 会话级追问状态管理：

```
ingest_analysis()
  ├─ 提取已提供字段 → 自动填充旧问题的 missing_fields
  ├─ 需要追问 → 注册新的 PendingClarification
  └─ 确认 ASR 推测 → 标记旧问题已确认

pop_next_reply()
  └─ 按段号顺序返回最早的未播报问题

prepare_confirmation() → 外部保存 → commit_confirmation()
  └─ 两阶段提交 + 版本守卫，防止并发冲突
```

**PendingClarification 的生命周期**：

```
ACTIVE ──→ DEFERRED ──→ ACTIVE (重新激活)
  │           │
  ├───────────┼──→ RESOLVED (字段补齐或确认)
  │           │
  └───────────┴──→ RESOLVED (过期)
```

**为什么需要版本守卫（revision）**：
- `supply_fields`、`defer`、`confirm` 每次操作都会 `revision += 1`
- 外部调用者必须先 `prepare_confirmation()` 获取 `expected_revision`，保存成功后再 `commit_confirmation()`
- 如果两次操作之间状态被其他路径修改，`commit` 会因版本不匹配而拒绝
- 防止：用户口头回答和 LLM 自动提取同时修改同一个问题的状态

### 4.4 `src/audio/` — 音频采集层

**核心决策：VAD + 预录制缓冲区**

```
VadAudioRecorder:
  ┌──────────────────────────────────────────┐
  │  PreRollBuffer (0.5s, deque of float32)  │
  │  持续写入，始终保持最近 0.5s 音频          │
  └──────────────────────────────────────────┘
                    │
                    ▼
  Silero VAD (sherpa-onnx, threshold=0.25)
                    │
        ┌───────────┼───────────┐
        ▼                       ▼
   语音开始                 语音结束 (静音 > 2s 或 超过 30s)
        │                       │
        └───────┬───────────────┘
                ▼
  TimelineSpeechAssembler
  ├─ 从预录制缓冲区取 0.5s 前置音频
  ├─ 验证样本重叠（防数据丢失）
  └─ 拼接为完整 vad_segment_*.wav
```

**为什么需要预录制缓冲区**：
- VAD 检测有固有延迟——当它判断"语音开始"时，第一个音素可能已经过去了
- 0.5s 预录制确保句首不被截断，对中文短指令（如"加热"）尤为重要
- `TimelineSpeechAssembler` 验证重叠样本数，防止拼接时出现音频间隙

### 4.5 `src/storage/` — 持久化层

**三种 JSONL 存储**：

| 存储 | 文件 | 内容 |
|---|---|---|
| `ASRResultStore` | `results/asr_segments.jsonl` | 原始转录证据 |
| `ExperimentEventStore` | `results/experiment_events.jsonl` | 结构化实验事件 |
| `ConfirmationStore` | `results/experiment_confirmations.jsonl` | 确认/答复记录 |

**共同设计**：
- 原子追加：先写临时文件，再替换原文件
- `ConfirmationStore` 写入前去重（扫描已有记录）
- 所有写入由 `main.py` 控制时序，存储层自身不做业务判断

---

## 五、新旧链路过渡策略

### 5.1 当前状态：统一链已接管，影子过渡代码待清理

```
用户口述
  │
  ├──→ 当前正式路径：统一理解 → 采用合同 → main 过渡写入
  │      └─ 真实会话已验证零旧 LLM 重复调用
  │
  └──→ 仍保留的回退代码：SegmentProcessor → SessionProcessingQueue
         └─ 待删除（INTENT-02-CLEANUP-SUBMIT-01），不再作为目标架构
```

**开关状态（2026-08-14）**：`UNIFIED_SHADOW_ENABLED` / `UNIFIED_SHADOW_EXECUTE_ENABLED` 已随
INTENT-02-CLEANUP-FLAGS-01 删除，统一链是唯一默认路径。

**当前任务**：继续 INTENT-02 五步清理——删除旧提交分支、统一命令入口、重命名影子概念、真实验收。

### 5.2 为什么当时采用影子模式

1. **零风险对比**：新旧链路同时运行，可对比输出差异
2. **渐进验证**：先观察（read-only）→ 确认正确 → 切换写入
3. **快速回退**：出问题只需关掉 `EXECUTE` 开关，旧链路继续工作
4. **持续交付**：每一步都是可工作的系统，不需要长时间停服重构

影子模式已经完成验证使命，不应继续承载新功能。查询、安全和 RAG 必须接入清理后的单一路径。

### 5.3 双轨清理职责迁移对照表（2026-08-14 起逐轮更新）

> 每个清理轮删除旧路组件时，必须在此登记：**旧路做了什么 → 新路如何获得该功能**。
> 避免"代码删了、能力也丢了"，也帮助后来者理解删除理由。

| 清理轮 | 被删的旧路组件 | 旧路原来做什么 | 新路如何获得该功能 |
|---|---|---|---|
| FLAGS-01 | `UNIFIED_SHADOW_ENABLED` / `UNIFIED_SHADOW_EXECUTE_ENABLED` + `validate_shadow_flags` | 开关切换新旧链路（观察/执行两档） | 新链是唯一默认路径，不需要开关；配置校验函数随开关一起退役 |
| SUBMIT-01 | `create_experiment_llm_processor`（旧 ExperimentLLMProcessor） | 旧链调 LLM 做实验结构化 | 统一链 `UnifiedUnderstandingProcessor` 一次调用完成理解+结构化 |
| SUBMIT-01 | `SegmentProcessor.process` / `SessionProcessingQueue.submit` | 旧链五步：ASR保存→LLM→事件保存→上下文更新（后台线程） | main 直接编排：ASR 落盘 → `event_store` 落盘 → `session_context.add_analysis`（prepare→persist→commit，主线程） |
| SUBMIT-01 | `display_completed_segment(s)` / `display_segment_result` / `display_coordinated_reply` + `skip_ingest` 补丁 | 旧链显示后台完成结果并 ingest 进 ReplyCoordinator | `display_shadow_observation` 显示观察摘要；协调器交互由 `ClarificationExecutor` 负责 |
| SUBMIT-01 | 外层 `try/finally` 队列收尾 + 后台线程/队列/背压 | 会话结束等待后台任务完成；**并让用户说完继续说、连续口述不卡** | 无后台任务，但**非阻塞录音能力随之丢失**（见 5.4 表"非阻塞录音"行；RESTORE-NONBLOCK-01 待恢复） |
| COMMAND-01 | `resolve_targeted_answer` 门卫（"问题 N，答案"） | 精确解析编号答复并路由 | 统一链 LLM 识别 answer 动作 + `AnswerEntityExtractor` 提实体 + executor 执行 |
| COMMAND-01 | `try_handle_clarification_command` 门卫（查看/暂缓） | 精确命令处理+结果展示 | 统一链 review/defer 动作 + executor；查看显示由 `display_review_result` 承接（REVIEW-OUTPUT-01） |
| COMMAND-01 | `try_handle_confirmation_answer` 门卫（"是的"） | prepare→写 ConfirmationRecord→commit | 统一链 confirm 动作 + executor；main 在状态变更成功后写 ConfirmationRecord（`from_executed_confirmation` 工厂） |
| COMMAND-01 | `display_clarification_command_result` / `display_confirmation_resolution` | 命令结果话术 | `display_review_result` + 观察摘要中的 execution_reason |
| COMMAND-01 | `_new_chain_handled_answer` 补丁 | 防止新旧两条路重复处理 answer | 补丁本身是双轨产物；统一为单一路径后不需要 |
| NAMING-01（待） | `shadow` 命名（observer/observation/显示） | —（纯命名） | 改为正式执行链命名，不改变行为 |
| VERIFY-01（待） | 孤儿模块 `clarification_command_handler.py`、`targeted_clarification.py` | 已不被 main 调用 | 删除前确认其测试覆盖已由新链测试承接，再删模块+测试 |
| RESTORE-NONBLOCK-01 | main.py 主循环内联的六步业务流水线（观察→落盘ASR→落盘事件+上下文→无编号兜底→执行→确认记录） | 主线程同步串行处理每段；observe 调 LLM 期间麦克风关闭，说完干等 | `UnifiedSegmentProcessor.process`（六步流水线，无线程纯业务）+ `OrderedTaskQueue`（后台单线程+背压4：submit/collect_ready/finish）；main 主线程只录音→结束判断→提交→显示 |
| WEB-BRIDGE-01 | `web/llm_bridge.py` 桥接的旧 `ExperimentLLMProcessor`（`analyze_segment`） | 网页端 LLM 只做实体抽取（events + entities），不分辨意图 | `UnifiedUnderstandingProcessor.understand` 一次调用完成 input_kind（experiment/control/uncertain）分辨 + 结构化；web 只消费 experiment 分支的实体卡片，control/uncertain 只带回标签不执行动作（见 5.6） |
| WEB-RENDER-01（B4，2026-08-18） | 前端 `voice_asr.js`/`mobile.js`/`lab_panel.js(labRender)` 读 `evaluation.follow_up_required/follow_up_question/deviations` 自行判断"要不要问"并**拼话播报**（薄字典平行投影） | `/record` 返回 `messages`（B3），前端只按 `kind`/`screen_target` 上样式、显示/朗读 `messages` 的 `text`（话术来自后端 copy 层）；"要不要问"的判断权收归后端（降级生产者+投影层） | **保留点（明确标注）**：`views.js` 历史视图仍读 evaluation（messages 不入库，历史无 messages；属存储数据展示非实时判断）；`labEvaluate` 面板走 `/protocols/evaluate`（非 /record 语音链），不在本迁移范围。质量状态见 5.4 表"web 侧"行 |
| WEB-RENDER-02（2026-08-18 真实验收后补） | 桌面语音链 `voice_asr.js` 识别后 `if (input && form) { requestSubmit() }` 填聊天框送 `/chat`——**B4 改的 /record 直连分支因 `return` 在前从未执行（死代码）**，界面追问/回执话术实为 agent 生成（"好的，请问…"） | 删除聊天框分支，桌面语音口述一律直连 `/record`：判断在后端（降级生产者+投影层）、话术走 messages text（copy 层"小科：…"）、前端只画只念 | **等价提升**：桌面与 `/m` 手机页统一走 messages 渲染；文字聊天（composer→/chat）保留 agent 链不动。真实验收证据：改前语音说"称量磷酸盐"返回 agent 话术；改后返回 copy 层话术 |
| RECORD-SERVICE-01（D2，2026-08-23） | `web/api/record.py` 内联的最近上下文、LLM 抽取、规则兜底、确定性评估、保存、共享结果适配和 PresentationIntent 投影 | `/record` 自己完成整条记录业务链，再用 WebRenderer 添加响应 messages；手机与桌面虽调用同一 HTTP 路径，但业务能力无法被其他入口直接复用 | `SharedRecordService.record()` 接管完整业务顺序；`/record` 只做 HTTP 校验、依赖绑定、`RecordPersistenceError`→HTTP 500 和 WebRenderer 响应适配 | **等价（自动合同）/ UX 待确认**：旧 JSON 字段、messages 文案、messages 不入库和保存失败无成功回执均有回归证据；未做真实浏览器体验裁决 |
| RECORD-SERVICE-02（D3，2026-08-23） | `web/lab_tools.py` 的 `record_observation` 独立执行规则抽取、评估、段号分配和保存，与 `/record` 形成第二条记录业务链 | 工具与 HTTP 入口可能因抽取路径和后续规则演进而产生不同记录结果 | 工具构造 `RecordCommand` 并调用同一 `SharedRecordService`，只把共享结果适配回原五字段工具合同；异常仍由工具分发器转成结构化错误 | **等价（自动合同）/ UX 待确认**：工具字段合同和失败边界保持；共享 intents 接入工具呈现留给 D4，未接 PlaybackScheduler |
| TOOL-PRESENT-01（D4，2026-08-23） | `record_observation` 保存后只把五字段结果交回聊天模型，模型再次生成“已记录”或追问 | 底层记录事实虽已统一，但回执措辞和是否追问仍可能被模型重新决定，绕过 Intent/copy/DeliveryPlan | 工具成功结果同时携带后端 `PresentationDeliveryPlan`；同步/流式 agent 完成同轮工具后直接用 WebRenderer/copy 的确定性文本结束该轮，不再请求模型重写记录回执 | **提升（自动合同）/ UX 待确认**：模型请求次数测试证明记录呈现不经第二次模型；仍经普通 delta 上屏，播放事件与许可接线留给 D5–D10 |
| CHAT-SCREEN-01（D5，2026-08-23） | `/chat/stream` 把普通正文、思考标记和工具卡片标记全部包装成 `delta`；前端 `delta` 同时上屏并进入 `enqueueSpeech` | 普通聊天文本天然暗含播放权，无法区分“显示内容”和“获准发声内容” | 普通正文经 `agent_chunk_event()` 变为显式 `screen_delta`；实际 v2 前端只上屏该事件。思考/卡片控制标记暂留旧 `delta`，播放路径随后单项删除 | **提升（自动合同）/ UX 待确认**：screen_delta payload 与前端分支均无发声能力；后端 voice_delivery、旧 delta 清理和真实播放尚未完成 |
| DELTA-TTS-01（D7，2026-08-23） | 活动 `streaming_chat_v2.js` 与遗留 `streaming_chat.js` 的 `delta` 普通文本分支都可直接调用 `enqueueSpeech` | 任何旧/误发 delta 都可能绕过 DeliveryPlan、PlaybackGate 和 Scheduler 获得发声权；遗留文件重新启用会恢复旁路 | 两份前端的 delta 分支只保留控制标记和屏幕更新，删除所有 delta 驱动的发声调用；task_queued/done 保持原样分项治理 | **提升（自动合同）/ UX 待确认**：静态分支测试与 Node 语法检查通过；后端 voice_delivery 尚未接通，真实播放未验收 |
| VOICE-EVENT-01（D6，2026-08-23） | 工具 DeliveryPlan 的 `voice_items` 停在 agent 内部，SSE 只能发送屏幕文本和遗留控制标记 | 后端无法显式交付稳定语音候选；若直接把文本塞回 delta 又会恢复无权限发声 | agent 以不可变批次输出合并后重新预算的 voice items，`/chat/stream` 独立序列化为 `voice_delivery`，不写聊天正文/历史；事件标注 `CONTENT_ELIGIBLE` 而非运行时授权 | **提升（自动合同）/ UX 待确认**：候选合同与预算有测试；前端尚不消费，Scheduler 尚未产生 READY/PREEMPT，真实播放未验收 |
| TASK-QUEUED-TTS-01（D8，2026-08-23） | 活动与遗留流式客户端收到 `task_queued` 后既显示排队回执又直接调用 `enqueueSpeech` | 后台排队状态绕过 Intent、DeliveryPlan 和播放门控；打开自动播报就会插话 | 两份客户端的 task_queued 只保留上屏、conversation_id、头像和任务面板刷新，删除直接 TTS；任务完成轮询通知保持独立待治理 | **提升（自动合同）/ UX 待确认**：分支静态测试与 JS 语法检查通过；真实浏览器、完成通知和受控播放未验收 |
| FRONTEND-VOICE-AUTH-01（D9，2026-08-23） | 前端没有 voice_delivery 消费合同，历史事件分支各自直接调用 TTS | 即使后端发送候选，前端也无法区分内容资格与运行时授权，容易把 CONTENT_ELIGIBLE 直接播放 | 共享 voice_delivery 客户端只允许 READY/PREEMPT 进入唯一 TTS；候选、延后、丢弃、未知和坏 payload 无副作用。两个流式客户端只负责委托 | **提升（自动合同）/ UX 待确认**：Node 行为测试验证调用序列；生产后端尚无 READY/PREEMPT，需 D10 Scheduler 接线后才可真实播放 |
| VOICE-MOUTH-01（C1，2026-08-20） | `speak.js` 自带 `/tts`+`Audio` 发声的 `labSpeak`、`mobile.js` 局部 `speak`（两张独立"嘴"） | 各自 fetch `/tts` 独立发声；打断时 `window.stopSpeech` 只能停 `local_tts.js` 自己那张，停不到 `speak.js`/`mobile.js` 正在念的音频（barge-in 失灵，风险 B） | 三张嘴收敛为单一 `window.speak`（保留 `local_tts.js`）：`speak.js` 改薄适配层 `labSpeak`→`window.speak`；`mobile.html` 加载 `local_tts.js`、`mobile.js` 追问改调 `window.speak`；`local_tts.js` 补浏览器兜底 + status 空安全。打断现停得住唯一那张嘴 |
| VOICE-TEXT-01（C2a，2026-08-20） | 前端 `speak.js`/`mobile.js` 朗读时 `.replace(/^小科：/, '')` 自己剥称呼前缀 | 从 `messages[].text` 里剥"小科："再念——"词"的一部分（剥前缀）落在前端 | 后端 copy 层新增 `voice` 通道：`copy_for_intent(..., voice=True)` 对 CLARIFICATION 返回纯问题（无"小科："、无来源标注），`WebRenderer.render` 多产出 `voice_text`；前端直接念 `voice_text` 不再剥前缀（词全在后端） |
| VOICE-ENTRY-01（2026-08-20） | 桌面页两个冗余"对话"入口：`vad_mode.js` 的「🎤 语音对话」按钮（VAD 免按键连续对话→/chat）、`avatar.js:41` 头像 click 触发 `phoneCallToggle` | 「语音对话」与「通话」职责重叠（都是连续对话→/chat，两套实现）；头像 click 是「通话」第二入口、与 `#sh-call` 重复；且 `phone_call.js` 的 `$('#sh-call')` 因 `$` 封装为 getElementById 不认 `#` 前缀永远取 null（按钮 onclick 从未接上、不变"挂断"，只有头像那条路能用） | 只留两个入口：`cp-mic`「语音记录」（→/record）+ `#sh-call`「通话」（→/chat）。删 `app.py` 加载 `vad_mode.js`（文件保留供 `vad_check.html` 诊断页）；删 `avatar.js:41` 头像 click 通话（头像保留状态展示+🔊播报开关）；修 `phone_call.js` `$` 封装 getElementById→querySelector | **等价/提升**：被删两个入口的"连续对话"能力由「通话」全覆盖（更完整：barge-in+噪音校准）；通话按钮修好后可正常进入/挂断 |

### 5.4 用户可见输出质量对照表（2026-08-14 建立，回应"没感觉新链路改善/功能丢了"）

> 5.3 表追踪"动作是否迁移"；本表追踪**动作迁移后，用户看到的输出质量是否等价**。
> 结论：业务逻辑（追问创建/回答填充/确认落盘/证据一致性）已迁移且更稳；
> **用户可见输出质量整体降级**——这是"体验没改善、感觉功能丢了"的根因，
> 也是 PRESENT-INTEGRATE-01 必须补的债。证据 = 会话 `20260814_174441` 走查输出。

| 用户可见能力 | 旧链（清理前） | 新链（现状，证据=会话 20260814_174441） | 质量状态 |
|---|---|---|---|
| 非阻塞录音（说完继续说） | 后台线程+队列+背压（max_pending_tasks=4），连续口述不卡，真机验收"连续5段不卡" | 已恢复：`OrderedTaskQueue`（后台单线程+背压4）+ `UnifiedSegmentProcessor`；集成测试证明录音期间后台继续处理；两句谎话已拆（111行→"ASR 原文已保存"；320行"无需等待"现为真） | **恢复**（等价，AUTO_OK 集成测试通过；待真实验收"连续5段不卡"复核） |
| 用户口述回显 | 显示识别文本 | "本段 ASR 识别完成：先加入防生缓冲液。" | 等价 ✓ |
| 确认回执 | 协调回复（"已确认第1步"类用户语言） | "[统一链] 第6段：…已将对问题1的答复的实体字段['action','object']填入。 仍需确认。。" | **降级**（开发语言+双句号） |
| 追问独立显示 | 协调器输出问题（"第2步离心多长时间？"） | 追问埋在"[统一链]…已创建待确认问题1：…"行内 | **降级**（被开发行淹没） |
| 降级提示 | "原始记录已保存，结构化处理暂时不可用"（POLICY 第6节示例） | 无面向用户提示，只有"[统一链] 目标=degraded_note…" | **丢失** |
| 查看待确认列表 | "当前没有待确认问题"/列表 | "当前共有1个待确认问题：-问题1（待回答）：…" | 等价 ✓ |
| 结束汇总 | 会话总结（用户语言） | "共处理8段…提交4段" + "最终上下文包含4条事件" | **降级**（混入开发语言） |
| 追问播报（web，B4） | 前端读 `evaluation.follow_up_required` 播报 `follow_up_question` | `messages` clarification 的 `text`（"小科：缺时长，请补充"）由 `labSpeakMessages` 朗读 | 等价 ✓（话术来自后端 copy 层，判断在后端） |
| 偏差播报（web，B4，"注意，X 方案规定为 Y，你说的是 Z"） | 前端拼话播报 `deviations` | `messages` 体系暂无 deviations 消息 → 不再播报 | **丢失**（登记：降级生产者/投影层补 deviations 消息，随 D 阶段或独立任务） |
| "本步现场记录已完整"（web，B4 无追问反馈） | 无追问时显示"本步现场记录已完整" | `messages` record_ack 降级"原始记录已保存，结构化处理暂时不可用。" | **降级**（措辞从"完整"变"降级"；D 阶段真观察器产 structured_experiment 后恢复"已记录实验步骤 N"等价反馈） |
| 实体/结构化展示（web，B4） | 前端展示 entities | 保留（前端只画不判） | 等价 ✓ |
| 历史视图（web，B4，/record/history） | 读 evaluation 展示追问/偏差 | 保留 evaluation 展示（messages 不入库，历史无 messages；属存储数据展示，非实时判断） | 等价 ✓（边界已说明） |

> **判定规则（写入验收纪律）**：迁移对照必须逐项标注质量状态（等价/降级/丢失），
> "降级/丢失"项在 PRESENT 前视为未完成；agent 的"功能验收通过"不得掩盖"体验质量降级"。

---

### 5.5 命令处理政策现状（2026-08-14 建档，回应"LLM 兜底初心 vs 命令侧弃权"）

> 证据三档：**精确命中**（命令表固定词）/ **本地语义**（前缀后缀规则）/ **LLM 识别**（模型判断）。
> 核心结论：新路初心是"LLM 兜底"，但命令侧 LLM 兜底几乎全线堵死——7 类输入里只有"查看"真正放了 LLM 进来。

| 输入 | 风险 | 可逆 | 精确命中 | 本地语义 | LLM 识别 | 最终去向 |
|---|---|---|---|---|---|---|
| 实验口述 NORMAL | 无 | — | — | — | **进实验** | EXPERIMENT_PIPELINE |
| 查看 REVIEW_PENDING | 低 | ✓ | 复核上下文 | 复核上下文 | **复核上下文** ✅ | CLARIFICATION_CONTEXT |
| **暂缓 DEFER_CURRENT** | 中 | ✓ | 复核上下文 | 复核上下文 | **弃权** ⚠️ | CONTEXT / ABSTENTION |
| 确认 AFFIRM | 中 | ✗ | 复核上下文 | 弃权 | 弃权 | CONTEXT / ABSTENTION |
| 否定 DENY | 中 | ✗ | 复核上下文 | 弃权 | 弃权 | CONTEXT / ABSTENTION |
| 编号回答 TARGETED_ANSWER | 中 | ✗ | 复核上下文 | 弃权 | 弃权 | CONTEXT / ABSTENTION |
| 结束 END_SESSION | 高 | ✗ | **直接执行** | 请求确认 | 请求确认 | EXECUTION / **CONFIRMATION（无下文）** ⚠️ |

**三个问题点**：

1. **暂缓（DEFER）——可逆操作被弃权，是 bug**。`DEFER` 标 `reversible=True`，但 `intent_policy.py` 写死"只有 LOCAL_SEMANTIC 才能放行"，LLM 识别的"我先跳过"落进弃权。`reversible=True` 是死的（待 `GAPS-FIX-DEFER-01` 接上）。
2. **结束（END_SESSION）——请求确认了但没下文**。LLM 识别"今天先记录到这里吧"→ `REQUEST_CONFIRMATION` → 分派到 `END_SESSION_CONFIRMATION`，但 main 主循环不处理该目的地，既不追问也不在肯定后结束（待 `GAPS-FIX-END-01` 闭环）。
3. **确认/否定/编号回答——LLM 识别全弃权，合理**。三者 `reversible=False`（不可逆：确认/否定/填入后状态难回退），LLM 判断不可逆操作宁可弃权要求精确或本地语义，保守但站得住，**不该放行**。

**"LLM 兜底"当前真实覆盖范围**：实验口述 ✅ 一直兜底；查看 ✅ 放行；暂缓 ❌ 被误杀；结束 ⚠️ 半通不通；确认/否定/回答 ⛔ 弃权（合理）。修完 DEFER + 结束闭环后，命令侧从"1/6 通"变"3/6 通"。

### 5.6 web 统一链桥迁移对照（WEB-BRIDGE-01，2026-08-15 建档）

> 背景：`web/llm_bridge.py` 原桥接旧链 `ExperimentLLMProcessor`（src 已标"待删除，
> 不再作为目标架构"，见 §5.1/§5.3 SUBMIT-01），网页端长期依赖一个将删组件。
> 本轮把桥迁到统一链 `UnifiedUnderstandingProcessor`，并补齐 `recent_context`。
> 本表登记"旧桥做了什么 → 新桥如何获得该功能"，逐项标用户可见质量状态。

| 网页能力 | 旧桥（迁移前） | 新桥（迁移后） | 质量状态 |
|---|---|---|---|
| 口述→实体卡片 | 旧链 `analyze_segment` 抽 events + entities | 统一链 experiment 分支（同一套 `src/llm/schemas.py` 合同，格式不变），`record.py` 合并逻辑零改动 | **等价**（单测 7 项通过 + 真实验收 5 条口述实体抽取准确，见下） |
| 模型失败降级 | 旧链 NOTE 卡片（"模型处理失败，仅保留未经解释的ASR原文"）+ degraded 标志 | 统一链 NOTE 卡片（"统一理解失败：…"）+ degraded 标志；前端只渲染 degraded 提示语，不渲染 NOTE 文案 | **等价**（降级文案只进 SQLite，不进 UI） |
| 指代理解（"它""改到周五"） | 旧链不带上下文 | 新桥从 `lab_records` 取最近 5 条口述作 `recent_context` | **增强**（统一链提示词显式支持上下文） |
| 控制命令识别（"帮我看看待确认"） | 旧链无此能力，命令被当实验口述硬拆卡片 | control 分支识别 + `input_kind` 标签；web 不执行动作，只回标签 | **新增**（真实验收口述 3 确认 `input_kind=control`、零错误卡片） |
| 记录/命令说不准的短句 | 旧链硬拆 | uncertain 分支 + `input_kind="uncertain"` | **新增**（UI 暂不消费） |

> **真实验收证据（2026-08-16，会话 `20260816_200646`，deepseek-v4-pro @ api.deepseek.com/v1）**：
> 5 条口述全部无降级、无报错。口述 1「加热到六十摄氏度」→ action=加热/temperature=六十摄氏度；
> 口述 2「加入五毫升盐酸」→ action/object/amount_value/amount_unit 全对；
> 口述 3「帮我看看待确认的问题」→ `input_kind=control`、零实体卡片（旧链会硬拆出错误卡片）；
> 口述 4「离心机八百转运行十分钟」→ 多字段含 duration；口述 5「溶液颜色变蓝」→ observation 事件。
> 追问话术：口述 1 缺时长未追问——对应项目已登记未定案争议 `LLM-FOLLOWUP-STRICT-01`
> （温度明确时缺时长是否应追问），非本轮迁移引入退化。
> **功能验收 REAL_OK；体验验收（UX）待用户走查确认。**

> 判定纪律同 §5.4：功能等价 ≠ 体验等价；"追问话术"与"降级提示语"两项
> 必须在真实验收中用新旧链输出逐条对比后才能标"等价"。


---

## 六、设计模式总结

| 模式 | 应用位置 | 目的 |
|---|---|---|
| **Protocol + DI** | ASRBackend, LLMClient, IntentClassifier, DispatchExecutor | 测试可替换，实现可切换 |
| **Factory** | create_asr_backend, create_llm_client | 集中创建逻辑，fail-fast |
| **Frozen Dataclass + 校验** | 所有跨模块合同 | 构造即正确，下游无条件信任 |
| **纯 Planner + 副作用 Executor** | UnifiedDispatchPlanner, ClarificationActionPlanner | 核心逻辑可单元测试 |
| **两阶段提交** | ReplyCoordinator prepare/commit | 外部 I/O 成功才修改内存状态 |
| **影子/ Pilot** | UnifiedShadowObserver | 新旧链路共存验证 |
| **单一工作线程 + 背压** | SessionProcessingQueue (max_pending_tasks=4) | ASR 不会无限领先 LLM |
| **策略模式** | IntentPolicyEvaluator | 风险等级决定执行边界 |
| **状态机 + 观察者** | StateManager (FMS) | 应用生命周期可观测 |

---

## 七、关键数据合同

### 7.1 UnifiedUnderstandingResult（统一理解输出）

```
┌─────────────────────────────────────────┐
│ UnifiedUnderstandingResult (frozen)     │
│ ├─ raw_text: str                        │
│ └─ 三选一：                              │
│     ├─ experiment: ExperimentUnderstanding │ → 实验记录链路
│     ├─ control: ControlUnderstanding      │ → 控制命令链路
│     └─ uncertain: UncertainUnderstanding  │ → 弃权，记录但不结构化
└─────────────────────────────────────────┘
```

### 7.2 ProcessOutcome[T]（通用结果包装）

```
┌──────────────────────────────────┐
│ ProcessOutcome[T] (frozen)       │
│ ├─ value: T                      │ ← 成功结果
│ ├─ degraded: bool                │ ← 是否降级
│ ├─ error: str | None             │ ← 错误信息
│ ├─ llm_attempts: int             │ ← LLM 调用次数
│ └─ llm_processing_seconds: float │ ← 处理耗时
└──────────────────────────────────┘
```

所有 LLM 调用都返回 `ProcessOutcome`，上层不需要 try/catch，只需检查 `degraded` 标志。

---

## 八、测试分层

```
Layer 4: 端到端（真实麦克风 + 真实 LLM）
  └─ scripts/ 中的手动测试脚本
  └─ 真实验收会话

Layer 3: 真实服务测试
  └─ 固定输入 → 真实 ASR/LLM → 验证输出格式

Layer 2: 集成测试（Fake 连线）
  └─ FakeUnderstandingProcessor + 真实 Router + 真实 Planner
  └─ 验证模块间数据合同兼容

Layer 1: 单元测试（Fake）
  └─ 纯逻辑测试（Planner、Parser、PolicyEvaluator）
  └─ 状态机转换测试
  └─ 422 个测试，全部通过
```

**测试原则**：
- Arrange–Act–Assert，每个测试只验证一个行为
- 测试公共接口，不依赖私有实现
- 同时覆盖正常、边界和失败路径
- 修复后必须运行全量测试防回归

---

## 九、扩展点（为未来预留）

当前架构已为以下方向预留了清晰的扩展点：

1. **新意图类型**：扩展 `InteractionCommandType` + `IntentPolicy` + `INTENT_POLICIES` 映射
2. **新分派目标**：扩展 `UnifiedDispatchDestination` + `UnifiedDispatchPlanner.plan()` 分支
3. **TTS 输出**：`PresentationMessage` + `VoiceDeliveryPolicy` 已定义合同，只需接入 TTS 引擎
4. **新 ASR 后端**：实现 `ASRBackend` Protocol，注册到 `factory.py`
5. **新 LLM 提供商**：实现 `LLMClient` Protocol，注册到 `factory.py`
6. **新会话能力**：扩展 `UnifiedInputKind` + `UnifiedUnderstandingResult` 分支

### 已规划的下一批扩展（详见 `PROJECT_TASK_CHECKLIST.md` 第 I 节）

**口述查询识别**：
- `UnifiedInputKind` 增加第 4 分支 `QUERY`
- `UnifiedDispatchDestination` 增加 `KNOWLEDGE_BASE` 目标
- 一次 LLM 调用同时识别实验/控制/不确定/查询四类输入
- 查询子类型：设备占用、实验信息、协议参考、通用知识

**安全警示**：
- `SafetyCheck` Protocol 插入实验采用管线
- 7 种危险类型：高温、危险化学品、高压、生物危害、锐器、电气、其他
- 3 级处置：ALLOW / WARN_BUT_PROCEED / BLOCK_UNTIL_ACKNOWLEDGED
- 复用现有 `MessageKind.SAFETY_ALERT` 消息类型

**用户画像 + 知识库（RAG）**：
- `KnowledgeBase` Protocol 定义最小检索接口
- `UserProfile` 存储用户偏好和默认值
- `SessionContext` 扩展携带画像和知识提示
- `PendingClarification.knowledge_source` 区分知识库触发 vs LLM 推测追问
- `ExperimentEntities.matched_term` 存储知识库匹配的标准术语

---

## 十、文件清单

```
src/
├── main.py                    # 组合根 + 会话循环 (1193行)
├── config.py                  # 集中配置 + 环境变量
├── asr/                       # ASR 后端 (Protocol + SenseVoice 适配器)
├── audio/                     # 音频采集 (VAD + 预录制 + 唤醒音)
├── wakeword/                  # 唤醒词检测 ("小科小科")
├── llm/                       # LLM 客户端 + 两代处理器
├── core/                      # 领域逻辑 (26个文件，纯数据合同+规划器)
├── storage/                   # JSONL 持久化
└── evaluation/                # 离线评估工具
```

## 2026-08-23 本轮维护记录：VOICE-C5-D10 Web 统一播放授权

- `web/playback_runtime.py` 是 Web 生产者与核心播放域之间的适配层。`/record` 与 chat tool 只提交 `VoiceDeliveryItem`，由共享 `WebPlaybackService → PlaybackRequest → PlaybackScheduler → PlaybackGate` 产生授权。
- `BrowserPlaybackExecutionPort` 是核心 `PlaybackExecutionPort` 的浏览器实现边界：服务器不播放音频；Scheduler 成功 hand-off 后，适配层才把结果序列化成 `voice_delivery authorization=READY`，由前端唯一 `consumeVoiceDelivery()` 进入 `window.enqueueSpeech`。
- 普通 chat 没有 `VoiceDeliveryItem`，因此只上屏，不进入 Scheduler；这不是绕过，而是没有语音候选就没有播放请求。
- `/record` HTTP JSON 新增 `voice_delivery_events` 影子字段并保留旧 `messages` 与记录字段；`messages.voice_text` 暂保留兼容数据，但桌面与手机客户端不再据此发声。
- 当前运行时协调器尚未接浏览器 VAD/TTS 事实，默认只验证空闲 READY；PREEMPT 在 STOPPED 反馈接通前安全降为 DEFERRED。会话隔离、实时状态回传与真机时序不属于本项。

## 2026-08-23 本轮维护记录：VOICE-C5-E1 职责冻结

- 新增 `tests/test_c5_architecture_freeze.py`，把 C5 架构约定从文档提升为持续执行的测试：内容资格层不能导入播放状态/TTS，Gate 不能拥有 Queue/执行行为，Web producer 不能直接调用 TTS，迁移范围内前端只有授权客户端能执行播放。
- `streaming_chat_v2.js` 与遗留 `streaming_chat.js` 已删除无写入者的 `speechBuffer` 及 done 收尾发声代码；普通 chat、delta、screen_delta、task_queued、done 均不再包含 `enqueueSpeech`。
- `task_panel.js` 的后台任务完成通知是当前冻结测试显式记录的范围外例外，后续若统一通知语音，应单独建任务接入 Scheduler，不能暗中扩大 C5 结论。
- C5 组合回归 `190/190`；项目级全量受 NumPy/Pydantic ABI 环境阻塞，执行到 898 项时有 17 个导入错误，因此架构状态为 `AUTO_OK` 而非真实设备或全项目通过。
