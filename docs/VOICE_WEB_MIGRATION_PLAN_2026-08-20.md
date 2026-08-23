# 语音接入 Web 迁移计划（2026-08-20 重排版 · 按执行顺序）

> 建于 2026-08-20，基于这一轮的发现重排：P0 复合确认+实体（REAL_OK）、语音入口治理、
> 噪音问题、以及"语音受控是根本目的"这个校准。
> 本文件是**当前唯一执行顺序**的落点；历史细节（Phase A/B 拆解、§6 旧任务归属表）仍在
> `VOICE_WEB_MIGRATION_PLAN.md`，执行时只看本文件。

---

## 0. 根本目的（一句话校准，2026-08-20 用户定）

**让"语音输出"受控制，不打扰实验者。** 统一/确定只是手段，不是目的。

关键约束：实验者**手忙眼忙，看的是试剂瓶不是屏幕**——所以：
- 语音必须**短、受控、又灵活**；
- 屏幕**不是**语音的兜底（降级到屏幕 = 让用户停下手里的活）；
- 控"形式"（长度/内容/优先级），不控"措辞"（话术要自然，才有"小科"的人味）。

---

## 1. 语音形态决定

- **半双工 + 打断（barge-in）**：能说、能被随时打断，不追求俩人同时说。
- **砍全双工**：需额外回声消除工程，高风险、低收益，不做。

---

## 2. 迁移契约（6 条）

1. **方向**：CLI 统一链迁入 web；web 是产品，CLI 降为兜底。
2. **不崩盘**：过渡期用降级生产者（确定性、不调 LLM）产出部分观察，真观察器就绪后 drop-in 抽换。
3. **呈现**：前端为最终呈现；`TerminalRenderer` 兜底、不镀金。
4. **单一语义权威**：语义只在 intent/copy 层决定；前端只按 `screen_target`/`kind` 上样式，不二次判断。
5. **TTS**：嘴在前端（供应商+播放+barge-in），词在后端（copy 层语音文案，短、按 `screen_target` 过滤）。
6. **理解/执行分层**：统一链管理解（辨意图/抽实体/判缺字段），工具管执行（建实验/查冲突/列实验/记忆/算数/时间/推步骤）。**迁移不替换执行工具**；`record_observation` 的规则抽取属理解、迁入统一链，落库仍由工具层做。

### 2.1 统一判断权架构校准（2026-08-22，仅分析记录，未设计/未编码）

**用户确认的目标**：同一句口述 ASR 不能因为从“通话”“聊天”或“语音记录”进入而由不同模块重复判断；需要收敛到一个理解权威，再把已确定的动作交给工具执行。

**当前代码事实**：

- `UnifiedUnderstandingResult` 目前只有 `experiment / control / uncertain` 三个互斥分支；
- `UnifiedDispatchDestination` 目前只有实验、澄清上下文、结束、弃权和降级目标；
- 两份合同都没有通用 `tool` 分支，也不输出工具名与参数；
- 因而当前 `UnifiedObserver` 只能判断实验口述、澄清/确认/结束控制和弃权，**不能**判断 `get_current_time / start_timer / calculate / list_protocols / move_step` 等工具；
- 通话/聊天中的工具选择仍由 `web/agent/core.py` 的聊天模型 function-calling 完成；“语音记录”入口则由入口本身预先指定为记录。

**尚未定稿的统一边界**：

```text
ASR 原文
  → 单一理解权威（判断：实验事实 / 会话控制 / 工具意图 / 普通对话 / 不确定）
  → 安全分派（只给最小执行权限，不产生副作用）
  → 既有工具层执行
  → 结构化执行结果
  → PresentationIntent / copy / voice_delivery
```

**必须先回答再编码的问题**：

1. “普通开放式对话”是否单列分支，还是归入某种工具/弃权分支；
2. 工具意图合同使用稳定的领域动作（如 `START_TIMER`），还是直接暴露具体工具名（如 `start_timer`）；
3. 工具参数由统一理解一次性抽取，还是由确定性校验器补问缺失参数；
4. “语音记录”这种用户已明确指定用途的入口，是仍可直达记录理解，还是也必须经过同一分类器但携带入口约束；
5. 风险权限如何分级：只读查询、可撤销动作、持久化写入和高风险动作不能共用一种执行许可；
6. 统一判断失败时如何保证原始 ASR 先保存、且不误调用任何工具。

**约束**：在上述合同经用户确认前，不扩展 `UnifiedInputKind`、不修改提示词、不改 dispatch、不把聊天模型现有 function-calling 静默替换掉。当前状态为 **ANALYZED_ONLY**。

---

## 3. 已完成（截至 2026-08-20）

| 项 | 状态 |
|---|---|
| Phase B 输出层接线（B1-B4） | ✅ REAL_OK（800 tests） |
| C1 三张嘴收敛为单一 `window.speak` | ✅ AUTO_OK |
| C2a 后端 `voice_text`（词在后端） | ✅ AUTO_OK |
| **P0 复合确认+实体**（CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01） | ✅ **REAL_OK**（808 tests，会话 20260820_122234） |
| 语音入口治理（保留「语音记录」+「通话」，删「语音对话」+「头像点击通话」） | ✅ 完成 |
| 噪音误触调参（阈值/回滞/最短语音，治标） | ⚠️ 已调，治本见第 2 步 |

---

## 4. 有序路线图（2026-08-23 重新计划；按执行顺序，一次只推进一小项）

> 本次重排修正一个遗漏：原计划只完整拆出了“播什么”，没有把“何时播、是否抢占、
> 延后后何时失效”列成独立实施项。播放时机不能放进 `PresentationDeliveryPlan`，也不能由
> C3 barge-in 代替。正确依赖是：**重要性语义 → 内容资格 → 播放许可 → 多入口接线 → 打断验证**。

### 4.0 唯一执行清单（41 项，与 `PROJECT_TASK_CHECKLIST.md` 同步）

> 本表取代此前对话中的临时 27 项。状态只在两份文档同步更新后才算变更；当前唯一下一项为第 30 项。

| # | 任务 ID | 工作项 | 状态 |
|---:|---|---|---|
| 1 | `VOICE-C5-B1-PLAYBACK-REQUEST-CONTRACT` | 播放请求：重要性、创建时间、有效期、替代键 | `AUTO_OK` |
| 2 | `VOICE-C5-B2-PLAYBACK-CONTEXT-CONTRACT` | 用户讲话、ASR、TTS、会话阶段上下文合同 | `AUTO_OK` |
| 3 | `VOICE-C5-B3-PLAYBACK-DECISION-CONTRACT` | `READY / DEFERRED / DROP / PREEMPT` 决定合同 | `AUTO_OK` |
| 4 | `VOICE-C5-B4-PRIORITY-TIMING-RULES` | 重要性到播放时机的纯规则 | `AUTO_OK` |
| 5 | `VOICE-C5-C1-PLAYBACK-GATE` | 无副作用播放门控函数 | `AUTO_OK` |
| 6 | `VOICE-C5-C2-DEFERRED-QUEUE` | 延后语音队列 | `AUTO_OK` |
| 7 | `VOICE-C5-C3-REEVALUATION-TRIGGERS` | 状态变化后的重新判断触发器 | `AUTO_OK` |
| 8 | `VOICE-C5-C4-EXPIRY-DROP` | 超期语音丢弃 | `AUTO_OK` |
| 9 | `VOICE-C5-C5-SUPERSEDE` | 新追问替代旧追问 | `AUTO_OK` |
| 10 | `VOICE-C5-C6-SESSION-CANCEL` | 会话结束取消剩余语音 | `AUTO_OK` |
| 11 | `VOICE-C5-C7-RUNTIME-STATE-COORDINATOR` | VoiceRuntimeState 与唯一状态写入者 | `AUTO_OK` |
| 12 | `VOICE-C5-C8-PLAYBACK-CONTEXT-FACTORY` | 可变运行状态复制为不可变播放快照 | `AUTO_OK` |
| 13 | `VOICE-C5-C9-PLAYBACK-SCHEDULER` | Gate、Queue、TTS 的唯一编排者 | `AUTO_OK` |
| 14 | `VOICE-C5-C10-TTS-ADAPTER-EVENTS` | TTS play/stop 与四类执行事件合同 | `AUTO_OK` |
| 15 | `VOICE-C5-C11-PREEMPTION` | CRITICAL 限定抢占 | `AUTO_OK` |
| 16 | `VOICE-C5-C12-TTS-FAILURE-BOUNDARY` | TTS 失败隔离与重试边界 | `AUTO_OK` |
| 17 | `VOICE-C5-D1-SHARED-RECORD-SERVICE` | 抽取共享记录应用服务 | `AUTO_OK` |
| 18 | `VOICE-C5-D2-RECORD-USE-SERVICE` | `/record` 使用共享服务 | `AUTO_OK` |
| 19 | `VOICE-C5-D3-TOOL-USE-SERVICE` | `record_observation` tool 使用共享服务 | `AUTO_OK` |
| 20 | `VOICE-C5-D4-TOOL-PRESENTATION` | tool 结果进入 Intent/copy/DeliveryPlan | `AUTO_OK` |
| 21 | `VOICE-C5-D5-CHAT-SCREEN-ONLY-DELTA` | chat delta 降为纯屏幕事件 | `AUTO_OK` |
| 22 | `VOICE-C5-D6-VOICE-EVENT-BACKEND` | 后端发送显式 `voice_delivery` 事件 | `AUTO_OK` |
| 23 | `VOICE-C5-D7-REMOVE-DELTA-TTS` | 删除 `delta → enqueueSpeech` | `AUTO_OK` |
| 24 | `VOICE-C5-D8-REMOVE-TASK-QUEUED-TTS` | 删除 `task_queued → enqueueSpeech` | `AUTO_OK` |
| 25 | `VOICE-C5-D9-FRONTEND-PLAYBACK-EVENT` | 前端只消费获准播放事件 | `AUTO_OK` |
| 26 | `VOICE-C5-D10-THREE-ENTRY-INTEGRATION` | `/record`、tool、chat 经过同一 PlaybackScheduler | `AUTO_OK` |
| 27 | `VOICE-C5-E1-AUTO-ACCEPTANCE` | C5 自动回归与职责冻结 | `AUTO_OK` |
| 28 | `VOICE-C5-E2-FREE-FOLLOWUP-PRESERVATION` | 恢复自由实验统一语义追问并保持保存后呈现 | `AUTO_OK` |
| 29 | `VOICE-C5-E3-RECORD-STREAMING-FEEDBACK` | `/record` 流式首反馈与提交后最终结果 | `AUTO_OK` |
| 30 | `VOICE-C4-1-SILERO-CONTRACT` | 通话模式 Silero VAD 适配合同 | **NEXT** |
| 31 | `VOICE-C4-2-SILERO-INTEGRATION` | RMS 判断切换为 Silero | `TODO` |
| 32 | `VOICE-C4-3-VAD-REGRESSION` | VAD 边界、失败回退和前端回归 | `TODO` |
| 33 | `VOICE-C3-1-PLAYBACK-TIMING-REAL` | 真机验证不抢话、延后恢复、过期不补播 | `TODO` |
| 34 | `VOICE-C3-2-BARGE-IN-REAL` | 真机验证自激、漏检和打断停止 | `TODO` |
| 35 | `VOICE-D1-SESSION-OWNERSHIP` | 服务端按对话托管有状态会话 | `TODO` |
| 36 | `VOICE-D2-REAL-OBSERVER` | `/record` 原始 ASRResult 接 UnifiedObserver | `TODO` |
| 37 | `VOICE-D3-DROP-IN-SWAP` | 降级生产者切换为真实观察器 | `TODO` |
| 38 | `VOICE-D4-FIVE-BRANCH-CONTRACT` | 五分支理解合同 | `TODO` |
| 39 | `VOICE-D5-TOOL-PERMISSION-ROUTING` | 工具参数、风险权限与安全分派 | `TODO` |
| 40 | `VOICE-E1-FUNCTIONAL-REAL` | 真实功能验收 | `TODO` |
| 41 | `VOICE-E2E3-UX-AND-CLOSEOUT` | 九维体验验收与收尾 | `TODO` |

固定依赖：`1–16 播放许可与执行架构 → 17–27 多入口融合 → 28 自由实验追问回归修复 → 29 流式首反馈 → 30–32 VAD → 33–34 真机 → 35–39 统一理解/路由 → 40–41 收尾`。

第 28 项由 2026-08-24 真实验收发现：统一理解已经产出的 `missing_fields / should_ask_follow_up /
follow_up_question` 在 Web 桥接和共享记录服务中未被完整保留，自由实验因此只显示“已记录”。此前
`LLM-FOLLOWUP-STRICT-01` 只登记为未定案争议且误判为非迁移退化，没有进入正式执行表；现由本项
正式吸收。独立完成条件为：统一语义追问不被自由模式空方案评估覆盖；方案确定性追问保持原行为；
成功保存后才生成 `CLARIFICATION`；保存失败不产生追问或成功回执；新增红灯回归测试转绿且共享记录
服务原有测试继续通过。

自动闭环（2026-08-24）：`llm_bridge` 现在透传事件 `missing_fields` 及分析级追问合同；共享记录
服务只在 `step.mode == "free"`、正常 experiment 分支且追问合同完整时采用语义追问，方案模式继续
使用确定性评估。有效 evaluation 随记录落盘，保存成功后才投影 clarification。桥接/共享服务专项
`17/17`、相邻记录/tool/呈现回归 `59/59`、项目正式全量 `1012/1012` 通过。尚未做本轮真实模型与
浏览器录音复验，因此状态为 `AUTO_OK`，不标 `REAL_OK`。

第 29 项自动闭环（2026-08-24）：新增 `POST /record/stream` NDJSON 流；连接后先发
`record_status/understanding`，共享记录事务完成后才发 `record_result`。保存失败只发
`record_error`，不产生结果、回执或播放授权。旧 `POST /record` 保留兼容；桌面和手机录音入口均
使用 `ReadableStream` 增量消费。该项缩短首次可见反馈时间，不声称统一理解 JSON 或 TTS 已变为
内容级流式。流式/前端专项 `44/44`，相关合同复验 `40/40`，项目全量 `1017/1017` 通过；待用户
真实浏览器裁决体感，因此为 `AUTO_OK`。

### 4.1 语音运行与播放执行架构（2026-08-23 用户确认纳入计划）

```text
Microphone（只产音频帧）
  → VAD（人声开始/短暂停顿/继续/断句）
      ├→ 固化音频段 → ASR（只转文本）
      └→ VoiceStateCoordinator（唯一更新 VoiceRuntimeState）
             → PlaybackContextFactory（复制不可变 PlaybackContext）
                    → PlaybackScheduler
                         ├→ PlaybackGate（纯决定）
                         ├→ DeferredPlaybackQueue（只存 DEFERRED）
                         └→ TTSAdapter（只 play/stop）
                                → STARTED / FINISHED / STOPPED / FAILED
                                → VoiceStateCoordinator
```

固定职责与状态语义：

- `VoiceRuntimeState` 至少区分 `user_speaking / segment_capturing / asr_processing / tts_playing`；
  播放快照统一使用 `voice_input_busy = segment_capturing or asr_processing`，表达语音输入链仍忙，
  不再使用容易混淆 VAD 采集与 ASR 处理的 `asr_listening` 名称。
- 短暂停顿：`user_speaking=False`、`segment_capturing=True`，仍无播放窗口；只有 VAD 断句后
  `segment_capturing=False`，音频段才交给 ASR。
- `VoiceStateCoordinator` 是可变运行状态唯一写入者；设备和 Scheduler 只上报事件。
- `PlaybackContextFactory` 只在注入时钟下复制快照，不修改运行状态、不做播放决定。
- `PlaybackScheduler` 是 Gate、Queue、TTS 的唯一编排者；`/record`、tool、chat 不得直调 TTS。
- `TTSAdapter` 不判断业务优先级，只执行 `play/stop`，并报告
  `STARTED / FINISHED / STOPPED / FAILED`；PREEMPT 必须等待 STOPPED 后再确认请求仍有效才播放。

### 第 1 步：C5-A 内容资格基线 —— **已完成，保持职责边界**

进度（2026-08-21）：
- ✅ `voice_text` 已由后端确定性策略产出；前端只播放非空 `voice_text`。
- ✅ pre-TTS 闸门已落地：去代码/URL/Markdown、单条 25 字硬上限、整轮 2 条/50 字/1 问。
- ✅ `record_ack`（含“已记录”）默认静默；追问、确认回执、异常等按语义白名单朗读。
- ✅ abstention + `no_action` 投影为“没听清，请再说。”，不再沉默。
- ✅ `/chat/stream` 屏幕/语音分离事件合同已定义并测试：`screen_delta` 无播放权，只有 `voice_delivery` 可触发 TTS（尚未接线）。
- ✅ C5 内容交付 `PresentationDeliveryPlan` 接口已补齐：同一批 Intent 保留全部 `screen_intents`，并按渠道政策与 2 条/50 字/1 问预算产出 `voice_items`。该计划**不判断播放时机**，不含 `READY / DEFERRED` 或麦克风状态。
- ✅ `WebRenderer` 已改为消费 `PresentationDeliveryPlan`，不再重复执行语音白名单或预算；现有 `/record → render_many()` 因而成为首个生产消费者，返回 JSON 合同保持不变（51 项局部回归通过）。
- ✅ `/record` 与聊天工具 `record_observation` 的共享成功结果合同 `RecordObservationResult` 已定义：对象存在即表示落盘成功，统一携带 session/segment、原文、实体、抽取来源、结构化/降级状态、缺失字段、追问和偏差；不混入 HTTP messages、工具卡片或 TTS 字段（合同阶段 43 项局部回归通过）。
- ✅ `/record` 已成为 `RecordObservationResult` 的首个生产适配入口：严格先 `save_record()`，成功后才构造共享结果并生成 PresentationIntent/messages；落盘失败不生成用户消息，原 HTTP/数据库字段保持兼容（53 项局部回归通过）。聊天工具尚未接入，记录链尚未完全融合。
- ⏳ 实时播放闸门与有状态调度尚未设计/实现；见下面 C5-B/C5-C。
- ⏳ 工具结果 `present` 与 Intent/copy 的话术来源收敛仍待完成；见下面 C5-D。

> 为什么先做：噪音、打断都是"前端发声"的体验问题，但"语音说什么"（话术统一 + 硬截断）
> 才是"语音受控"这个根本目的的直接落地。先定"说什么"，再调"怎么听/怎么停"。

- **① 话术来源统一**：理解结果（`Intent → copy 层`）和工具结果（`present`）目前各走各的；
  应汇到**同一个话术层**，产出统一的 `text`（屏幕）+ `voice_text`（TTS），**TTS 只读这一个来源**。
- **② pre-TTS 硬约束**：TTS 前加确定性闸门——硬截断（字数/时长上限）、内容过滤（去 markdown/代码/URL）、
  分句选优先级；叠加认知负担预算（`PRESENT-03`：2 条/50 字/1 问）。**不靠 prompt 软约束**。
  **细则来源**：`OUTPUT_PRESENTATION_POLICY.md` §2（VOICE/SCREEN 四层输出，如"已记录"默认不朗读、追问允许朗读）+ §7（TTS 文本规则，如每条<25字、不问 JSON 字段名）；上屏外层时机见 `PRESENT_DESIGN.md` §13（六类时机合同）。
- **③ no_action 反馈**（`PRESENT-NOACTION-FEEDBACK-01`）：LLM 弃权（uncertain）时给反馈（"没听清，请再说"），不沉默。

#### C5-B：补齐重要性与播放时机合同（下一项，只定义合同）

**目的**：把“内容有资格朗读”和“当前获准播放”明确分开。`MessagePriority` 继续表达业务重要性，
新增的播放合同读取实时会话状态后给出决定，但本小项不启动 TTS、不接前端。

输入至少包含：

- `VoiceDeliveryItem` 对应的 `intent_id / kind / priority / voice_text`；
- 用户是否正在讲话、ASR 是否收音、TTS 是否播放；
- 当前实验/会话阶段；
- 消息创建时间、有效期和是否仍与当前问题相关。

输出使用互斥决定：

- `READY`：现在可以播放；
- `DEFERRED`：暂缓，条件变化后重新判断；
- `DROP`：已过期、被替代或失去上下文，不再播放；
- `PREEMPT`：高优先级消息可停止当前低优先级播放后立即播放。

最低规则基线：

| 重要性 | 默认时机规则 |
|---|---|
| `CRITICAL` | 可抢占低优先级播放；安全提示不能被普通消息压住 |
| `DIRECT_ACK` | 尽快播放，但不盖住用户正在进行的口述 |
| `ACTIVE_QUESTION` | 等本轮口述/ASR 收音结束后播放；旧问题被新问题替代时丢弃 |
| `REVIEW / SUMMARY` | 会话空闲窗口播放；超期可丢弃 |
| `ROUTINE / DEBUG` | 默认不获得语音资格；只显示或写日志 |

**验收**：合同测试覆盖四种决定；证明 `PresentationDeliveryPlan` 不含麦克风/TTS 状态，也不产生
`READY / DEFERRED / DROP / PREEMPT`。

#### C5-C：实现有状态 `PlaybackGate` 与延后队列

**目的**：将 C5-B 的纯合同落成唯一播放许可入口。

小项顺序：

1. 纯规则函数：`VoiceDeliveryItem + priority + PlaybackContext → PlaybackDecision`；
2. 有状态调度：保存延后项，并在用户停止讲话、ASR 结束、TTS 结束时重新判断；
3. 生命周期：支持过期、被新追问替代、会话结束取消；
4. 抢占：只有明确允许的高优先级消息能产生 `PREEMPT`；
5. 失败边界：TTS 失败不得丢失屏幕输出，也不得循环重播。

**验收**：Fake 时钟和 Fake 播放状态覆盖正常、延后恢复、过期丢弃、问题替代和高优先级抢占；
此时仍不接真实浏览器。

#### C5-D：统一 `/record`、tool、chat 的结果与呈现入口

**目的**：三个入口可以产生不同业务结果，但不能各自决定话术和发声。

按以下小项逐一接入，每完成一项单独停下验收：

1. 抽取共享记录应用服务，统一“组装持久化项 → 保存 → `RecordObservationResult`”；
2. `/record` 改用共享服务，保持 HTTP JSON 兼容；
3. `record_observation` tool 改用同一服务，删除重复的评估/保存路径；
4. tool 的结构化结果进入 `PresentationIntent → copy → DeliveryPlan`，不让模型重新决定记录回执；
5. 普通 chat 文本只走 `screen_delta`，不再天然拥有播放权；
6. 后端只通过 `voice_delivery` 事件发送获准候选，事件携带稳定 `intent_id`；
7. 前端删除 `delta/task_queued → enqueueSpeech` 直通路径，只消费播放许可事件；
8. 三入口最终都经过同一 `PlaybackGate` 后才能调用唯一 TTS 入口。

**验收**：记录保存失败不产生成功回执；同一记录结果在 `/record` 与 tool 中得到相同语义意图；
普通 `delta` 永不直接触发 TTS；未获 `READY/PREEMPT` 的语音项不能播放。

#### C5-E：C5 自动验收与职责冻结

- 内容层决定“表达什么”；
- `DeliveryPlan` 决定“哪些内容有语音资格”；
- `PlaybackGate` 决定“现在能否播放”；
- TTS 适配层只执行播放/停止，不做业务判断；
- C5 自动测试通过后只标 `AUTO_OK`，真实体验留到 C3。

### 第 2 步：C4 噪音误触治本 —— 换 Silero VAD

- 通话模式（`phone_call.js`）现在是**能量检测（RMS）**，天生怕噪音；调阈值只是让它更迟钝，治标不治本。
- 换成 **Silero VAD**（`vad_mode.js` 已在用），能分"人声 vs 噪音"。
- 完成后 C3 才验得干净（否则能量检测的噪音误触会污染 barge-in 判断）。

### 第 3 步：C3 真机验证播放时机与 barge-in

- 外放测**自激**（听到自己 TTS 就打断自己）、耳机测**漏检**（说"停"能否停住）。
- 验证 C5-C：用户讲话期间不抢播、讲话结束后延后项恢复、过期追问不补播、安全提示按规则抢占。
- 同时验 C1/C2a：追问念纯问题（无"小科"）、打断停得住。
- 留证据（终端输出 + 观察记录）。

### 第 4 步：Phase D 统一理解与路由（不再与 C5 输出职责混合）

- D1 服务端托管有状态会话（`reply_coordinator`，按对话 keyed、并发安全，不用全局单例）。
- D2 `/record` 输入改原始 `ASRResult`，接 `UnifiedObserver.observe`（含 LLM，带可回退开关）。
- D3 抽换降级生产者 → 真观察器，**输出层不动**，跑全量回归。
- **边界（契约 6）**：只收敛 `record_observation` 的规则抽取进统一链，**保留执行工具**（list/check/propose/confirm/calculate/time/memory/move_step）。
- 顺带解决："对，是X"等非"是的"前缀的确认（当前靠 LLM，可能 abstention）——由真观察器接管后统一处理。
- 在 C5 稳定之后再设计五分支理解合同：`experiment / control / tool / chat / uncertain`；
  它决定请求去哪里，不决定结果是否朗读。工具风险权限和参数校验在此阶段单列设计。

### 第 5 步：Phase E 收尾验收

- E1 功能验收（REAL_OK）：真实录音→记录→追问→确认闭环。
- E2 体验验收（UX_CONFIRMED）：按九维走查，最终裁决权在用户。
- E3 固化"明确不做"清单 + 更新三份必维文档。

---

## 5. 待解决问题清单（本轮发现，按优先级）

| 优先级 | 问题 | 落点 |
|---|---|---|
| 高 | 通话 energy-VAD 怕噪音（阈值调高治标） | 第 2 步 C4 |
| 高 | 话术来源不统一（Intent→copy vs 工具 present） | 第 1 步 C5 |
| 高 | 语音长文本无硬闸（靠 prompt 软约束） | 第 1 步 C5 |
| 高 | no_action 沉默（LLM 弃权无反馈） | 第 1 步 C5 |
| 高 | 重要性只有字段，尚未统一控制抢占/延后/丢弃 | 第 1 步 C5-B/C5-C |
| 高 | chat `delta/task_queued` 仍可绕过 Delivery 直接进入 TTS | 第 1 步 C5-D |
| 高 | 延后语音缺少过期、替代和会话结束取消规则 | 第 1 步 C5-C |
| 中 | "对，是X"等非"是的"前缀确认仍靠 LLM | 第 4 步 D |
| 中 | 朗读完状态字回不到"正在聆听"（已修、待统一两处措辞） | 第 1/3 步收尾 |
| 中 | ASR"是的"→"日的"误识别 | 已登记 `ASR-DEMO-NOISE-01` |
| 环境 | 工作区分裂（Desktop vs Documents 数据不同步） | 环境，非迁移 |

---

## 6. 明确不做

- 全双工。
- CLI 终端 UX 镀金。
- 在薄字典上另立平行投影。
- **提前通用化** QUERY/DENY/导出（留接缝、功能上线时再扩）。
- **把执行工具收敛进统一链**（违反契约 6：理解/执行分层）。
