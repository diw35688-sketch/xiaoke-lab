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

### 4.0 唯一执行清单（41 个主项 + 已登记子项，与 `PROJECT_TASK_CHECKLIST.md` 同步）

> 本表取代此前对话中的临时 27 项。状态只在两份文档同步更新后才算变更；当前唯一下一项为第 35 项。

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
| 26 | `VOICE-C5-D10-VOICE-CANDIDATE-INTEGRATION` | `/record` 与 chat tool 已有语音候选经过同一 PlaybackScheduler | `AUTO_OK` |
| 27 | `VOICE-C5-E1-AUTO-ACCEPTANCE` | C5 自动回归与职责冻结 | `AUTO_OK` |
| 28 | `VOICE-C5-E2-FREE-FOLLOWUP-PRESERVATION` | 恢复自由实验统一语义追问并保持保存后呈现 | `AUTO_OK` |
| 29 | `VOICE-C5-E3-RECORD-STREAMING-FEEDBACK` | `/record` 流式首反馈与提交后最终结果 | `AUTO_OK` |
| 30 | `VOICE-C4-1-SILERO-CONTRACT` | 通话模式 Silero VAD 适配合同 | `AUTO_OK` |
| 31 | `VOICE-C4-2-SILERO-INTEGRATION` | RMS 判断切换为 Silero | `AUTO_OK` |
| 32 | `VOICE-C4-3-VAD-REGRESSION` | VAD 边界、失败回退和前端回归 | `AUTO_OK` |
| 32a | `VOICE-C4-3A-SPEECH-STARTED-BRIDGE` | 讲话开始进入按会话隔离的服务端状态 | `AUTO_OK` |
| 32b | `VOICE-C4-3B-SPEECH-PAUSED-BRIDGE` | 短暂停顿进入同一会话状态 | `AUTO_OK` |
| 32c | `VOICE-C4-3C-SPEECH-RESUMED-BRIDGE` | 停顿后继续讲话进入同一会话 | `AUTO_OK` |
| 32d | `VOICE-C4-3D-SEGMENT-FINALIZED-ASR-BRIDGE` | 断句与 ASR 处理事件进入同一会话 | `AUTO_OK` |
| 32e | `VOICE-C4-3E-SESSION-PLAYBACK-STATE` | PlaybackScheduler 读取同一 conversation 的语音状态 | `AUTO_OK` |
| 32f | `VOICE-C4-3F-TTS-FEEDBACK-REEVALUATION` | 浏览器 TTS 事实反馈与延后项重评 | `AUTO_OK` |
| 33 | `VOICE-C6-UNIFIED-CONVERSATION-SURFACE` | 单聊天时间线、显式模式、分策略输出与真实播放收口 | **NEXT** |
| 33a | `VOICE-C6-A1-TURN-BLOCK-CONTRACT` | 统一 Turn/Block 输出合同 | `AUTO_OK` |
| 33b | `VOICE-C6-A2-SINGLE-CONVERSATION-STORE` | 唯一 ConversationTurnStore，移除前端双写 | `AUTO_OK` |
| 33c | `VOICE-C6-A3-CHAT-FIRST-SURFACE` | 方案/步骤/安全/记录/tool 收敛到聊天时间线 | `AUTO_OK` |
| 33d | `VOICE-C6-A4-EXPLICIT-MODE-SWITCH` | 自由聊天/自由实验记录/方案实验记录显式切换 | `AUTO_OK` |
| 33e | `VOICE-C6-A5-MODE-OUTPUT-POLICIES` | chat/实验记录/tool 分策略输出 | `AUTO_OK` |
| 33f | `VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX` | 三生产者统一外壳与交叉自动回归 | `AUTO_OK` |
| 33g | `VOICE-C3-1-PLAYBACK-TIMING-REAL` | 三种模式真机验证不抢话、延后恢复、过期不补播 | `TODO` |
| 34 | `VOICE-C3-2-BARGE-IN-REAL` | 真机验证自激、漏检和打断停止 | `TODO` |
| 35a | `VOICE-D0-INPUT-EVIDENCE-CONTRACT` | 文字/单次录音/连续通话的来源可信实验输入合同 | `AUTO_OK` |
| 35 | `VOICE-D1-SESSION-OWNERSHIP` | 服务端按对话与实验会话托管有状态会话 | `AUTO_OK` |
| 36 | `VOICE-D2-REAL-OBSERVER` | `/record` 原始 ASRResult 接 UnifiedObserver | `TODO` |
| 37 | `VOICE-D3-DROP-IN-SWAP` | 降级生产者切换为真实观察器 | `TODO` |
| 38 | `VOICE-D4-FIVE-BRANCH-CONTRACT` | 五分支理解合同 | `TODO` |
| 39 | `VOICE-D5-TOOL-PERMISSION-ROUTING` | 工具参数、风险权限与安全分派 | `TODO` |
| 40 | `VOICE-E1-FUNCTIONAL-REAL` | 真实功能验收 | `TODO` |
| 41 | `VOICE-E2E3-UX-AND-CLOSEOUT` | 九维体验验收与收尾 | `TODO` |

固定依赖调整为：`1–16 播放许可与执行架构 → 17–27 已有语音候选融合 → 28 自由实验追问回归修复 → 29 流式首反馈 → 30–32f VAD 与会话播放状态 → 33a–33f 单聊天时间线/显式模式/分策略输出 → 35a–37 原始三分支统一链接入 → 33g–34 在最终实验链上做真机播放/打断 → 38–39 另行设计五分支与工具权限 → 40–41 收尾`。33g–34 保留，不以旧记录链的真机结果替代统一链接入后的验收。

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
8. `/record` 与 chat tool 当前已有的语音候选经过同一 `PlaybackGate` 后才能调用唯一 TTS 入口；普通 chat 当时仍是纯屏幕正文，不能把本项扩大解释为完整三入口或统一前端回合。

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

第 30 项自动闭环（2026-08-24）：新增运行库无关的 `SileroVadAdapter` 合同。输入固定为
16 kHz 单声道、512 个归一化浮点采样的不可变帧；输出为讲话开始、短暂停顿、继续和断句四类事实，
并纯映射到现有 `VoiceRuntimeEventType`。运行时不可用、模型加载失败、推理失败或输出非法时明确
`USE_RMS`，且失败结果不能同时携带状态事件。本项不加载模型、不访问麦克风、不替换通话 RMS，
合同/相邻回归 `30/30`、项目正式全量 `1040/1040` 通过，因此标 `AUTO_OK`。当前唯一下一项为
第 31 项 `VOICE-C4-2-SILERO-INTEGRATION`。

第 31 项自动闭环（2026-08-24）：新增浏览器 `call_silero_vad.js`，固定使用 Silero v5，将
`vad-web` 的开始、逐帧概率和结束回调转换成讲话开始、短暂停顿、继续和断句事件。连续通话入口
现在优先启动 Silero；成功时直接把 16 kHz 段送入既有 WAV/ASR 队列，不再创建 RMS 麦克风链；
初始化或运行失败时先停止 Silero，再回退原 RMS。固定概率样例和 Node 行为测试证明适配状态机、
单一麦克风路径及初始化失败回退；它们不证明真实模型对真实音频的分类质量。组合回归 `46/46`、
项目正式全量 `1043/1043` 通过，因此标 `AUTO_OK`。当前唯一下一项为第 32 项
`VOICE-C4-3-VAD-REGRESSION`。

第 32 项自动闭环（2026-08-24）：真实模型探查复现 `VadSegmenter` 在 sherpa `front` 出队后再读
samples 导致空段的问题；先加入模拟底层失效的红灯测试，再把实现改为先复制/组装 `VoiceSegment`、
成功后才 `pop()`，未调整任何模型或 VAD 参数。固定真实模型回归使用 Git 已跟踪的
`web/voice/reference.wav`，从 24 kHz 确定性重采样到 16 kHz 并补 3 秒尾静音，实际得到 1 个非空段；
固定 2 秒静音和固定种子低水平宽带噪音均得到 0 段。浏览器 Node 测试同时覆盖短暂停顿/继续、
misfire、初始化失败、运行期失败、RMS 单一路径和挂断重启。VAD 单元 `20/20`、真实模型 `3/3`、
组合 `69/69`、项目正式全量 `1047/1047` 通过，因此标 `AUTO_OK`；真实房间、真实浏览器和外放/耳机
仍未验收。后续审计发现浏览器 VAD 事实尚未进入服务端 Coordinator，不能直接进真机。

32a 纠偏子项（2026-08-24）：`phone_call.js` 在 Silero 产生 `speech_started` 时，读取
`lab-agent-conversation-id` 并向 `/voice/runtime/event` 发送 `user_speech_started`。服务端只接受
数据库中已存在的会话，每个会话持有独立 `VoiceStateCoordinator`；未知会话 404，
重复开始请求幂等。Python 会话/路由专项 `4/4`、相关组合 `20/20`、项目全量 `1051/1051`
与 Node 行为测试通过。该状态尚未由
PlaybackScheduler 读取，也尚未接入恢复和断句。

32b 纠偏子项（2026-08-25）：`phone_call.js` 在 Silero 产生 `speech_paused` 时，
复用语音运行事件上报函数，携带同一 `conversation_id` 发送 `user_speech_paused`。
服务端显式映射到 `USER_SPEECH_PAUSED`，仅把该会话 `user_speaking` 改为 `false`，
保留 `segment_capturing=true`，因而短停顿不等于断句；重复停顿请求幂等。Python 会话/路由
`6/6`、相关组合 `43/43`、Node 行为测试和全量 `1053/1053` 通过。仍未接恢复、
断句、ASR/TTS 事件或 Scheduler，也未做真实设备验收。后续复核因此增补 32c–32f。

32c 纠偏子项（2026-08-25）：`phone_call.js` 在 Silero 产生 `speech_resumed` 时，
携带同一 `conversation_id` 发送 `user_speech_resumed`。服务端显式映射到
`USER_SPEECH_RESUMED`，只将同一片段的 `user_speaking` 恢复为 `true`，继续保留
`segment_capturing=true`；重复继续请求幂等。会话/路由专项 `8/8`、纯合同
`24/24`、Node 行为测试和全量 `1055/1055` 通过。复核同时确认断句/ASR、按会话 Scheduler 与 TTS 反馈仍未接通，
因此增补 32d–32f，将真机第 33 项退回 `TODO`；当前唯一下一项为 32d。

32d–32f 生产闭环（2026-08-25）：浏览器按顺序上报断句与 ASR 开始/成功/失败；
服务端为每个 conversation 共享同一 Coordinator、Scheduler 和延后队列，因此 A 讲话只延后 A，
B 不受影响。浏览器 TTS 对每个授权项回报 STARTED/FINISHED/STOPPED/FAILED；ASR 或 TTS 变空闲后
重评延后队列，可播项返回 READY，过期项返回 DROP/expired。专项 `48/48`、3 个 Node 行为测试、
JS 语法、`git diff --check` 和全量 `1060/1060` 通过，因此 32d–32f 标 `AUTO_OK`。真实麦克风/外放/耳机仍未验收，
当前唯一下一项为第 33 项。

第 33 项真实验收纠偏（2026-08-25）：真实页面证明普通 chat 的 ASR 与文字回复正常，但普通正文没有语音候选，因此没有 `/tts` 或 TTS 生命周期请求。试验性 `ASSISTANT_REPLY` 已定位缺口并完成相关专项 `43/43`，但仍复用实验语音首句/25 字限制，不是最终 chat 策略，也不构成 REAL_OK。进一步复核确认原第 26 项只统一了 `/record` 与 chat tool 已有语音候选的 PlaybackScheduler，不是完整三入口、统一回合或统一前端。

因此在真实播放前增加 C6 前置批次，目标不是把所有业务强塞进实验记录合同，而是“策略分开、输出机制统一”：

1. `33a TURN-BLOCK-CONTRACT`：定义 `conversation_id/turn_id/block_id/interaction_mode/input_source/voice source_block_id` 等身份；合同无保存、tool 执行和播放副作用。
2. `33b SINGLE-CONVERSATION-STORE`：服务端事件只进入一个 ConversationTurnStore；删除 `chatPushThink + runPushThink`、`chatPushTool + runPushTool` 双状态。
3. `33c CHAT-FIRST-SURFACE`：唯一聊天时间线呈现用户/助手、方案、步骤、安全、记录、tool、确认和状态消息块；管理页保留完整浏览/编辑，但不复制实时运行状态。
4. `33d EXPLICIT-MODE-SWITCH`：显式区分自由聊天、自由实验记录、方案实验记录。文字/单次录音/连续通话只表示输入来源；请求携带模式版本快照，切换不改变已提交回合的语义。
5. `33e MODE-OUTPUT-POLICIES`：自由 chat 自然交流且不自动保存；自由实验保存后可按语义缺口追问；方案实验按方案已知值/现场必测/偏差追问；tool 只呈现真实结果。三者最终生成同一 Turn/Block 与 voice identity。
6. `33f THREE-PRODUCER-AUTO-MATRIX`：覆盖屏幕、语音开关、讲话延后、过期、失败、幂等、模式切换、A/B 会话隔离和刷新不重放。
7. `33g PLAYBACK-TIMING-REAL`：分别用普通 chat、自由/方案实验记录和 tool 做外放/耳机真实不抢话、恢复和过期不补播验收。

模式层级固定为 `chat` 与 `experiment`；实验上下文再分 `free/protocol`。自由实验没有方案约束，但必须保留统一语义理解产生的必要追问：原始口述先保存，成功后每轮最多问一个影响复现、判断或安全的关键缺口，允许跳过/稍后补充，回答补回原记录。五分支 `experiment/control/tool/chat/uncertain` 仍留在 35–39，它只决定输入去向，不决定屏幕话术或播放时机。

33a 自动闭环（2026-08-25）：新增纯合同 `ConversationTurn / ConversationBlock`。回合固定
`conversation_id/request_id/turn_id/interaction_mode/experiment_context/mode_version/input_source`；
用户/助手文字以及方案、步骤、安全、记录、tool、确认、系统状态卡片和 voice 均由 Block 表示。VOICE 不复制屏幕正文，必须以
`source_block_id` 引用同一 turn 的非语音 Block，并携带唯一 `intent_id` 与 `MessagePriority`。
合同对象及嵌套 payload 不可变，`to_wire()` 可 JSON 序列化。纯函数 `decide_turn_replay()` 以
`(conversation_id, request_id)` 区分新请求、完全相同的幂等重放、模式版本冲突和其他内容冲突；
它不保存、不执行 tool、不修改 Store、不调度或播放。专项 `14/14`、相邻合同 `39/39`、项目全量 `1076/1076` 通过，因此标 `AUTO_OK`；
不构成前端或真实设备验收。当前唯一下一项为 33b `SINGLE-CONVERSATION-STORE`。

33b 自动闭环（2026-08-25）：新增浏览器唯一 `ConversationTurnStore`。当前 Chat 的用户文字、服务端
助手正文、think 和 Tool 卡片只写 Store，聊天时间线通过订阅渲染；运行画布删除实时
`stream/pendingIndex`、think/tool HTML 和 `runPushThink/runPushTool/runClearStream`，旧 Tool 转发器不再加载。
服务端 Tool pending/result 补同一 `tool_call_id`，Store 更新同一 `tool_card` Block。相同
`(conversation_id, request_id)` 的原始请求重放保留已有 Block，内容或模式版本变化报冲突；这只发生在
浏览器内存，不代表跨刷新持久化。专项组合 `27/27`、4 个 Node 行为测试、JS/Python 语法、
`git diff --check` 和项目全量 `1083/1083` 通过，因此标 `AUTO_OK`；未做真实浏览器走查。
当前唯一下一项为 33c `CHAT-FIRST-SURFACE`。

33c 自动闭环（2026-08-25）：新增 `conversationBlockView()`，把七类卡片 Block 翻译为共同的
`label/title/status/lines/meta/tone` 视图模型；用户/助手继续使用气泡，think 保留状态行，其他内容使用
统一聊天卡片骨架。方案会话只读事实投影为 protocol/step/safety Blocks；单次录音先建立 experiment Turn，
保存结果投影为 record/confirmation Blocks。原 run 画布不再加载，方案、试剂安全、记录和设置仍作为管理页。
专项 `30/30`、5 个 Node 行为测试、JS 语法和全量 `1091/1091` 通过，标 `AUTO_OK`；未做真实浏览器布局走查。
当前唯一下一项为 33d `EXPLICIT-MODE-SWITCH`。

33d 专项自动闭环（2026-08-25）：新增唯一 `interactionModeState` 和 Composer 三档显式选择；只有实际切换
才递增 `mode_version`。文字、单次录音、连续通话分别只标记 `text/single_recording/continuous_call`，
提交时冻结模式快照；Chat Store 与 HTTP 请求、录音 Store 与 HTTP 请求分别复用同一对象，异步期间再切换不会
改写旧请求。Chat/Record 请求模型共用服务端组合校验，但尚不按模式改变保存、Tool、回复或 TTS 策略。
专项组合 `22/22`、项目全量 `1098/1098`、3 个 Node 合同测试、JS 语法、Python 编译与 `git diff --check`
通过；未做真实浏览器验收。当前唯一下一项为
33e `MODE-OUTPUT-POLICIES`。

33e 自动闭环（2026-08-25）：新增纯 `OutputPolicy`，把冻结快照映射为 Chat、自由实验、方案实验三种
策略。统一 Composer 的文字/连续通话按模式分流；单次录音在 Chat 模式回到 Chat，只有实验模式进入共享记录服务。
Chat 的工具列表移除 `record_observation`，执行入口再设硬闸门；反向误投 `/record` 也在构造服务前拒绝。
自由实验显式忽略当前方案约束，保存原始事实后最多保留一个关键语义追问；方案实验要求有效方案，并使用既有
方案已知值、现场必测、偏差和安全评估，冲突在抽取/保存前失败。Tool 继续只呈现真实 outcome。
专项 `46/46`、全量 `1105/1105`、6 个 Node 行为测试、JS 语法和 `git diff --check` 通过；未做真实浏览器
验收。当前唯一下一项为 33f `THREE-PRODUCER-AUTO-MATRIX`。

33f 自动闭环（2026-08-25）：盘点发现实际语音事件尚未携带 33a 规定的 `source_block_id`。本轮把
`request_id/turn_id` 从 Composer 送到 Chat/Record，请求身份必须成对出现；Chat/Tool 语音绑定助手 Block，Record
追问绑定 confirmation Block。`source_block_id` 随 `VoiceDeliveryItem → PlaybackRequest → Scheduler 结果 →
voice_delivery` 保持不变，浏览器在播放前验证当前 Turn 中确有该 Block。Python 矩阵覆盖三生产者在 READY、讲话
DEFERRED、恢复、过期 DROP 和 A/B 会话隔离下的相同行为；Node 矩阵覆盖三种 Block、孤儿引用拒绝、幂等重放和模式
版本冲突。专项 `54/54`、全量 `1110/1110`、7 个 Node 行为测试及语法检查通过，未做真实浏览器/设备验收。
当前唯一下一项为 33g `PLAYBACK-TIMING-REAL`。

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

## 2026-08-25 补充：33c-UX 单主视图

外壳不再同时显示管理画布和聊天。默认路由改为 `chat`，唯一 Composer、ConversationTurnStore 和 Block 时间线占据主区域；`protocols/reagents/records/settings` 仅在用户点击导航时整页替换聊天，返回主对话时继续使用原聊天 DOM 与状态。

模式仍只影响 Block 策略：Chat 主要呈现 user/assistant/tool/status，实验模式可追加 protocol/step/safety/record/confirmation；模式不再映射为第二画布。专项回归 `27/27`、JS 语法和差异检查通过，属于 `AUTO_OK / UX_PENDING`，不代表真实浏览器体验已确认。唯一下一项为真实浏览器单主视图复验，通过后继续 33g 播放时序验收。

## 2026-08-25 补充：33g 前置语音入口与普通 Chat 播放资格恢复

运行检查证明语音链有两个独立阻塞：受限 Uvicorn 进程不能让 FunASR 创建 `ffmpeg -version` 子进程，导致 `/asr/warmup` 503；普通 Chat 的 `ASSISTANT_REPLY` 又错误携带 `ROUTINE`，被既有 Scheduler 静默策略固定判为 `DROP/context_lost`。服务现以同项目运行时在非受限环境启动并保留模型代理，SenseVoice 预热与固定 WAV 转写成功；Chat 优先级改为 `REVIEW`，空闲真实 SSE 已获得 `READY`。火山 TTS 连续三次真实合成成功。专项 `38/38`、全量 `1111/1111` 通过；仍需真实麦克风、浏览器 Audio 播放和人耳验收后才能升级真实状态。

浏览器复验继续显示无声时，服务日志证明 ASR 与 Chat 均 200、却无 `/tts`，定位到隐藏的旧头像静音状态。单主视图现把语音开关放到聊天头部，保留 `tts-muted` 持久值但不再让它不可操作；播放、禁用、来源拒绝和播放器缺失均发出可观察结果。相关组合 `50/50` 与 Node 行为测试通过，PID 29900 已加载新缓存版本并完成 ASR 预热。仍不把它标为真实播放通过。

自由实验真实截图进一步发现 `lab_panel.js` 仍作为第二个投影消费者自动展开，和聊天中的 protocol/record/confirmation Blocks 重复。历史接口证明第 71 段只保存一次。现停止加载整份遗留面板并移除 `voice_asr.js::labRender`，保留 shell 的方案/安全/记录管理页；相关回归 `43/43` 通过，PID 25484 现场确认旧脚本未加载且 ASR 已预热。待用户刷新确认后才能标记 UX 通过。

方案模式真实走查又发现 Composer 模式与服务端活动方案是两个独立状态：原按钮可先显示“方案实验”，但 `/protocols/session` 仍为 `free`，因而下一 Turn 正确地投影出自由实验 Block。现把有效方案作为进入 `experiment/protocol` 的前置条件；无活动方案时路由到方案选择页，只有选中具体方案且服务端确认后才同步模式并回到单聊天时间线。相关组合 `29/29` 通过，仍待真实浏览器确认选择与返回体验。

## 2026-08-25 补充：Chat 语音输出合同已决定、尚未编码

用户决定普通 Chat 的可朗读正文必须作为独立可见 Block，`voice_text` 与来源 Block 正文逐字一致；默认回复在生成阶段以约 10 秒为长度目标，禁止显示长文后仅朗读第一句或在播放中硬截断。用户明确“继续说”时使用单回合 continuation 并建立新的详细 Block，不转为永久偏好。用户打断先暂停且不自动恢复；明确指定重读时根据历史可见 Block 原文重新合成音频，不重新调用模型改写。

连续 VAD/ASR 误触的第 1、2 次显示并朗读反馈，第 3 次起只更新屏幕状态、不再生成反馈语音，但连续监听保持开启；正式建立有效 `user_text` Block 后清零并解除抑制。Free/Protocol 的 Block 语音矩阵、10 秒字数、历史重读引用形式和前端样式均未决定。当前仍是设计状态，生产代码中的首句/25 字限制尚未修改。

## 2026-08-25 补充：Free / Protocol Experiment 语音合同已决定、尚未编码

两种 Experiment 均要求实际 `voice_text` 与独立可见来源 Block 正文逐字一致；一次完整 Experiment Turn 最多产生一个独立、可见的语音汇总 Block，按中文语速估算最长约 15 秒。业务 Block 可以有多个并分别维护状态，但不逐块进入 TTS；需要说出的结果必须在汇总 Block 形成前组织完整，不得显示后截断。用户原话显示但不回读，保存成功的 `record_card` 只显示不朗读，保存失败不得产生成功反馈；现有通用 `safety_alert` 只显示不读，明确危险动作判断与 `danger_intervention` 当前不存在，不能冒充已有能力。

Free 必须先保存原始事实，成功后最多一个关键语义追问；追问与本轮必要解释分别作为业务 Block 显示，确需朗读时合成一个可见语音汇总 Block，没有需说内容时允许静默保存。Protocol 必须先有用户选择并经服务端确认的活动方案；`protocol_card` 只在进入/切换/版本变化时出现一次，`step_card` 只在进入/切换/版本变化时出现一次，不能随每条记录 Turn 重复。现场事实保存回执静默；本轮新偏差、必测缺口或确认内容可由多个 `confirmation_card` 分别维护，但自动语音统一为至多一个汇总 Block。当前 protocol/step 仍按 `turnId` 重复投影且语音仍有首句/25 字限制，整体状态为 `DESIGN_DECIDED / NOT_CODED`。

## 2026-08-25 补充：统一可见语音 Block 纯合同 AUTO_OK

新增 `src/core/spoken_output.py`，以冻结的 mode/context/reply_scope 选择纯预算：Chat 默认 50 字估算约 10 秒，单回合 continuation 不套默认预算，Free/Protocol 整 Turn 唯一自动语音 75 字估算约 15 秒。构造结果固定为一个可见 `assistant_text(role=spoken)` 与一个 payload 为空、只通过 `source_block_id` 引用它的 `VOICE`；`voice_text` 只能直接读取可见 Block正文，超预算在 Block 建立前失败，禁止截断。

新增专项 `6/6`、相邻组合 `30/30`、项目全量 `1119/1119`、Python编译和差异检查通过，标 `AUTO_OK`。本轮未接生产 Chat/Record、前端 Store/渲染、Scheduler 或 TTS，当前页面仍使用旧首句/25 字路径；唯一下一步是只接普通 Chat 生产链，不同时接 Experiment。

## 2026-08-25 补充：普通 Chat 生产接入

普通 Chat 现由模型生成最多50个中文字符的纯文本完整短答，`chat_stream` 先缓冲验证，再发布一个可见 `assistant_text(role=spoken)`；唯一 voice item从同一正文派生并引用 `${turnId}:spoken`，不再经过首句/25字内容策略。为让50字预算穿过Scheduler重建，新增 `VoiceDeliveryItem.max_chars → PlaybackRequest.max_chars → WebPlaybackService`传递，旧Record/Tool默认仍保持25字策略。

前端只改 `streaming_chat_v2.js` 的Chat Block身份和发布时间：`:assistant`改为`:spoken`、payload增加`role=spoken`、完整验证后一次显示；没有新增或隐藏界面区域，Experiment路径未改。专项迭代后项目全量 `1123/1123` 通过。PID 14492现场使用官方DeepSeek得到screen/voice逐字一致、`:spoken`来源和Scheduler READY；真实 `/tts` 返回200、audio/mpeg、118560 bytes，ASR已预热。仍需用户浏览器刷新、人耳完整播放和约10秒体验确认后才能标真实通过。

## 2026-08-26 补充：统一链来源可信输入合同

当前代码继续作为唯一实现基线，不从 `Desktop\asr_demo` 复制或覆盖文件；桌面仓库只用于核对原始职责。新增 `ExperimentTurnInput` 作为 Web 到统一链的纯数据接缝：文字输入没有 ASR 证据，单次录音和连续通话必须携带匹配的最终 `ASRResult`，同时冻结请求/回合身份和实验模式快照。专项 `9/9`、相邻 `35/35`、正式全量 `1162/1162` 通过，仅证明合同和回归，不证明生产接线或真实识别。当前唯一下一项为第 35 项会话所有权。

## 2026-08-26 补充：统一链会话所有权 AUTO_OK

新增 `ExperimentRuntimeSessionRegistry`，以 `(conversation_id, lab_session_id)` 为键分别托管 `ReplyCoordinator`、`SessionContext` 和单工作线程执行器。同一会话 FIFO 串行，不同会话可并行；完全一致的请求重试复用原任务，请求身份冲突和队列背压都有显式错误。专项 `11/11`、相邻 `43/43`、正式全量 `1175/1175` 通过。本轮未从桌面参考仓库复制代码，也尚未连接生产 `/record`、`UnifiedObserver` 或真实 LLM；下一项是在该会话边界内接入并验证真实观察器，不能提前宣称识别完成。
