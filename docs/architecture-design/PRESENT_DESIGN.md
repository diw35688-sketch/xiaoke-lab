# PRESENT-INTEGRATE-01 会话级呈现系统设计（v2）

首次定义：2026-08-15（过渡版：统一打印/分流）
v2 升级：2026-08-16（"单一输出权"定位 + presentation pump + 四条边界）

状态：DESIGN（待用户确认后进入 CODED）

> 本文档定义"输出层会话级呈现系统"的模块边界、数据结构、接口与分步。
> 输出职责与政策以 `OUTPUT_PRESENTATION_POLICY.md` 为准；任务状态与顺序以
> `PROJECT_TASK_CHECKLIST.md` 为准；体验验收标准见 `UX_WALKTHROUGH_CHECKLIST.md`。
>
> 关联任务：`PRESENT-INTEGRATE-01`（会话级呈现系统）、`UX-MODE-01`（= 本任务的
> 用户可见验收标准）、`SYNC-UI-CLAIMS-01`（文案一致性，随本任务收口）。

## 0. 一句话定位（v2 与过渡版的根本区别）

过渡版是"把散落的 `print()` 收拢、包一层"。v2 是**给系统安一张唯一的嘴**：

> **所有执行流都不许自己输出；它们只投递呈现意图；只有一条呈现执行流
> （presentation pump）拥有 stdout 写入权。**

这不是"统一打印"，是**单一输出权（single-writer）**。终端是第一个渲染器，
Web 与 TTS 是后续消费者。核心是把"系统现在处于什么状态"和"现在需要主动说什么"
分开——但状态模型（`SessionViewState`）等第二个消费者出现后再建，见第 11 节。

## 1. 解决什么问题（体验债，证据不变）

证据 = 会话 `20260814_174441` 走查 + 架构 5.4 表：

| 债 | 现象 | v2 对应 |
|---|---|---|
| UX-01 | DEBUG 与用户信息同屏混排 | DEBUG 走 `logging`，不经 pump、不上用户屏 |
| UX-02 | 追问文本埋在 `[统一链]` 开发行 | 追问作为独立语义 Intent，文案目录单独成句 |
| UX-04 | 降级/弃权段无用户人话 | 文案目录输出"原始记录已保存，结构化处理暂时不可用" |
| UX-06 | 双句号"。。" | 文案目录集中拼接、去重标点 |
| UX-07 | "第 N 段"未与"实验步骤 N"分离 | 投影时传 `experiment_step_number` |
| UX-08 | 结束汇总含开发语言 | 汇总只给用户语言（步骤数/待确认数） |
| UX-11 | 用户版/管理员版输出分层 | `UI_MODE=user|admin` + Renderer 分流 |

## 2. 目标架构

```
业务事实（SegmentOutcome / 会话状态 / 结束汇总 / 启动与唤醒）
   │
   ▼  纯投影（无副作用，只读业务结果）
PresentationIntent（不可变语义意图：发生了什么，不含中文、不含可变状态）
   │
   ▼
PresentationCoordinator（FIFO 主干 + 单问题选择 + 相邻"已保存"合并）
   │
   ▼
presentation pump（唯一 stdout 写入者；从 Coordinator 取货交 Renderer）
   │
   ▼
TerminalRenderer（前缀/布局/换行/UI_MODE 过滤）──► stdout（SCREEN）
                                        └──► DEBUG 走 logging（不经 pump）
```

关键：后台 worker 只 enqueue intent；主线程的 ASR 文本、监听提示、结束提示也投递到
同一入口；pump 是唯一调用 renderer/stdout 的执行流。worker 算完立即投递，不等下一段
录音结束，保留已验收的"插空反馈"速度（维 5/9 不退化）。

### 2.1 稳定接缝与 sink 的边界（2026-08-16 记录）

> 回答"以后加轻量前端，为什么还要设计 TerminalRenderer？如何保证上下游不绑定终端 render？"

**稳定接缝（上下游都不许动、Web/TTS 都要复用）是结构化语义，不是终端文本：**

| 层 | 是不是稳定接缝 | 说明 |
|---|---|---|
| `PresentationIntent`（结构化 kind+args） | ✅ 稳定接缝 | 终端/Web/TTS 都认这套语义 |
| `PresentationCoordinator`（排序产物） | ✅ 稳定接缝 | 产出的是 Intent，不是文本 |
| `TerminalRenderer`（render→str） | ❌ sink 实现 | 只是"终端"这一张嘴 |

**`render` 的定位**：终端这个 sink 的具体实现，不是通用渲染抽象。输入端 Intent 是
跨 sink 通用的；输出端 `str`（中文文本）是终端要的，只存在于 `TerminalRenderer ↔ stdout`
这一小段，不上游暴露。

**为什么现在还建 TerminalRenderer**：现在只有一个真实消费者（终端），按 YAGNI 不为
没来的 Web 提前建渲染器；但为 Web 预留的不是 TerminalRenderer，而是它上游的 Intent
结构化接缝。Web 将来是第二个 sink，并行走 Coordinator 的产出，不是替换 TerminalRenderer。

**上下游如何不绑定终端 render**：
- 上游：pump/Coordinator 拿的是结构化 `PresentationIntent`，不拿 `render` 返回的 `str`；
  pump 依赖 `Renderer` 协议（Protocol，只约定 `render(intent)`），不依赖 `TerminalRenderer`
  具体类——将来 `WebRenderer` 实现同一协议即可，pump 一行不改。
- 下游：文案目录（`copy_for_intent`）是独立函数，不反向依赖 TerminalRenderer。

**已知权衡**：文案目录返回含 `\n` 的 str（review 多行列表），隐含了"终端文本块"假设；
Web 要结构化列表（可点击/时间线/状态区域）时，由子步 C 的 `SessionViewState` 承接，
`PresentationIntent` 与 `Coordinator` 这两个稳定接缝不动。这是"留接缝、不造功能"——把
接缝画对、把当前唯一的 sink 做扎实，把结构化状态留给它真正的消费者（Web）出现时再建。

## 3. 模块职责表

| 模块 | 文件（新增） | 负责 | 不负责 |
|---|---|---|---|
| `PresentationIntent` | `src/core/presentation_intent.py` | 不可变语义意图：kind、args（语义参数）、priority、屏幕区域、来源引用 | 不含可变 `status`、不含最终中文 |
| 文案目录 | `src/core/presentation_copy.py` | 语义 + 参数 → 用户文案（user/admin 两种措辞） | 不做布局/前缀/换行 |
| `PresentationCoordinator` | `src/core/presentation_coordinator.py` | FIFO 主干 + 单问题选择 + 相邻"已保存"合并；原子跟踪 pending/deferred/in-flight 完成所有权 | 不做 supersede/持久化历史/通用规则引擎 |
| presentation pump | `src/core/presentation_pump.py` | 唯一 stdout 写入者；从 Coordinator 取货交 Renderer；提供有超时和失败语义的 flush | 不决定内容/顺序 |
| `TerminalRenderer` | `src/core/terminal_renderer.py` | 前缀/布局/换行/UI_MODE 过滤 | 不产文案、不决定内容 |
| DEBUG logging | 标准库 `logging` | 基础设施与开发详情写文件/日志 | 不经 pump、不进 Intent |

`main.py` 职责不变（组合根 + 会话循环），只是把散落的 `print()` 换成"投递 Intent"；
基础设施层（LLM client / ASR backend / state_manager）把 `print()` 换成 `logging`。

### 3.1 完成交付合同

- `pending_count == 0` 只表示队列中暂时无货，不能证明已取走的消息完成 renderer/output；
- Coordinator 在 `submit` 时取得每条消息的完成所有权，Pump 在 output 返回后的 `finally`
  中调用 `mark_completed()`；语义去重丢弃项当场完成，deferred 项保持 unfinished；
- `join(timeout)`/`flush(timeout)` 等待 unfinished 归零，超时显式返回 `False`；
- renderer/output 异常被记录为结构化 `PresentationDeliveryFailure`，Pump 继续处理后续消息，
  flush 最终用 `PresentationDeliveryError` 报告本轮失败；
- 停机顺序固定为 flush → 报告超时/失败 → stop，不能再轮询 pending 队列猜测完成。

## 4. 四条边界（团队钉死，照单全收）

1. `PresentationIntent` 必须 `frozen=True`，不含可变 `status`；生命周期若暂时需要，
   由 Coordinator 内部队列条目管理，不进 Intent。
2. 第一轮不建 9 个领域事件类；只提供 `SegmentOutcome → 窄 PresentationIntent` 的纯投影。
3. 文案目录负责"语义 + 参数 → 用户文案"；Renderer 只负责前缀、布局、换行和模式过滤。
4. Coordinator v1 只做 FIFO 基础顺序、优先级、单问题限制、重复"已保存"合并；不做
   supersede 图、持久化消息历史或通用规则引擎。

## 5. 排序精确定义（FIFO + priority 的边界）

- **主干 = 稳定 FIFO**：谁先投递谁先出，不全局重排。回合顺序（维 2）靠 FIFO +
  `OrderedTaskQueue` 段内有序保证，不靠一个会乱序的排序器。
- **`priority` 只用于"单问题限制"**：同时有多个待回答问题时，选优先级最高那一个；
  不做全局优先级重排。
- **"已保存"合并要求两条相邻**：只有相邻的同类"已记录"才合并，避免跳过中间消息乱并。

## 6. `PresentationMessage` 的演进（已完成）

2026-08-16 已完成迁移：旧 `src/core/presentation_message.py` 及其专属测试已删除，
生产代码与测试只保留 `PresentationIntent` 主链，无兼容模块或类型别名。

| 旧字段（`PresentationMessage`） | 去向 |
|---|---|
| `kind` / `priority` / `screen_target` | 复用，移入 `PresentationIntent` |
| `text`（最终中文） | 移除；由文案目录按 `kind + args` 生成 |
| `status`（可变生命周期） | 移除；由 Coordinator 队列条目管理（边界 1） |
| `channels` / `speech_policy` | 移除；TTS 关注点，子步 C 的 `DeliveryPlan` 再引入 |
| `requires_response` / `deferrable` | 移除；调度关注点，子步 C 的 `PresentationTurn` 再引入 |
| `message_id` | 保留语义，改称 `intent_id`（不可变标识） |

`PresentationMessage` 数据类、`MessageStatus`、`DeliveryChannel`、`SpeechPolicy`、
`VoiceDeliveryPolicy` 等 Message 专属概念已全部删除；共享枚举 `MessageKind` /
`MessagePriority` / `ScreenTarget` 已归位到 `presentation_intent.py`。

> **迁移结论**：旧模型曾用于探索屏幕、TTS 与生命周期边界；稳定接缝确定后不再保留脚手架。
> 第二真实渠道出现前不预建新的通用交付对象；届时依据真实需求再考虑
> `DeliveryPlan`/`PresentationTurn`，不得复活旧双轨。

## 7. 映射关系（投影规则：业务事实 → 语义意图 → 文案）

投影层只产出"语义 + 参数"，文案目录负责中文。示例：

| 输入（observation 字段） | Intent（kind + args） | 文案目录输出（user 版） |
|---|---|---|
| `status == FAILED` | `RECORD_ACK` / 参数`result=failed` | "本段结构化处理失败，原始记录已保存。" |
| `acceptance_kind == degraded_evidence_note` | `RECORD_ACK` / 参数`result=degraded` | "原始记录已保存，结构化处理暂时不可用。" |
| `acceptance_kind == structured_experiment` | `RECORD_ACK` / 参数`result=recorded`,`step_number=N` | "已记录实验步骤 N。" |
| `clarification_action == create` 且 `executed` | `CLARIFICATION` / 参数`question` | "小科：{question}"（独立成句，UX-02） |
| `clarification_action == answer` 且 `executed` | `CONFIRMATION_ACK` / 参数`display_number`,`remaining_fields` | "已补充问题 N，仍需补充：X。"（去双句号） |
| `clarification_action == confirm` 且 `executed` | `CONFIRMATION_ACK` / 参数`display_number` | "已确认问题 N。" |
| `clarification_action == defer` 且 `executed` | `CONFIRMATION_ACK` / 参数`display_number` | "问题 N 已暂缓。" |
| `clarification_action == review` | `CLARIFICATION_REVIEW` / 参数`items` | 列表（复用现有友好文案） |
| `end_confirmation_requested` | `CLARIFICATION` / 参数`question` | "是否结束本次实验记录？（请说"是的"或"不是"）" |

### 7.1 语义参数的来源与挖掘方法（2026-08-16 记录）

> 回答"各语义参数到底有没有结构化暴露、如何挖掘使用"。以后给投影层加新参数时，按本节三步法检查，**禁止在下游解析自然语言**。

**参数来源三类：**

| 类别 | 例子 | 现状 |
|---|---|---|
| ① 本来就结构化 | `question`（追问文本）、`display_number`（问题编号）、`acceptance_kind`、`end_confirmation_requested`、review 快照 | 一直是 dataclass 字段，直接读 |
| ② 源头结构化、执行器压平了 | answer 的 `remaining_fields`（源头 `missing_fields`）、`resolved`（源头 `not is_unresolved`） | A-4 已补回字段并透传 |
| ③ 还缺、暂不影响 | create 后新问题编号（`affected_display_number`）、执行失败反馈（`state_changed=False` 的原因） | 子步 B 接线时补，或按需补 |

**追出生地三步法（加新参数时照做）：**

1. **定位出生地**——这个参数最早在哪个环节被算出来？
2. **看它出生时是不是字段**——是 dataclass 字段就直接引用；是被拼进中文了，就在出生地补一个字段（而不是到下游拆中文）。
3. **透传**——沿 `执行结果 → 观察摘要（UnifiedObservation） → 投影层` 一路带下来，投影层直接 `observation.xxx`。

**完整链路示例（remaining_fields）：**

```text
出生地：answer_clarification() 返回 updated.missing_fields（结构化，本来就有）
   │
执行器 _execute_answer：曾把 missing_fields 拼成中文"仍需补充：duration"（在此处丢结构化）
   │ A-4 在此补：ClarificationExecutionResult.remaining_fields = tuple(updated.missing_fields)
   ▼
ClarificationExecutionResult.remaining_fields
   │ unified_segment_processor 透传 exec_result.remaining_fields
   ▼
UnifiedObservation.answer_remaining_fields
   │ 投影层 observation.answer_remaining_fields
   ▼
Intent args = {"remaining_fields": ("duration",)}
```

**反面教训**：若不在源头补字段，而是让投影层解析"仍需补充：duration"这串中文、把 `duration` 抠出来——一旦执行器改了措辞（如"还差时间"），投影层就崩。拆中文 = 在别人随时会改的句子上做脆弱假设；补字段 = 在源头钉死一份不会漂移的结构化事实。

## 8. 分步（每步可独立验证）

### 子步 A：契约（AUTO_OK，不接 main、零用户可见变化）

`PresentationIntent` + 文案目录 + `TerminalRenderer` + 单元测试。
只定义合同与纯函数，不改 `src` 现有行为。

### 子步 B：接线 + 并发边界（真实验收）

最小 `PresentationCoordinator` + presentation pump + 全链单一出口 + 基础设施 DEBUG
迁 `logging`。真实会话 + 九维走查（维 1/7 ✗→✓；维 2/5/9 不退化）。

### 子步 C：等 Web/TTS 真实需求（只加 sink，不动主链）

`SessionViewState` / `DeliveryPlan` / `PresentationTurn` / supersede / 完整事件词汇表。

## 9. UX 覆盖表

| UX 项 | 子步 A（契约） | 子步 B（接线） |
|---|---|---|
| UX-01 分诊 | renderer 分流逻辑 + 测试 | logging 接线，屏幕干净 |
| UX-02 追问独立 | 文案目录拆独立句 + 测试 | main 显示 |
| UX-04 降级人话 | 文案目录降级文案 + 测试 | main 显示 |
| UX-06 双句号 | 文案目录去重标点 + 测试 | main 显示 |
| UX-07 编号分离 | 投影接收 step number + 测试 | 计数器接线 |
| UX-08 汇总语言 | 汇总文案构造 + 测试 | main 显示 |
| UX-11 分层 | UI_MODE 校验 + renderer + 测试 | logging 接线 |

## 10. 验收标准

- **子步 A**：全量测试通过（现有 490 项 + 新增契约测试），`src` 现有行为零变化。
- **子步 B**（完成标准，缺一不可，不得只以"新系统能显示"为准）：
  1. **单一输出入口**：用户消息只有一个输出入口（presentation pump），任何执行流不得自行输出；
  2. **后台不直接显示**：后台业务线程不再直接显示（只投递 Intent，由 pump 统一渲染）；
  3. **旧 print 已删**：被迁移类别的旧 `print()` 已删除（不是"新增一套、旧的还留着"）；
  4. **无新旧开关**：没有"新旧 PRESENT 切换开关"，新链路是唯一路径（延续去 shadow 纪律）；
  5. **全量测试通过**；
  6. **真实验收无退化**：真实会话验证没有重复、丢失或延迟退化；九维表维 1/7 由 ✗→✓，
     维 2/5/9 不退化；user 模式屏幕无 `[统一链]`/`[LLM请求]`/token/路径/状态变化；
     DEBUG 全量落入 `debug_<session>.log`；admin 模式行为与现状一致。

## 11. 已规划下一步（子步 C，等第二个真实消费者再建）

| 能力 | 触发条件 | 接入点 |
|---|---|---|
| `SessionViewState`（稳定区域状态快照） | Web UI 需要结构化状态，而非解析中文 | 读持久化记录整理成视图模型 |
| `DeliveryPlan` / `deliver_voice` | TTS 接入（P3） | Coordinator 的输出侧 |
| `PresentationTurn` + supersede 图 | 出现真实乱序/过期/取消场景 | Coordinator 内部 |
| 完整领域事件词汇表（9 类） | 安全/RAG/设备查询真实落地 | 投影层逐来源固化 |

> 这些是路线图明确要的下一步，不是"用不着的东西"，只是现在没有第二个真实消费者。
> 接缝（`PresentationIntent`）已在子步 A/B 立好，将来插入不动主链。

## 12. 明确不做（本轮）

- 不接 TTS（`deliver_voice` 属子步 C）；
- 不改前端/Web（TerminalRenderer 是文本终端实现）；
- 不迁移 `RECORD` 层（存储层已独立，不在消息链路内）；
- 不动 `GAPS-FIX-ANSWER-HINT-01` 的编号提示（属 GAPS 软问题，与 PRESENT 并行，另行收口）；
- 不建 `SessionViewState` / `DeliveryPlan` / `PresentationTurn` / supersede / 事件词汇表（子步 C）。

## 13. 用户呈现准入与时机合同（2026-08-16 用户确认）

PRESENT 不是把旧 `print()` 原样搬进统一出口。任何信息进入用户屏幕前，必须先判断
“用户此刻是否需要知道”；技术过程默认进入日志。首版使用以下六类时机：

| 时机 | 用户可见内容 | 约束 |
|---|---|---|
| `ONCE_PER_SESSION` | 会话开始说明、会话编号、连续口述说明、首次“请开始口述” | 每个会话只显示一次，不得在录音循环中重复 |
| `ON_EVENT` | ASR 转写、记录/降级/失败回执、新追问、回答/确认/暂缓回执 | 真实业务事件发生才显示 |
| `ON_STATE_CHANGE` | 首次超时、临近自动结束、降级、恢复、警告 | 状态未变化不得重复；倒计时只在关键节点提示 |
| `ON_REQUEST` | 用户主动查看待确认问题及“当前没有待确认问题” | 不主动反复播报 |
| `END_ONLY` | 实验步骤数、待确认数合并后的结束摘要 | 会话结束只显示一个摘要块 |
| `LOG_ONLY` | 模型加载、麦克风/VAD 内部阶段、文件路径、音频时长、目标/权限/token/上下文事件数 | user 模式不得上屏；admin/日志保留 |

明确删除的循环噪声：每段重复的“请开始口述”、每段“系统将立即继续监听”、
“麦克风准备就绪/检测到人声/说话结束/录音已保存路径”。系统静默继续监听是默认行为，
无需逐轮宣布。

首版无口述阶段固定为：首次进入等待时提示一次、剩余约 60 秒提示一次、剩余约 30 秒
提示一次、达到会话总超时后结束。同一阶段连续收到录音超时不再提示；检测到新口述后
回到活跃态，下一次重新进入等待时可以再次提示。

推荐节奏：唤醒反馈 → 一次性会话说明与首次录音提示 → 用户口述 → 转写与必要回执/追问
→ 静默继续监听 → 仅状态变化时提示 → 一次性结束摘要。

该分类是后续 QUERY、DENY、WARNING 与 TTS 的共用时机接缝；新增消息必须先归类，
不得仅因内部产生了事件就直接呈现。TTS 以后在 `DeliveryPlan` 决定是否播报，不能把
“屏幕可见”等同于“必须朗读”。

## 14. Delivery Boundary 架构护栏（2026-08-16 落地）

`PRESENT-DELIVERY-BOUNDARY-01` 把第 2 节目的架构变成可自动检查的边界：

| 护栏 | 检查方式 | 不允许 |
|---|---|---|
| 运行路径无直接 print | `tests/test_presentation_output_boundary.py` AST 扫描 | main/ASR/audio/wakeword/state/llm 直接 print |
| PRESENT 各层无直接 print | 同上 | Intent/文案/协调器/投影/pump/终端渲染器直接 print |
| 纯函数层无 I/O | 同上 | 文案、投影、终端渲染调用 open/input |
| 协调器与 pump 不反向依赖终端/文案 | 同上 | coordinator 导入 pump/copy/projection/terminal；pump 导入 copy/projection/terminal |
| FIFO + in-flight flush | `tests/test_presentation_pump.py` | 乱序、丢尾消息、flush 语义错误 |
| 唯一 stdout 写入点 | pump 依赖 `Renderer` 协议 + `output` 注入 | 其他执行流自行输出 |

新增消息只需扩展 `PresentationIntent` 的 kind/args、投影和文案目录；普通消息不得要求
修改 Coordinator 或 Pump。WARNING 在真实接入前补最小调度子步；TTS/Web 等第二真实渠道
接入前，才提取有限 Delivery/Renderer 抽象，不因未来可能性提前建设框架。
