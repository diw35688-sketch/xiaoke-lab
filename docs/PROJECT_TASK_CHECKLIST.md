# asr_demo 项目任务清单

最后更新：2026-08-25（可搬家的一键启动与新手交付指南，见维护日志）

> 本文件是当前任务、优先级和验收状态的唯一来源。架构说明、环境命令和下一会话摘要
> 分别见 `PROJECT_ARCHITECTURE.md`、`ENVIRONMENT_SETUP.md` 和
> `NEXT_SESSION_HANDOFF_2026-08-09.md`；第 6 节维护日志只作证据追溯，不决定当前下一项。

项目根目录：以仓库实际存放位置为准；启动器不得依赖个人绝对路径。

## 1. 使用规则

本文件是项目推进的唯一任务总表。每轮开发和真实验收结束后都要更新。

状态定义：

| 状态 | 含义 |
|---|---|
| `TODO` | 尚未开始 |
| `DESIGN` | 正在定义数据结构或接口 |
| `CODED` | 代码已完成，但自动测试尚未全部通过 |
| `AUTO_OK` | 单元/集成/回归测试通过，但尚未真实环境验收 |
| `REAL_OK` | 已使用真实麦克风、ASR、LLM 或完整流程验收 |
| `BLOCKED` | 存在明确阻塞条件 |

体验状态（功能验收之外的独立维度，定义见 `docs/UX_WALKTHROUGH_CHECKLIST.md`）：

| 状态 | 含义 |
|---|---|
| `UX_PENDING` | 本轮涉及输出面但尚未走查 |
| `UX_WALKED` | 走查完成，证据在 UX_WALKTHROUGH_CHECKLIST.md 第 8 节 |
| `UX_CONFIRMED` | 用户实际体验后确认通过 |
| `UX_ISSUES` | 走查发现体验问题（登记：现象/复现路径/期望） |

> 注意：`REAL_OK`（功能验收）≠ `UX_CONFIRMED`（体验验收）。两者不能互相替代，
> agent 不得把功能验收通过写成体验验收通过。

状态升级必须有证据：

```text
TODO → DESIGN → CODED → AUTO_OK → REAL_OK
```

不能因为“代码看起来正确”直接标记为 `REAL_OK`。

优先级定义：

| 标志 | 含义 |
|---|---|
| `P0` | 当前主线或阻塞项；不完成就不应继续后续能力 |
| `P1` | TTS前核心闭环；P0完成后按依赖顺序推进 |
| `P2` | 重要增强、稳定性或跨模块集成；不阻塞当前小步 |
| `P3` | 明确后置、依赖外部条件或表现层增强 |

优先级表示执行紧迫度，状态表示完成证据，两者不能互相替代。已完成任务仍保留其架构优先级；
若发现数据丢失、安全或主流程阻断问题，可在维护日志说明证据后提升优先级。

### 硬问题 vs 软问题（阻塞判定，2026-08-14 用户指出"每次都标必修"后建立）

> 判据：**用户能否完成一次实验记录、并拿到正确数据？**

| 类别 | 定义 | 是否阻塞主流程/PRESENT |
|---|---|---|
| **硬问题** | 程序崩溃（未捕获异常导致退出/会话中断）；数据丢失或错位（原始 ASR/事件/确认记录未落盘或落错）；核心交互失败（结束命令失效且无法补救、追问无法创建、回答无法提交、待确认状态错乱） | **是，必修** |
| **软问题** | 显示/话术问题（开发语言、双句号、提示缺失但状态正确）；ASR 误识别增多（语义理解仍能兜底、数据不丢）；边缘表达未命中（不崩、可重试） | **否，与 PRESENT 并行处理、出现即修，不阻塞** |

> **纪律**：真实验收暴露问题，必须先按此判据归类再定优先级，不得"发现即必修"。
> 软问题与 PRESENT 并行处理（出现即修）；只有硬问题才能推迟 PRESENT。
> **推进闸门（用户 2026-08-14 决策）**：硬问题修完即进 PRESENT，**不设固定日期**（进展快于计划则提前）。
> **补充（2026-08-14 评委指出）**：还有一类"文案承诺与实际行为不一致"（如 main.py 打印"无需等待 LLM 处理完成"但实际同步等待），它既非崩溃也非数据错，原判据拦不住。规则：**凡是给用户的行为承诺与实际不符，按后果归类——导致用户误判操作节奏的（如"无需等待"）算硬问题（核心交互节奏错误）；仅措辞不当的算软问题。** 已登记 `SYNC-UI-CLAIMS-01` 专项核查。

## 2. 当前测试基线

- 当前全量自动测试：`1190 tests OK`（Python 3.11.9 一次性运行时 + 现有 `.venv` 依赖，2026-08-26，自由实验六步受控验证完成后实测；现有 `.venv` 启动器仍指向已缺失的 Python 3.11）
- 环境执行纪律：受限环境出现进程启动错误时，必须先在获准的非受限环境用同一条项目 `.venv` 原命令重试；不得直接诊断 `.venv` 或启动器损坏，也不得用另一解释器混载 `.venv` 包代替正式全量验收
- 最近 PRESENT 真实验收会话：`20260815_212615`（补充复验 `20260815_213926`）
- 最近 PRESENT 双会话复验：`20260816_143151` → `20260816_143201`（同进程再次唤醒成功，零第三方泄漏）
- 最近真实会话已验证：编号分离、结束汇总用户语言、回执及时（九维表维 4/5/9 通过）；同时登记了输出泄漏、`no_action` 沉默、缺字段复核和 ASR 误识别问题。

恢复工作时先运行：

```powershell
Set-Location <项目目录>

.\.venv\Scripts\python.exe -B -m unittest discover `
    -s tests `
    -v
```

## 3. 当前唯一下一项

**`VOICE-C3-1-PLAYBACK-TIMING-REAL`（33g）：在真实浏览器分别验收 Chat、Record、Tool 的播放时机。**

33b 已完成自动软件闭环：新增唯一前端 `ConversationTurnStore`，当前 Chat 的用户文字、服务端助手正文、think 状态和 Tool 卡片只写 Store，再由聊天时间线订阅渲染；运行画布删除 `stream/pendingIndex` 与 `runPushThink/runPushTool/runClearStream`，旧 `tool_cards.js` 转发器不再加载。Tool 事件由服务端补稳定 `tool_call_id`，同一调用的 pending/result 更新同一 Block。Store 以 `(conversation_id, request_id)` 处理完全相同重放并拒绝内容/模式版本冲突，但不保存数据库、不执行 Tool、不播放。专项组合 `27/27`、4 个 Node 行为测试、JS/Python 语法、`git diff --check` 和项目全量 `1083/1083` 通过，因此仅标 `AUTO_OK`；尚未做真实浏览器走查。

第 32 阶段剩余生产链已完成自动闭环：

- `segment_finalized` 与 ASR 开始/成功/失败进入同一 conversation 状态；
- 每个 conversation 拥有共享同一 `VoiceStateCoordinator` 的 Scheduler 与延后队列，A 讲话只延后 A，B 不受影响；
- ASR/TTS 状态变空闲时重评延后项，未过期返回 `READY`，过期返回 `DROP/expired`；
- 浏览器播放单元携带 `intent_id/priority`，回报 `tts_started/finished/stopped/failed`；
- 专项 `48/48`、全部 3 个 Node 行为测试、JS 语法与全量 `1060/1060` 通过。未做真实设备验收，因此仅为 `AUTO_OK`。

纠偏子项 `VOICE-C4-3C-SPEECH-RESUMED-BRIDGE` 已完成自动验收：

- Silero `speech_resumed` 携带现有 `conversation_id` 发送 `user_speech_resumed`；
- 服务端将其映射到 `USER_SPEECH_RESUMED`，同一片段内只使 `user_speaking=false -> true`，`segment_capturing` 继续为 `true`；
- 重复继续请求幂等，不串改其他会话；会话/路由专项 `8/8`、纯合同 `24/24` 和 Node 行为测试通过。
- 未接断句、ASR、按会话 Scheduler 或 TTS 反馈，不产生真机结论。

纠偏子项 `VOICE-C4-3B-SPEECH-PAUSED-BRIDGE` 已完成自动验收：

- Silero `speech_paused` 携带浏览器现有 `conversation_id` 请求 `/voice/runtime/event`；
- 服务端映射为 `USER_SPEECH_PAUSED`，仅使同一会话 `user_speaking=false`，保留 `segment_capturing=true`；
- 重复停顿请求幂等，不串改其他会话，也不伪造断句；
- Python 会话/路由专项 `6/6`、相关组合 `43/43`、Node 行为测试和项目全量 `1053/1053` 通过。
- 未接恢复、断句、ASR/TTS 事件或 Scheduler，未做真实浏览器/麦克风验收。

纠偏子项 `VOICE-C4-3A-SPEECH-STARTED-BRIDGE` 已完成自动验收：

- Silero `speech_started` 携带浏览器现有 `conversation_id` 请求 `/voice/runtime/event`；
- 服务端查库确认会话已存在，不存在返回 404，不偷偷新建会话；
- 每个会话使用独立 `VoiceStateCoordinator`，开始事件使 `user_speaking=true` 且 `segment_capturing=true`；
- Python 会话/路由专项 `4/4` 与 Node 浏览器行为测试通过；未接停顿、恢复、断句，未让 Scheduler 消费该状态，未做真机验收。
- 相关组合回归 `20/20`，项目原 `.venv` 全量 `1051/1051` 通过。

上一项 `VOICE-C4-3-VAD-REGRESSION` 已完成自动验收：

- 红灯测试复现真实 sherpa `front` 在 `pop()` 后底层 samples 失效、随后被误判为空段的问题；修复为先复制/组装 `VoiceSegment`，成功后再出队；
- 使用 Git 已跟踪的 `web/voice/reference.wav`，确定性重采样至 16 kHz 并补 3 秒尾静音，本地真实 Silero 产出 1 个非空语音段；
- 同一真实模型对固定 2 秒静音和固定种子、固定幅度的 3 秒低水平宽带噪音均产出 0 个语音段；
- 浏览器概率状态机覆盖短暂停顿/继续/断句/misfire，Node 行为测试覆盖初始化失败、运行期失败、单一麦克风路径及挂断后重启；
- VAD 单元测试 `20/20`、真实模型固定样例 `3/3`、相关组合回归 `69/69`、项目正式全量 `1047/1047` 通过。

上一项 `VOICE-C4-2-SILERO-INTEGRATION` 已完成自动验收：

- 新增浏览器 `call_silero_vad.js`，按固定版本动态加载 ONNX Runtime 与 `vad-web`，把模型回调转换为第 30 项四类语义事件；
- `phone_call.js` 以 Silero 为正常主路径，直接接收其 16 kHz 音频段并进入原 WAV/ASR 队列，不再同时启动 RMS 麦克风链；
- Silero 初始化或运行失败时先停用适配器，再回退原 RMS 采集；两条路径不会同时持有麦克风；
- 固定概率样例证明低人声概率不建段，并覆盖开始、停顿、继续、断句顺序；这是适配状态机证据，不是实际模型音频准确率证据；
- Silero/状态/页面/C5 组合回归 `46/46`，新增 Node 行为测试均通过，项目正式全量 `1043/1043` 通过。

上一项 `VOICE-C4-1-SILERO-CONTRACT` 已完成自动验收：

- 固定适配器输入为 16 kHz、单声道、每帧 512 个归一化浮点采样，并校验序号与单调时间；
- 定义讲话开始、短暂停顿、继续和断句四类语义事件，纯映射到现有 `VoiceRuntimeEventType`；
- 模型运行时不可用、加载失败、推理失败或输出非法时，合同明确回退现有 RMS；失败结果不得同时伪造状态事件；
- 合同不加载模型、不访问麦克风、不修改 Coordinator，也不替换 `phone_call.js` 的 RMS；
- 合同与相邻状态链回归 `30/30`，项目正式全量 `1040/1040` 通过。

上一项 `VOICE-C5-E1-AUTO-ACCEPTANCE` 已完成自动验收：

- 新增 7 条 C5 架构冻结测试，锁定 DeliveryPlan、Gate、Scheduler、Web producer 与前端执行边界；
- 删除活动版和遗留版流式客户端中不可达的 `done → speechBuffer → enqueueSpeech` 死代码，防止旁路被未来赋值复活；
- C5 请求、状态、Gate、Queue、抢占、失败边界、记录/tool/chat 和前端专项 `190/190`；Node 行为与两份流式客户端语法检查通过；
- 项目级 discover 执行 898 项，17 个模块加载错误、0 个业务断言失败；错误均来自现有 cp311 NumPy/Pydantic 二进制与当前 Python 3.12 不兼容，不能宣称项目全量通过。

第 28 项已自动闭环：统一理解追问合同在自由模式被保留并随有效 evaluation 落盘；方案模式仍以
确定性评估为权威，保存失败仍不会生成成功回执或追问。专项 `17/17`、相邻回归 `59/59`、项目正式
全量 `1012/1012` 通过；尚未完成本轮真实模型和浏览器录音复验，因此只标 `AUTO_OK`。

第 29 项已自动闭环：新增 `/record/stream` NDJSON 流，立即发送理解状态，保存成功后才发送最终
结果；保存失败只发错误事件。桌面和手机均增量消费，旧 `/record` 保持兼容。专项 `44/44`、相关
合同 `40/40`、项目全量 `1017/1017` 通过；真实浏览器体感尚待用户裁决。

第 33 项是真机验收：在真实浏览器和麦克风条件下，分别用外放与耳机观察用户讲话期间不抢播、
讲话结束后延后项恢复、过期追问不补播，并留下设备、浏览器、输入、终端和观察记录。该项需要用户
参与真实环境裁决；不把第 32 项的本地模型或模拟回归替代为真机结论。

`END_ONLY` 第四刀已完成自动闭环：结束时只交付一个结构化摘要，合并实验步骤数与待确认明细；
零待确认也明确说明，旧“提交 M 段实验口述”内部术语已删除。专项 41/41、全量 571/571 通过。
同轮已将即时收尾回执从 `SESSION_SUMMARY` 改为 `SESSION_CLOSING_SUMMARY`，无兼容双名，
不影响离线核验脚本的 `session_summary()` 统计函数，也未引入 LLM 正式总结。
真实验收仍统一并入 `PRESENT-FINAL-UX-VERIFY-01`。

`PRESENT-FEEDBACK-REGRESSION-01` 已自动闭环：程序级 pump 在初始化前启动，启动中、就绪、
唤醒成功和 Ctrl+C 退出都经同一 Coordinator/Pump 交付；会话复用该链路，
不再每次唤醒新建第二条生产输出链。启动期间按 Ctrl+C 也能显示退出回执。
专项 56/56、全量 578/578 通过。

`PRESENT-PUMP-FLUSH-01` 已自动闭环：Coordinator 原子跟踪 pending、deferred 与 in-flight
消息，Pump 在 renderer/output 真正返回后才确认完成；`flush(timeout)` 超时返回 `False`，
交付失败抛出带 intent/error/reason 的结构化异常，同时失败消息不会阻断后续消息。
慢 output、失败隔离、去重与 deferred 计数均有合同测试；专项 24/24、全量 584/584 通过。

`PRESENT-LEGACY-MESSAGE-CLEANUP-01` 已自动闭环：`MessageKind`、`MessagePriority`、
`ScreenTarget` 三个现役语义枚举归位到 `presentation_intent.py`；旧 `PresentationMessage`
及其 `DeliveryChannel`、`MessageStatus`、`SpeechPolicy`、`VoiceDeliveryPolicy`、专属 10 项测试
全部删除，无兼容别名。`src/tests` 旧引用为 0；专项 86/86、删除后全量 574/574 通过。

`PRESENT-FIX-LEAK-01` 已完成第二轮自动修复：recorder/VAD/wakeword/state/LLM/ASR/main 生产模块
均无直接 `print()`；内部状态走 logging，FunASR 初始化和 generate 显式设置
`disable_update=True`、`disable_pbar=True`、`disable_log=True`，并以 `TQDM_DISABLE=1` 关闭
ModelScope 下载条。真实会话 `20260816_141745` 首轮仍发现版本检查/下载输出，现已针对性修复；
二次会话 `20260816_142352` 证实下载日志/进度条已消失，但 FunASR 1.4.1 在 disable 判断前仍
无条件打印版本号；现已只替换其 `check_for_update` 入口。同时 READY 补 Ctrl+C 指引，新增
WAITING 状态提示再次唤醒。专项 63/63、全量 576/576 通过；会话 `20260816_142945` 与
双会话 `20260816_143151` → `20260816_143201` 已完成真实复验。

PRESENT 之外的 Query/Safety/RAG 真实接入、ASR 路演稳定性和 LLM 格式容错仍保留在任务库，
但不改变本节的当前执行顺序。

## 3.1 当前执行看板

> 本看板只放近期事项；完整任务库与历史证据见第 4 节和维护日志。

### 3.1-VOICE 语音 Web 当前唯一施工清单（2026-08-26 更新，41 个主项 + 已登记子项）

> 本表取代此前对话中临时列出的 27 项；旧表遗漏了播放许可层，不能继续作为执行依据。
> 一次只推进一项，顺序以本表为准；完整设计说明见
> `docs/VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 第 4 节。

| # | 任务 ID | 工作项 | 状态 | 独立验收边界 |
|---:|---|---|---|---|
| 1 | `VOICE-C5-B1-PLAYBACK-REQUEST-CONTRACT` | 定义带 `priority`、创建时间、有效期和替代键的播放请求 | `AUTO_OK` | 合同正常/边界/失败测试；DeliveryPlan 职责不扩张 |
| 2 | `VOICE-C5-B2-PLAYBACK-CONTEXT-CONTRACT` | 定义用户讲话、ASR 收音、TTS 播放和会话阶段快照 | `AUTO_OK` | 上下文为不可变快照，不直接控制设备 |
| 3 | `VOICE-C5-B3-PLAYBACK-DECISION-CONTRACT` | 定义 `READY / DEFERRED / DROP / PREEMPT` 互斥结果 | `AUTO_OK` | 四种结果及原因码合同测试 |
| 4 | `VOICE-C5-B4-PRIORITY-TIMING-RULES` | 建立 `MessagePriority` 到播放时机的纯规则 | `AUTO_OK` | 覆盖讲话中、收音中、播放中和空闲状态 |
| 5 | `VOICE-C5-C1-PLAYBACK-GATE` | 实现无副作用的播放门控函数 | `AUTO_OK` | 相同请求和上下文得到确定性决定 |
| 6 | `VOICE-C5-C2-DEFERRED-QUEUE` | 建立延后语音队列 | `AUTO_OK` | DEFERRED 项不丢失、不立即播放 |
| 7 | `VOICE-C5-C3-REEVALUATION-TRIGGERS` | 在停止讲话、ASR/TTS 结束时重新判断 | `AUTO_OK` | Fake 状态转换验证恢复时机 |
| 8 | `VOICE-C5-C4-EXPIRY-DROP` | 实现超期语音丢弃 | `AUTO_OK` | Fake 时钟证明过期项不补播 |
| 9 | `VOICE-C5-C5-SUPERSEDE` | 新追问替代旧追问 | `AUTO_OK` | 旧上下文问题被 DROP，只保留新问题 |
| 10 | `VOICE-C5-C6-SESSION-CANCEL` | 会话结束时取消剩余语音 | `AUTO_OK` | 结束后队列清空且不再恢复 |
| 11 | `VOICE-C5-C7-RUNTIME-STATE-COORDINATOR` | VoiceRuntimeState 与唯一状态写入者 | `AUTO_OK` | 事件归约确定性；短暂停顿不等于断句 |
| 12 | `VOICE-C5-C8-PLAYBACK-CONTEXT-FACTORY` | 运行状态复制为不可变播放快照 | `AUTO_OK` | 注入时钟；工厂不改状态、不做决定 |
| 13 | `VOICE-C5-C9-PLAYBACK-SCHEDULER` | Gate、Queue、TTS 的唯一编排者 | `AUTO_OK` | READY/DEFERRED/DROP/PREEMPT 各有单一路径 |
| 14 | `VOICE-C5-C10-TTS-ADAPTER-EVENTS` | TTS play/stop 与四类执行事件合同 | `AUTO_OK` | STARTED/FINISHED/STOPPED/FAILED 互斥且可追踪 |
| 15 | `VOICE-C5-C11-PREEMPTION` | 限定 CRITICAL 抢占低优先级播放 | `AUTO_OK` | 等 STOPPED 后复核有效性；普通消息不能抢占 |
| 16 | `VOICE-C5-C12-TTS-FAILURE-BOUNDARY` | 隔离 TTS 失败和重试 | `AUTO_OK` | 屏幕输出不丢、失败项不循环播放 |
| 17 | `VOICE-C5-D1-SHARED-RECORD-SERVICE` | 抽取共享记录应用服务 | `AUTO_OK` | 统一组装、保存、成功结果生成顺序 |
| 18 | `VOICE-C5-D2-RECORD-USE-SERVICE` | `/record` 使用共享服务 | `AUTO_OK` | HTTP JSON 兼容，保存失败无成功回执 |
| 19 | `VOICE-C5-D3-TOOL-USE-SERVICE` | `record_observation` tool 使用共享服务 | `AUTO_OK` | 删除重复评估/保存路径，工具合同兼容 |
| 20 | `VOICE-C5-D4-TOOL-PRESENTATION` | tool 结构化结果进入 Intent/copy/DeliveryPlan | `AUTO_OK` | 模型不重新决定记录回执话术 |
| 21 | `VOICE-C5-D5-CHAT-SCREEN-ONLY-DELTA` | chat `delta` 降为纯屏幕事件 | `AUTO_OK` | delta 不携带、不暗含播放权限 |
| 22 | `VOICE-C5-D6-VOICE-EVENT-BACKEND` | 后端发送显式 `voice_delivery` 事件 | `AUTO_OK` | 仅传稳定 intent 与语音候选/许可数据 |
| 23 | `VOICE-C5-D7-REMOVE-DELTA-TTS` | 删除前端 `delta → enqueueSpeech` | `AUTO_OK` | 流式文本继续显示但不直接发声 |
| 24 | `VOICE-C5-D8-REMOVE-TASK-QUEUED-TTS` | 删除前端 `task_queued → enqueueSpeech` | `AUTO_OK` | 排队结果不绕过统一门控 |
| 25 | `VOICE-C5-D9-FRONTEND-PLAYBACK-EVENT` | 前端只消费获准播放事件 | `AUTO_OK` | 未获 READY/PREEMPT 的项不能调用 TTS |
| 26 | `VOICE-C5-D10-VOICE-CANDIDATE-INTEGRATION` | `/record` 与 chat tool 已有语音候选经过同一 PlaybackScheduler | `AUTO_OK` | 只证明已有候选共用播放执行入口；不代表普通 chat 或前端回合已统一 |
| 27 | `VOICE-C5-E1-AUTO-ACCEPTANCE` | C5 全量自动回归与职责冻结 | `AUTO_OK` | 内容、资格、状态、时机、调度、执行边界齐全 |
| 28 | `VOICE-C5-E2-FREE-FOLLOWUP-PRESERVATION` | 恢复自由实验统一语义追问并保持保存后呈现 | `AUTO_OK` | 语义追问不被空方案评估覆盖；保存成功后才生成 clarification；新增红灯测试转绿 |
| 29 | `VOICE-C5-E3-RECORD-STREAMING-FEEDBACK` | `/record` 流式首反馈与提交后最终结果 | `AUTO_OK` | status 必须先到；保存成功后才有 result；保存失败无结果/回执/播放 |
| 30 | `VOICE-C4-1-SILERO-CONTRACT` | 定义通话模式 Silero VAD 适配合同 | `AUTO_OK` | 与音频帧及 Coordinator 事件兼容 |
| 31 | `VOICE-C4-2-SILERO-INTEGRATION` | 通话模式由 RMS 判断切换到 Silero | `AUTO_OK` | 噪音与人声固定样例自动验证 |
| 32 | `VOICE-C4-3-VAD-REGRESSION` | VAD 边界、失败回退和前端回归 | `AUTO_OK` | 短暂停顿/继续/断句边界稳定 |
| 32a | `VOICE-C4-3A-SPEECH-STARTED-BRIDGE` | 讲话开始事件进入按会话隔离的服务端状态 | `AUTO_OK` | 现有会话才可写；A/B 状态不串；重试幂等 |
| 32b | `VOICE-C4-3B-SPEECH-PAUSED-BRIDGE` | 短暂停顿事件进入同一会话状态 | `AUTO_OK` | 只改 `user_speaking`，不把停顿误当断句 |
| 32c | `VOICE-C4-3C-SPEECH-RESUMED-BRIDGE` | 停顿后继续讲话进入同一会话状态 | `AUTO_OK` | 恢复 `user_speaking`，保留同一采集片段 |
| 32d | `VOICE-C4-3D-SEGMENT-FINALIZED-ASR-BRIDGE` | 断句与 ASR 处理事件进入同一会话 | `AUTO_OK` | 断句后关闭采集；ASR 成功/失败都清理忙状态 |
| 32e | `VOICE-C4-3E-SESSION-PLAYBACK-STATE` | PlaybackScheduler 读取同一 conversation 的语音状态 | `AUTO_OK` | A 讲话只延后 A；B 不受影响 |
| 32f | `VOICE-C4-3F-TTS-FEEDBACK-REEVALUATION` | 浏览器 TTS 事实反馈与延后项重评 | `AUTO_OK` | STARTED/FINISHED/STOPPED/FAILED 闭环；延后项可恢复或过期丢弃 |
| 33 | `VOICE-C6-UNIFIED-CONVERSATION-SURFACE` | 单聊天时间线、显式模式、分策略输出与真实播放收口 | `IN_PROGRESS` | Chat、自由实验、单录和结束连续通话已有真实证据；方案实验仍失败，整体尚未收口 |
| 33a | `VOICE-C6-A1-TURN-BLOCK-CONTRACT` | 定义统一 Turn/Block 输出合同 | `AUTO_OK` | request/turn/block/voice 身份、mode_version 与纯幂等冲突判断；无副作用；专项 14/14、全量 1076/1076 |
| 33b | `VOICE-C6-A2-SINGLE-CONVERSATION-STORE` | 前端建立唯一 ConversationTurnStore | `AUTO_OK` | 正文/think/tool 只写 Store；删除 run 双状态；稳定 tool_call_id；专项 27/27、全量 1083/1083 |
| 33c | `VOICE-C6-A3-CHAT-FIRST-SURFACE` | 方案、步骤、安全、记录和 tool 收敛为聊天消息块 | `AUTO_OK` | 统一卡片骨架+BlockView；管理页保留，run 画布退役；专项 30/30、全量 1091/1091 |
| 33d | `VOICE-C6-A4-EXPLICIT-MODE-SWITCH` | 显式切换自由聊天、自由实验记录、方案实验记录 | `AUTO_OK` | 唯一模式状态；提交快照；输入来源解耦；专项 22/22、全量 1098/1098，未做真实浏览器 |
| 33e | `VOICE-C6-A5-MODE-OUTPUT-POLICIES` | 分离 chat、实验记录和 tool 输出策略 | `AUTO_OK` | Chat 禁止记录；free/protocol 显式保存策略；专项 46/46、全量 1105/1105 |
| 33f | `VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX` | chat、记录、tool 接同一输出外壳并完成交叉自动回归 | `AUTO_OK` | source_block_id 贯通；三生产者调度矩阵；专项 54/54、全量 1110/1110 |
| 33g | `VOICE-C3-1-PLAYBACK-TIMING-REAL` | 三种模式真机验证不抢话、延后恢复和过期不补播 | `TODO` | 普通 chat、自由/方案记录、tool 分别留外放/耳机证据 |
| 33h | `VOICE-C6-A7-REMOVE-TASK-RESULT-TTS-BYPASS` | 删除后台任务结果对播放器的直接调用 | `TODO` | 2026-08-25 计时样本出现 null intent；先仅显示，需播报时必须走正式 voice_delivery |
| 34 | `VOICE-C3-2-BARGE-IN-REAL` | 真机验证自激、漏检和打断停止 | `TODO` | C1/C2a/C4/C5 联合 REAL_OK 证据 |
| 35a | `VOICE-D0-INPUT-EVIDENCE-CONTRACT` | 定义文字/单次录音/连续通话进入实验统一链的来源可信输入合同 | `AUTO_OK` | 文字不得伪装 ASR；语音必须携带匹配的最终 ASRResult；专项 9/9、相邻 35/35、全量 1162/1162 |
| 35 | `VOICE-D1-SESSION-OWNERSHIP` | 服务端按对话与实验会话托管有状态会话 | `AUTO_OK` | 并发对话不共享 reply/voice 状态 |
| 36 | `VOICE-D2-REAL-OBSERVER` | 会话边界内接 UnifiedObserver（受控验证） | `AUTO_OK` | 语音映射/文字拒绝/0次LLM/1次LLM/降级ASR不丢；专项 6/6、全量 1186；接路由时定 `_submissions` 去重窗口期 |
| 37 | `VOICE-D3-DROP-IN-SWAP` | 降级生产者切换为真实观察器并完成方案实验闭环 | **NEXT** | 当前唯一下一能力：free/protocol 状态隔离、方案评价、最终 Blocks、SQLite 与真实验收 |
| 38 | `VOICE-D4-FIVE-BRANCH-CONTRACT` | 设计 `experiment/control/tool/chat/uncertain` 五分支 | `TODO` | 五分支互斥；理解层不执行工具 |
| 39 | `VOICE-D5-TOOL-PERMISSION-ROUTING` | 工具参数校验、风险权限和安全分派 | `TODO` | 不确定输入不产生工具副作用 |
| 40 | `VOICE-E1-FUNCTIONAL-REAL` | 真实录音到记录、追问、确认的功能验收 | `TODO` | 自由/方案模式分别留 session、终端和持久化证据 |
| 41 | `VOICE-E2E3-UX-AND-CLOSEOUT` | 九维体验验收与明确不做清单收尾 | `TODO` | UX 由用户裁决，三份维护文档同步 |

依赖关系调整为：`1–16 播放许可与执行架构 → 17–27 已有语音候选融合 → 28 自由实验追问回归修复 → 29 流式首反馈 → 30–32f VAD 与会话播放状态 → 33a–33f 单聊天时间线/显式模式/分策略输出 → 35a–37 原始三分支统一链接入 → 33g–34 在最终实验链上做真机播放/打断 → 38–39 另行设计五分支与工具权限 → 40–41 收尾`。2026-08-26 用户将统一链接入与识别能力检验提到当前主线；33g–34 保留 `TODO`，不是取消。

### 3.1A 近期任务登记（兼含关联完成项）

> 本表保留跨模块任务与历史关联，行号不代表当前执行顺序。
> PRESENT 期间的范围与任务状态见下方“15 项收口清单”；剩余施工顺序以其上方
> “当前剩余唯一施工顺序（用户 2026-08-16 确认）”为准。

| 顺序 | 优先级 | 任务 | 当前状态 | 本轮要得到的结果 | 进入下一项的条件 |
|---:|---|---|---|---|---|
| 1 | `P0` | `INTENT-02-CLEANUP-VERIFY-01` 清理后真实验收 | `TODO` | 五类口述连续会话验收 | 全量测试通过且真实功能不减 |
| 2 | `P1` | Query/Safety/Knowledge 三组合同与 Fake | `TODO` | 独立类型和协议，不接 main | **清理后第一批** |
| 3 | `P1` | QUERY 第四分支与只读分派 | `TODO` | unified 识别 QUERY，路由到知识查询边界 | 不接真实设备服务或 RAG |
| 4 | `P2` | 安全、RAG、查询真实接入与 E2E | `TODO` | 见第 I.2 节 | PRESENT 与团队服务合同稳定后 |
| 5 | `P1` | `ASR-ROBUSTNESS-RULE-GAPS-01` 鲁棒性旁路缺口修复 | `TODO` | 真实旁路报告 7 个缺口逐项定案：规则/提示词/确定性兜底 | 来源：`INTENT-02-ASR-ROBUSTNESS-01` 真实旁路（deepseek-v4-flash，21/28 一致）。7 缺口 + **用户 2026-08-14 逐项决策**：①段3"加热到60摄氏度"当新实验事件 → **接受当实验**，另加"回答问题请指定编号"显示提示；②段7/14 同音错词确认不稳定 → **先走 ASR 层修复**（热词/后处理），提示词暂不动，演示场景未定故不深做；③段17 "PH"（实为 ASR 听成"PHG"）过度确认 → **再测**，暂不修；④段18"不对，应该是7.4"被 LLM 判为 targeted_answer（精确解析为 deny）→ **否定修正不做**，当实验记录展示；⑤段20"再加50毫升"、段25"电流显示80毫安"过度判为回答 → **提示词已收紧**，**再测**（重跑旁路报告确认现状）；⑥⑦ 不存在（报告恰 7 段不一致，归为 ①-⑤ 五类） |
| 6 | `P1` | `ASR-ROBUSTNESS-RULE-GAPS-02` 鲁棒性复验补充观察（112047/112445，用户已逐项决策） | `TODO` | 5 项补充观察按决策执行 | 用户 2026-08-14 决策：**A**（"问题一先跳过"→answer 漏 DEFER）→ **修**；**B**（"暂缓问题一"→abstention 漏 DEFER）→ **修**（与 A 同根因：意图 schema 无"按编号暂缓"，需新增 defer_targeted 或等效处理）；**C**（"不对，应该是7.4"→no_action）→ **纠正记录**：不是 deny 大模型问题，定性为"修正历史记录"类需求，先不做、当实验记录展示；**D**（自然结束语→观察失败 ValueError）→ **方案二：固定结束语**（LLM 识别结束意图时提示"请说'结束实验记录'"，只有精确命令结束；方案一"确认后关闭"留待有时间再做）；**E**（"仍需补充：空"）→ **已修**（显示一致性轮），**再测**并入下次真实会话；**F**（"再加50毫升"→abstention）→ **先不管**。另：段9"一夜枪"未触发确认（缺口②不稳定复现）随②走 ASR 层 |
| 7 | `P1` | `GAPS-FIX-END-01` 结束语非精准命中 → 追问 → 肯定后结束（用户 2026-08-14 晚改方案一） | **REAL_OK** | 旁路对 `end_session_confirmation` 产出"请求结束确认"信号（不再抛 ValueError）→ 观察器/工人传递 `end_confirmation_requested` → 后台显示"是否结束？"+ 置会话级标志 → 主循环下一段 affirm 命中即结束 | 会话 20260815_111049：段6"今天先记录到这里吧"→"是否结束？"→段7"是的是"→"确认结束"正常收尾，不再崩 ValueError |
| 8 | `P1` | `GAPS-FIX-DEFER-01` DEFER 可逆候选接上下文校验 + 按编号暂缓真实验收（用户 2026-08-14 晚） | **REAL_OK** | ①`intent_policy.py` reversible 的 `LLM_CANDIDATE` 也走 `REQUIRE_CONTEXT`；②根因修复：`register_clarification` 创建即"当前问题"；③`defer_targeted` 按编号暂缓（新增 `DEFER_TARGETED` 命令类型 + 解析模式"问题N先跳过/第N个问题先跳过" + 规划器 `find_by_number`） | 会话 112341：暂缓生效；defer_targeted 单测（解析器+旁路）覆盖 |
| 9 | `P1` | `GAPS-FIX-ANSWER-HINT-01` ① 回答需指定编号提示 | `TODO` | 存在待确认问题时，被当实验处理的短句旁提示"回答请指定问题编号（如'问题一，…'）" | 用户决策（2026-08-14）：① 接受当实验（LLM 自由判断），但加显示提示引导用户回答时带编号；纯显示层小改动 |
| 10 | `P1` | `GAPS-REVERIFY-01` ③⑤E 复验 + ②现状复查 | **REAL_OK** | 真实旁路 21/31 一致：③ PH 大小写（段17）不再过度确认、⑤ 电流80毫安（段25）正确判实验、D 自然结束语（段28）正确识别 end_session；真实会话 115134：E"仍需补充：duration"、③"PH值是7.2"无过度确认、D 完整"追问→是→结束"全部闭环 | ② 同音错词仍不稳定（段7/14/29），按用户决策走 ASR 层，不在此轮 |
| 11 | `P0` | `UX-BASELINE-01` 体验基线走查（用户 2026-08-14 提出"终端看不出体验"后建立） | **完成（UX_ISSUES）** | 九维体验走查表已建（`docs/UX_WALKTHROUGH_CHECKLIST.md`）；会话 `20260814_174441` 基线走查完成，10 项问题登记 UX-01~10（8 项走查发现 + 提示音/嘈杂识别为用户补充），5 项正向确认；原始输出 `results/walkthrough_baseline_session_20260814_174441.txt`，逐行标注版 `results/walkthrough_baseline_annotated_20260814_174441.md` | 10 项 UX 问题留待输出层/ASR 任务自然闭环（用户 2026-08-14：暂不与 PRESENT 强制绑定）；每闭环一项可复走九维表对比 |
| 12 | `P1` | `UX-FIX-TONE-01` 事件提示音（UX-09，用户 2026-08-14 提出） | `TODO` | 需要用户注意的事件（追问/确认回执/降级/识别失败/结束语未识别）播放提示音，用户听到声音再看屏幕；复用 `play_wake_tone` 设施（`src/audio/feedback.py` 扩展事件音）+ 消息链路触发点；提示音≠TTS 朗读 | **用户决策（2026-08-14 更新）：顺延到 PRESENT-INTEGRATE-01 之后做**——触发点直接挂在 PRESENT 建好的消息链路上，输出层只动一次避免返工；完成后按九维表走查（重点验维6 ✗→✓） |
| 13 | `P1` | `ASR-NOISE-SAMPLES-01` 嘈杂识别样例入语料（UX-10，用户 2026-08-14 提出） | **完成** | 20260814_174441 三个真实噪声样例已入 `evaluation/narration_robustness/narration_plan.json` 段 29/30/31（'防生缓冲液'/'제가.'/'.别束实验记录.'），schema 21 项 + 全量 468 项通过；修复走既有 ASR 线（AUDIO-PREROLL 截音/热词/后处理） | 样例已可被 `evaluate_narration_robustness.py` 评测；修复时机由 ASR 任务线决定 |
| 14 | `P1` | `UX-MODE-01` 终端输出分层：用户版/管理员版（UX-11，用户 2026-08-14 提出） | `TODO` | 用户模式屏幕只显示 SCREEN 层（对话/回执/状态/待确认/指引），DEBUG 层单独保留（写 `results/debug_<session>.log`，信息不丢）；管理员模式屏幕显示全部；main.py 42 处 print 归类分层 + 统一出口；`UI_MODE=user|admin` 配置开关 | **与 PRESENT-INTEGRATE-01 同源**（消息链路），随 PRESENT 落地（硬问题修完即进，不设固定日期），不单独提前实现；完成后按九维表走查（重点维1/7 ✗→✓） |
| 15 | `P0` | `RESTORE-NONBLOCK-01` 恢复非阻塞录音（评委 2026-08-14 发现：main.py 已无后台线程） | **REAL_OK** | 新建 `OrderedTaskQueue`（通用单线程队列+背压4）+ `UnifiedSegmentProcessor`（六步业务流水线）；main 主循环改为"录音→提交后台→显示"，入口文件不再堆业务规则；拆两句谎话（111行"旧流程继续"→"ASR 原文已保存"；320行"无需等待"现为真）。全量 483 项通过（+15）；集成测试证明"录音期间 LLM 在后台跑"；真实会话 20260815_094954 连说 10 段不卡、计数正确（共10段/提交8段/上下文8=事件数） | 已恢复。体验裁决=用户接受当前"结果延后显示"节奏；前瞻要求 TTS 不乱序朗读（登记 TIMING-02） |
| 16 | `P1` | `RESTORE-DEGRADED-HINT-01` 恢复降级人话提示（评委 2026-08-14 发现） | **REAL_OK** | `display_observation` 在 `acceptance_kind=="degraded_evidence_note"` 时打印"原始记录已保存，结构化处理暂时不可用"（话术取自 `OUTPUT_PRESENTATION_POLICY.md` 第224行） | 冒烟测试确认输出含人话 |
| 17 | `P1` | `SYNC-UI-CLAIMS-01` 用户文案与实际行为一致性核查（评委 2026-08-14 发现） | **硬谎话 2 处已拆（随 RESTORE-NONBLOCK-01）** | ①main.py:320"无需等待"→非阻塞后为真；②main.py:111"旧流程继续"→"ASR 原文已保存"。**误导 2 处**仍待 PRESENT 文案统一改：③"立即继续监听"（非阻塞后为真）；④"提交 M 段实验口述"（内部术语）。DEBUG 泄漏仍登记 UX-01/UX-11 | 误导 2 处随 PRESENT 文案统一改 |
| 18 | `P1` | `ANSWER-FALLBACK-ADJACENCY-01` 无编号兜底加"紧邻"约束（用户 2026-08-14 晚指出） | **AUTO_OK** | `decide_unnumbered_answer` 加第 5 条规则：问题来源段+1==当前段才允许自动接；新增 `current_segment_id` 参数 + 测试（隔段不承认） | 单测覆盖边界路径，无需专门真实复验 |
| 19 | `P1` | `PRESENT-FIX-LEAK-01` 开发输出泄漏收尾（B-4 真实验收发现） | `REAL_OK` | 141745发现完整第三方噪声；142352清到仅剩版本行；定位并精确禁用FunASR 1.4.1版本检查入口。会话142945确认启动/整轮零FunASR/ModelScope/路径/进度/RTF/耗时/token泄漏，READY含Ctrl+C、WAITING含再次唤醒指引 | 专项63/63、全量576/576通过；第二次实际唤醒留到最终双会话UX验收，不阻塞泄漏任务 |
| 20 | `P1` | `PRESENT-NOACTION-FEEDBACK-01` 投影层 no_action 容错反馈（B-4 真实验收发现） | `AUTO_OK` | 新增 `NO_ACTION_FEEDBACK` 语义意图，控制类 no_action 不再沉默；文案按 reason 映射为“没有找到编号/请说明回答内容/当前没有可操作问题/没把握安全执行”等。执行器 NO_ACTION 透传 planner reason。新增 9 项测试；全量 724 项通过 | 待真实会话验证“制业枪”等 no_action 场景有可见回应；通过后升 REAL_OK |
| 33 | `P0` | `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01` 同句确认+实体回答不能丢字段 | `AUTO_OK` | CONFIRM 执行器支持 supplied_entity_fields 或实体提取器，确认与填字段原子完成；PRESENT 确认回执携带 remaining_fields/resolved 并如实显示。新增 7 项测试：完全解决、仍缺字段、纯确认、提取器填充；全量 715 项通过 | 待真实会话验证“是的，体积为50毫升”确认记录不再残留 amount_value/amount_unit；通过后升 REAL_OK |
| 21 | `P1` | `LLM-FOLLOWUP-STRICT-01` 缺字段追问复核（B-4 二次真实验收修正） | `MERGED` | 历史样本曾被当成提示词严格度争议；2026-08-24 重新审计确认更直接的集成缺陷：统一理解已有追问字段，但 Web 桥和共享记录服务未完整保留，自由模式空方案评估会覆盖语义追问 | 已正式吸收到唯一施工清单第 28 项 `VOICE-C5-E2-FREE-FOLLOWUP-PRESERVATION`，不再作为无人负责的旁支 TODO |
| 22 | `P0` | `ASR-DEMO-NOISE-01` 路演前 ASR 噪音/误识别必修（用户 2026-08-16 明确"路演必须解决"） | `TODO` | 两次真实验收暴露的误识别：①"加热到60摄氏度"→"加热到60摄氏度APP"（尾音）；②"结束实验记录"→"要车翻圈啦"（language=auto 误判粤语 yue）；③"将溶液加热"→"标溶液加热"（首字误听）；④"是的"→"日的"（确认词首字误听，导致确定性 AFFIRM 前缀没命中、掉给 LLM 弃权，2026-08-20 P0 真实验收发现）。**解决方向**：a) language 参数 auto→固定 zh（治粤语误判）；b) 热词/后处理（`ASR-CMD-02-POSTPROCESS-01` 已 REAL_OK，等组长定演示领域后接入）；c) 截音（AUDIO-PREROLL 尾音截断）；d) 噪声样例入语料（`ASR-NOISE-SAMPLES-01`） | **路演环境下核心口述/结束命令识别稳定、不乱识别**（路演硬门槛，不达不演） |
| 23 | `P2` | LLM 返回格式错误导致降级（B-4 二次真实验收发现） | `TODO` | 段1"标溶液加热" llm_error="顶层字段不匹配；缺少=[control,experiment,uncertain]，额外=[reason]"——LLM 对误识别文本返回了 uncertain 分支格式但缺顶层字段，触发降级（数据未丢，原始记录已保存，优雅降级生效） | 观察 LLM 返回格式稳定性；必要时加格式修复/重试 |
| 24 | `P1` | `PRESENT-ADMISSION-01` 用户呈现准入与去重复 | `AUTO_OK` | 四刀完成：会话提示去重复、基础设施转 logging、`IdleNoticeTracker`、`END_ONLY` 单一结束摘要。结束摘要合并实验步骤数与待确认明细，零待确认也明确显示。专项41/41、全量571/571通过 | 自动闭环；真实会话九维走查统一并入 `PRESENT-FINAL-UX-VERIFY-01` |
| 25 | `P1` | `PRESENT-FEEDBACK-REGRESSION-01` 程序级与零待确认反馈补回 | `AUTO_OK` | 新增结构化 `PROGRAM_STATUS`（starting/ready/exited）和 keyword 合同化 `WAKE_ACK`；程序级 Coordinator/Pump 在初始化前启动，会话复用同一链路；启动期间和待机期间 Ctrl+C 都交付退出反馈；零待确认已由 END_ONLY 明确显示；程序状态与唤醒事实均经 projection→Intent。专项56/56、全量578/578通过 | 自动闭环；真实 user 模式可见性与去重复并入 `PRESENT-FINAL-UX-VERIFY-01` |
| 26 | `P1` | `PRESENT-PUMP-FLUSH-01` pump 完成交付合同 | `AUTO_OK` | Coordinator 用原子 unfinished 计数覆盖 pending/deferred/in-flight；Pump 在 output 返回后 `mark_completed()`；`flush(timeout)` 区分超时与结构化交付失败，失败后继续交付后续消息 | 慢 output、失败隔离、去重/deferred 计数测试通过；专项24/24、全量584/584通过；真实尾消息复验并入最终 UX 验收 |
| 27 | `P1` | `PRESENT-EXTENSION-SEAMS-01` QUERY/DENY/WARNING/导出呈现接缝 | `TODO` | 禁止未来功能不断在 `main.py` 手写 if/elif 投影；各自结构化结果经 projection→Intent；定义 WARNING 是否及如何抢占普通 FIFO；导出只读 SessionRecord，PRESENT 只消费开始/成功/失败结果 | Fake 合同覆盖四类来源；WARNING 调度规则明确且不破坏普通 FIFO；不解析 PRESENT 文案做导出 |
| 28 | `P1` | `PRESENT-LEGACY-MESSAGE-CLEANUP-01` 删除旧 PresentationMessage 双轨 | `AUTO_OK` | 三个现役语义枚举归位到 `presentation_intent.py`；删除旧模块、旧对象、channel/status/speech policy 与专属 10 项测试，不留兼容别名 | `src/tests` 旧引用为0；专项86/86、删除后全量574/574通过；TTS/Web 交付模型留待第二真实渠道 |
| 29 | `P1` | `PRESENT-FINAL-UX-VERIFY-01` PRESENT 最终真实验收 | `TODO` | user/admin 对照真实会话：反馈完整、无重复/泄漏、顺序正确、最后消息不丢，维1/7改善且维2/5/9不退化 | 下面“PRESENT 当前15项收口清单”核心项实现完成；记录 session_id、终端证据和九维结论 |
| 30 | `P1` | `PRESENT-CLOSING-NAME-01` 收尾回执与正式 SessionSummary 消歧 | `AUTO_OK` | `MessageKind.SESSION_SUMMARY` 已改为 `SESSION_CLOSING_SUMMARY`，同步枚举值、copy 函数、main、测试与当前文档；`src/tests` 旧 PRESENT 名零残留，无兼容双名，无 SessionRecord/LLM 总结/导出扩张；专项41/41、全量571/571通过 | 自动闭环；真实输出随最终 PRESENT UX 会话统一复验 |
| 31 | `P1` | `PRESENT-RECORD-PREVIEW-01` 规范记录预览替代 user 原始 ASR | `TODO` | 将已存在的 `accepted_analysis.events[].normalized_text` 以严格 `event_previews` 合同透传到 `RECORD_ACK`，user 显示“已记录实验步骤N：……”；原始 ASR 不再逐段占据 user 主界面，但继续落盘并在 admin/debug 或按需详情可查；不启用自由 `assistant_reply`、不新增 LLM 调用 | 分三步：A 先显示 ASR+规范预览做对照；B 验证稳定后移除 user TRANSCRIPT Intent；C 真实语音核对 ASR JSONL/Event JSONL/user/admin/追问/降级。单事件、多事件、标点、空预览、降级和非阻塞测试齐全 |
| 32 | `P1` | `PRESENT-DELIVERY-BOUNDARY-01` Coordinator/Renderer/Pump 架构合同与渐进扩展纪律 | `TODO` | 固定唯一链路与职责边界：结构化结果→projection→`PresentationIntent`→Coordinator（排序/去重/生命周期）→Pump（执行交付并回执）→Renderer（纯格式化）→Sink（唯一 I/O）；普通新消息不得要求修改 Coordinator/Pump，用户可见输出不得绕过链路。消息内容随业务增量扩展；WARNING 在真实接入前补最小调度子步；TTS/Web 等第二真实渠道接入前才专门提取有限 Delivery/Renderer 抽象，不因未来可能性提前建设框架 | 文档职责/变化归属明确；架构护栏覆盖直接 print 泄漏、FIFO、in-flight flush、Renderer 无 I/O；阶段收口检查确认无跨层业务分支和重复交付实现 |

#### PRESENT 当前 15 项收口清单（用户 2026-08-16 确认）

> 本表是 PRESENT 当前范围的统一入口；复用已有任务 ID，不重复造任务。序号表示清单项，
> 不覆盖全项目原有优先级。第 1–10、13–15 项属于核心收口，第 11–12 项是直接挂接 PRESENT 的体验增强。

**已完成的 PRESENT 基础项：**

```text
1 END_ONLY → 2 必要反馈 → 3 pump flush → 4 旧消息清理 → 13 收尾命名 → 5 泄漏
```

**当前剩余唯一施工顺序（用户 2026-08-16 确认）：**

| 新顺序 | 任务 | 当前状态 |
|---:|---|---|
| 1 | `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01` P0 复合确认+回答不能丢字段 | `AUTO_OK` |
| 2 | `PRESENT-NOACTION-FEEDBACK-01` NOACTION 容错反馈 | `AUTO_OK` |
| 3 | `UX-MODE-01` user/admin 输出分层 | `部分完成，任务状态待校准` |
| 4 | `SYNC-UI-CLAIMS-01` 文案与真实状态一致性 | `部分完成` |
| 5 | `PRESENT-RECORD-PREVIEW-01` 规范记录预览 | `TODO` |
| 6 | `PRESENT-DELIVERY-BOUNDARY-01` Delivery Boundary 架构护栏 | `TODO` |
| 7 | `PRESENT-EXTENSION-SEAMS-01` QUERY/DENY/WARNING/导出扩展接缝 | `TODO` |
| 8 | `GAPS-FIX-ANSWER-HINT-01` 回答编号提示 | `TODO` |
| 9 | `UX-FIX-TONE-01` 事件提示音 | `TODO` |
| 10 | `PRESENT-FINAL-UX-VERIFY-01` 最终双模式真实 UX 验收 | `TODO` |

> 上表取代此前按阶段排列的剩余施工顺序。未经用户重新确认不得跳项；若确需调整，必须先同步
> 本清单与交接文档。下面 15 项表继续承担范围、历史编号、状态与验收定义，不再作为剩余顺序依据。

| 序号 | 任务 | 当前状态 | 剩余结果 |
|---:|---|---|---|
| 1 | `PRESENT-ADMISSION-01` 呈现准入与去重复 | `AUTO_OK` | 四刀已完成，专项 41/41、全量 571/571 通过；真实走查留到第 10 项 |
| 2 | `PRESENT-FEEDBACK-REGRESSION-01` 必要反馈补回 | `AUTO_OK` | 启动/就绪/唤醒/退出已走 projection→Intent→程序级共享 pump，零待确认已明确显示；专项 56/56、全量 578/578 通过 |
| 3 | `PRESENT-PUMP-FLUSH-01` pump 完成交付合同 | `AUTO_OK` | unfinished 计数覆盖 pending/deferred/in-flight；flush 显式区分超时与交付失败；专项 24/24、全量 584/584 通过 |
| 4 | `PRESENT-LEGACY-MESSAGE-CLEANUP-01` 删除旧消息双轨 | `AUTO_OK` | 旧模块、旧对象、专属 channel/status/speech policy 和 10 项旧测试已删除；现役枚举归位 Intent；专项86/86、全量574/574通过 |
| 5 | `PRESENT-FIX-LEAK-01` 开发输出泄漏收尾 | `REAL_OK` | 会话142945确认全程零泄漏；双会话143151→143201进一步确认同进程再次唤醒、两个新会话编号、WAITING/EXITED与程序级Pump生命周期均正确；专项63/63、全量576/576通过 |
| 6 | `PRESENT-NOACTION-FEEDBACK-01` no_action 容错反馈 | `AUTO_OK` | 控制类 no_action 统一投递 NO_ACTION_FEEDBACK，用户不再看到沉默；真实 UX 随最终验收 |
| 7 | `PRESENT-EXTENSION-SEAMS-01` 扩展接缝 | `TODO` | QUERY/DENY/WARNING/导出结果统一 projection→Intent；定义 WARNING 抢占规则 |
| 8 | `UX-MODE-01` user/admin 输出分层 | `部分完成，任务状态待校准` | 程序级反馈分层、按会话日志、user/admin 真实对照验收 |
| 9 | `SYNC-UI-CLAIMS-01` 文案与行为一致 | `部分完成` | 删除“提交 M 段”等内部术语，统一核查用户承诺与真实行为 |
| 10 | `PRESENT-FINAL-UX-VERIFY-01` 最终真实验收 | `TODO` | 验证反馈完整、无重复/泄漏、顺序正确、尾消息不丢及九维不退化 |
| 11 | `GAPS-FIX-ANSWER-HINT-01` 回答编号提示 | `TODO` | 存在待确认项时，引导用户用“问题一，……”明确回答目标 |
| 12 | `UX-FIX-TONE-01` 事件提示音 | `TODO` | 追问/回执/降级/失败等需注意事件播放提示音；提示音不等于 TTS |
| 13 | `PRESENT-CLOSING-NAME-01` 收尾回执命名消歧 | `AUTO_OK` | 已统一为 `SESSION_CLOSING_SUMMARY`，无兼容双名和旧 PRESENT 引用；专项 41/41、全量 571/571 通过 |
| 14 | `PRESENT-RECORD-PREVIEW-01` 规范记录预览 | `TODO` | user 用 `normalized_text` 核对系统最终采纳事实，原始 ASR 继续保存并转 admin/debug/按需详情；禁止自由 assistant_reply 和额外 LLM 调用 |
| 15 | `PRESENT-DELIVERY-BOUNDARY-01` 交付链路架构合同 | `TODO` | 固定 Coordinator/Renderer/Pump/Sink 职责、生命周期和变化归属；QUERY/DENY 等随业务扩，WARNING 按真实调度需求扩，TTS/Web 在第二真实渠道接入前做有限架构子步；禁止过早通用化，也禁止绕过统一链路 |

### 3.1B 已完成看板（近期已闭环，证据详见维护日志）

| 顺序 | 优先级 | 任务 | 当前状态 | 本轮要得到的结果 | 进入下一项的条件 |
|---:|---|---|---|---|---|
| 1 | `P0` | `INTENT-02-UNIFIED-DISPATCH-01` 统一路由结果分派合同 | `AUTO_OK` | 六类无副作用目标与最小权限合同完成 | 10项专项、4项Router→Planner集成及全量332项通过；未接main、存储、协调器或状态机 |
| 2 | `P0` | `INTENT-02-UNIFIED-DISPATCH-INTEGRATION-01` 固定文本旁路分派集成 | `AUTO_OK` | 模拟ASR证据→真实Router→真实Planner→只读报告形成旁路 | 6项专项、五类脚本烟雾及全量338项通过；无执行依赖、无文件写入 |
| 3 | `P0` | `INTENT-02-UNIFIED-DISPATCH-WAV-01` 固定WAV真实旁路验收 | `REAL_OK` | 固定WAV→真实ASR→统一路由→安全分派，只输出观察报告 | 18.072秒固定WAV真实识别1.593秒；DeepSeek首次请求成功1.961秒；普通实验只得到experiment_pipeline＋forward_experiment_analysis；全量340项通过，未写业务文件或连接执行模块 |
| 4 | `P0` | `INTENT-02-DISPATCH-EXECUTION-CONTRACT-01` 分派执行请求/结果合同 | `AUTO_OK` | 将最小权限计划转换为可审计、可拒绝、可防重复的执行请求；仍不实现真实副作用 | 新增10项合同/Fake测试；相关24项、全量350项通过；未接main、存储、状态机或TTS |
| 5 | `P0` | `INTENT-02-EXPERIMENT-ACCEPTANCE-CONTRACT-01` 实验结果采用合同 | `AUTO_OK` | 验证统一理解的实验候选后形成不可变规范快照，禁止旧SegmentProcessor再次调用LLM | 新增10项采用测试；相关37项、全量360项通过；未写存储或上下文 |
| 6 | `P0` | `INTENT-02-CLARIFICATION-ACCEPTANCE-01` 待确认动作采用合同 | `AUTO_OK` | 把创建、回答、确认、暂缓、回看和弃权变成目标明确的无副作用动作计划 | 新增13项测试；相关43项、全量373项通过；没有commit方法，未修改ReplyCoordinator |
| 7 | `P0` | `INTENT-02-ACCEPTANCE-INTEGRATION-01` 固定文本采用链集成 | `AUTO_OK` | Router→Planner→ExecutionRequest→实验/待确认采用器组成一条无副作用链 | 新增9项接线测试；相关59项、全量382项通过；固定文本覆盖实验、创建追问、查看、暂缓、指定回答、LLM中风险弃权和降级；不接main或存储 |
| 8 | `P0` | `INTENT-02-MAIN-SHADOW-INTEGRATION-01` main影子观察接入 | `REAL_OK` | 新采用链读取main产生的同一份最终ASR证据并输出可比较观察结果 | 自动全量385项；真实会话`20260810_120209`观察4段，3段成功、结束候选1段安全失败且旧流程继续；未写影子业务数据、未改状态、未发TTS。首次怀疑追问合同缺失，后续测试证明合同原有双检验，真实差异最终定位为统一Prompt能力规则遗漏；main命令标准化漂移已修复并REAL_OK |
| 9 | `P0` | `INTENT-02-FOLLOWUP-INVARIANT-01` 追问跨字段一致性合同 | `AUTO_OK` | `missing_fields`非空或`needs_confirmation=true`时，不能接受`should_ask_follow_up=false`并产生NO_ACTION | 复核发现parse_analysis原本已强制该不变量，采用快照物化时也会再次严格解析；新增5项明确上下游反例测试并补影子missing_fields/follow_up_required摘要；相关25项、全量390项通过。真实会话no_action不能证明矛盾，因为当时未记录新链字段 |
| 10 | `P0` | `INTENT-02-END-NORMALIZATION-UNIFY-01` 结束命令标准化单一来源 | `REAL_OK` | main与InteractionCommandParser必须复用同一份SenseVoice情绪符号清理和命令集合 | 删除main独立字典/正则，新增情绪尾反例和一致性2项，全量392项；修改后短真实会话直接结束，ASR业务记录保持186、事件保持133，主程序停止且最后记录未变化，证明结束口述未进入分段、影子/旧LLM或存储 |
| 11 | `P0` | `INTENT-02-SHADOW-FOLLOWUP-OBSERVE-01` 追问字段真实影子复验 | `REAL_OK` | 使用新增脱敏摘要观察新统一链自己的missing_fields与follow_up_required | 会话`20260810_180242`确定差异来自统一Prompt缺少能力规则，不是合同矛盾 |
| 12 | `P0` | `INTENT-02-UNIFIED-PROMPT-MISSING-FIELDS-01` 统一Prompt缺失字段能力对齐 | `REAL_OK` | ~ | Prompt新增1行业务规则；真实DeepSeek复验missing_fields=['temperature','duration']；影子会话`20260811_103134`确认create+缺失字段输出正确 |
| 13 | `P1` | `INTENT-02-REPLY-GATE-01` ClarificationAction→ReplyCoordinator执行器 | `AUTO_OK` | ~ | 新增ClarificationExecutor+23项测试；ReplyCoordinator新增4个原子方法；影子会话`20260811_103134`验证新链输出create施工单但未执行；415项通过 |
| 14 | `P0` | `COMMAND-03` 自然控制表达兼容 | `AUTO_OK` | 将”我先跳过/可先跳过”等自然表达匹配到精确命令 | DEFER新增安全前缀+跳过后缀规则；REVIEW新增自然表达式模式；Prompt新增uncertain兜底规则；3项parser+1项prompt测试；418项全量通过；未做真实影子复验 |
| 15 | `P0` | `INTENT-02-REPLY-GATE-02` ANSWER施工单实体填充 | `AUTO_OK` | ~ | 新增AnswerEntityExtractor轻量LLM提取+answer_clarification方法；统一理解control分支可携带supplied_entities；Executor优先用施工单实体再fallback到extractor；422项通过 |
| 16 | `P0` | `INTENT-02-REPLY-GATE-03` 影子位接入ClarificationExecutor | `REAL_OK` | ~ | 真实会话`20260811_143031`：CREATE✅+ANSWER✅（轻量extractor提取实体→已执行）；4轮修复（重复ID/cls参数/缺extractor）；422项通过 |
| 17 | `P0` | `INTENT-02-UNIFIED-CUTOVER-01` 关旧ingest_analysis，新链路成为唯一来源 | `REAL_OK` | ~ | 会话`20260812_100807`：5段口述，CREATE✅ ANSWER✅ REVIEW✅，无重复追问，结束命令正常；422项通过 |
| 18 | `P0` | `INTENT-02-LLM-DEDUP-01` 关旧SegmentProcessor重复LLM调用 | `REAL_OK` | ~ | 会话`20260812_114401`：6段全部新路径直存零旧LLM；修NameError+非实验回退+answer竞态三个bug；422项通过 |
| 19 | `P0` | `ENV-RECOVERY-02` 验证正式 Python 3.11.9 环境 | `AUTO_OK` | 基础解释器和 `.venv` 均为3.11.9；核心依赖与 main 导入成功；422项通过 | 首次失败是沙箱执行权限误判；未重建环境 |
| 20 | `P0` | `MAIN-FLAG-INVARIANT-01` 配置组合不变量 | `AUTO_OK` | 禁止 execute=true/enabled=false；补配置测试和 `.env.example` | config 新增 `validate_shadow_flags` 纯函数并在加载时 fail-fast；新增 5 项测试；427 项通过；非法组合不再可能读取未赋值的 `observation` |
| 21 | `P0` | `MAIN-EVIDENCE-COMMIT-01` 澄清动作证据优先提交 | `REAL_OK` | 状态动作统一采用 prepare→persist→commit | observe 拆出 pending_action；main 编排 persist ASR/事件 → commit 状态；真实会话 20260813_104732：CREATE/ANSWER/REVIEW/结束正常，ASR 3 段 + 事件 1 段落盘，零重复 LLM；428 项通过 |
| 22 | `P0` | `MAIN-SESSION-CONTEXT-01` 恢复统一链路上下文 | `REAL_OK` | observe 接收提交前上下文；事件落盘成功后 add_analysis | main 的 observe 调用传入 `session_context.as_prompt_context()`；事件落盘成功后 `add_analysis(outcome.value)`（与旧 SegmentProcessor 第5步语义一致：上下文不含"内存有但文件无"的事件）；新增 shadow 上下文透传 2 项测试 + 提示词 recent_context 断言 1 项；全量 435 项通过。真实会话 `20260814_092200`：2 段口述（"加入5毫升缓冲液"→"加热到60摄氏度"），结束打印"最终上下文包含 2 条事件"= 已落盘事件数；第 2 段 prompt_tokens 959→971、cached 896 不变，直接证明前文进入提示词；结束命令未进入分段（3 个录音文件仅 2 条 ASR 记录）；新增 `scripts/verify_session_context.py`（含 5 项测试）按会话核验 ASR/事件/上下文计数 |
| 23 | `P1` | `MAIN-RUNTIME-HARDEN-01` 运行边界整理 | `REAL_OK` | 修正实验段计数、持续唤醒错误退避、删除重复空字段分支 | ① `ShadowObservation` 新增 `is_experiment_evidence` 属性，main 统一链只统计实验/降级证据段（查看/暂缓/弃权不占计数）；② 新建 `src/core/retry.py` 纯函数 `next_backoff_delay`（1→2→4→8→10s 封顶），main 唤醒循环失败退避、成功重置、Ctrl+C 不受影响；③ 删除 `ClarificationExecutor` 重复 `if not supplied_fields` 死分支；新增 retry 5 项 + evidence 3 项测试，全量 443 项通过。真实会话 `20260814_093515`：3 段口述（实验/查看/实验），结束打印"提交 2 段实验口述"，控制命令不占计数；事件记录仅段 1、3；上下文计数 2 = 事件数 |
| 24 | `P0` | `INTENT-02-CLEANUP-FLAGS-01` 去标志位 | `REAL_OK` | 删除两个 shadow flag，新链成为唯一默认路径 | 删除 `UNIFIED_SHADOW_ENABLED`/`UNIFIED_SHADOW_EXECUTE_ENABLED` 及 `validate_shadow_flags`（config.py 与 .env.example 同步清理）；main 的观察器/执行器无条件创建、删除旧 submit 分支与观察-only 提前显示、`skip_ingest` 恒 True；删除 test_config.py 5 项开关测试；代码零残留引用；全量 438 项通过。真实会话 `20260814_095506` 不退化复验通过：启动打印"统一理解链已启用（唯一默认路径）"；6 段口述"提交 2 段实验口述"，控制/弃权不占计数；ASR 误识别"看待确认问题"被统一链正确理解 review；"还有什么问题？"走精确快速路径零 LLM；上下文 2 = 事件数 |
| 25 | `P0` | `INTENT-02-CLEANUP-SUBMIT-01` 去旧 submit 分支 | `REAL_OK` | 删除旧 submit、skip_ingest 和旧显示补丁 | 旧 SegmentProcessor LLM 路径从 main 消失：删 `create_experiment_llm_processor`、`SegmentProcessor`/`SessionProcessingQueue`/`CompletedSegment` 使用与 import、四个旧显示函数、`_display` 及全部 `collect_ready/finish/pending_count` 调用、外层 try/finally 队列收尾；统一链事件落盘改用 `event_store`；删 `tests/test_reply_coordinator_integration.py`；main.py 净删 847 行；全量 433 项通过。真实会话 `20260814_102122` 复验通过：3 段口述"提交 2 段实验口述"、上下文 2 = 事件数、无事件保存失败、无"当前待处理任务数"。首轮复验（`20260814_101632/101744`）抓出重构 Bug：`event_store` 未作为参数传入 `run_experiment_session` 导致 NameError、事件全丢（上下文 0）；补传参修复后复验通过——真实验收成功拦截单测盲区 |
| 26 | `P0` | `INTENT-02-CLEANUP-COMMAND-01` 统一命令入口 | `REAL_OK` | 消除三道旧门卫和 `_new_chain_handled_answer` 补丁 | 主循环删除 targeted-answer/clarification/confirmation 三道门卫及补丁，统一链成为唯一命令路径；搬入新链三件职责：① review 显示（`display_review_result`，修复 `INTENT-02-REVIEW-OUTPUT-01`）② confirm 动作确认记录持久化（`ConfirmationRecord.from_executed_confirmation` + `ReplyCoordinator.find_clarification`）③ 执行反馈；删 `test_confirmation_main.py`；全量 432 项通过。真实会话 `20260814_104104`：20 段口述——查看显示多次生效（"当前没有待确认问题"/"当前共有 N 个"）、create 追问 3 次、answer 指定回答 3 次解决 2 个问题、计数"提交 6 段"、上下文 6 = 事件数、剩余问题列出；**附注**：确认记录真实路径未触发（无 needs_confirmation 场景，单测覆盖，VERIFY-01 补"水域/水浴"式场景） |
| 27 | `P0` | `INTENT-02-CLEANUP-NAMING-01` 去影子命名 | `AUTO_OK` | 观察器等改为正式执行链命名 | `unified_shadow.py`→`unified_observer.py`；`UnifiedShadowObserver`→`UnifiedObserver`、`ShadowObservation`→`UnifiedObservation`、`ShadowObservationStatus`→`UnifiedObservationStatus`、`create_unified_shadow_observer`→`create_unified_observer`、`display_shadow_observation`→`display_observation`、`shadow_observer`→`observer`、`shadow_executor`→`executor`、request_id 前缀 `shadow-`→`unified-`、显示前缀 `[新系统影子]`→`[统一链]`、docstring 去"影子"；`tests/test_unified_shadow.py`→`test_unified_observer.py`（类名同步）；src/tests 零 shadow 残留；全量 468 项通过；待一次轻量真实会话确认不退化（显示前缀 `[统一链]`、行为与之前一致） |
| 28 | `P1` | `INTENT-02-REVIEW-OUTPUT-01` 统一链 review 查看结果输出 | `REAL_OK` | 新链识别到 review 动作时显示待确认列表或"没有待确认问题" | **随 `INTENT-02-CLEANUP-COMMAND-01` 实现并验证**（`display_review_result` 搬进新链；会话 104104 多次显示"当前没有待确认问题"/"当前共有 N 个待确认问题"） |
| 29 | `P1` | `INTENT-02-ASR-ROBUSTNESS-01` ASR 误识别鲁棒性评测 | `REAL_OK` | 固定"噪声转写"集（真实误识别样例+同音变体）→ 统一链意图路由对照报告 | **提前执行（2026-08-14，用户直接要求，不改变 NAMING-01 的 P0 顺序）**。新增 `evaluation/narration_robustness/narration_plan.json`（28 段连贯实验口述：正常/缺失字段/无编号回答/错编号/双回答/只有编号/ASR误识别-控制/ASR误识别-实体/误识别+缺失双重/暂缓/否定修正/大小写变体容忍/上下文依赖/异常观察/测量/语义弃权/结束，每段带 spoken/observed 双文本与期望标注）+ `src/evaluation/narration_robustness_plan.py` 严格 schema + `tests/test_narration_robustness_plan.py` 21 项（schema 拒绝坏数据；13 实验段零控制误触发；"看待确认问题"依赖 LLM 容错、"还有什么问题"精确命中、"问题5。"缺答案→no_action、双回答已知限制文档化等）。确定性报告：零误触发 13/依赖LLM 7/精确命中 5/已知限制 3。真实 DeepSeek 旁路 `scripts/evaluate_narration_robustness.py --mode real`（只读）：**21/28 一致、7 缺口**，登记新任务 ASR-ROBUSTNESS-RULE-GAPS-01；全量 454 项通过 |
| 30 | `P1` | `UNIFIED-PROMPT-ASR-ERROR-CONFIRM-01` 统一Prompt补疑似ASR错词确认规则 | `REAL_OK` | 实体疑似同音错词/识别错误时 needs_confirmation=true + confirmation_reason + 确认追问 | 统一提示词实验规则新增"实体疑似同音错词或ASR识别错误时设置needs_confirmation"；合同测试断言；全量 433 项通过。真实会话 `20260814_110116` 段 11："使用一夜枪取50微升缓冲液" → 事件 `needs_confirmation=True, reason="疑似ASR识别错误：'一夜枪'可能应为'移液枪'"` + 确认问题"您说的'一夜枪'是指移液枪吗？"；段 12"问题三，是的，是一夜枪。" → confirm 执行 → **确认记录首次真实落盘**（experiment_confirmations.jsonl 第 1 行） |
| 31 | `P1` | `INTENT-02-ANSWER-UX-01` 回答体验：反馈补缺 + 无编号回答识别 | `REAL_OK` | ①answer 部分完成后明确提示"仍缺字段"；②仅一个待确认问题时无编号事实性短句判为对该问题的回答（多个时不得自动归属） | ①执行器 reason 含"仍需补充"（会话 110116 验证）；②无编号回答纯函数兜底 `src/core/answer_fallback.py`（单问题+短句+提取字段⊆缺失字段；夹带无关字段的实验记录绝不路由成回答）+ 提示词收紧 + 合同测试；467 项通过。真实会话 `20260814_113237` 验证：段 3"时间为10分钟"→ abstention 被兜底接住为 answer，反馈"已将对问题 1 的答复的实体字段 ['duration'] 填入。仍需补充：temperature"；段 4"60摄氏度"→ 补 temperature"问题已解决"；段 2"分中"听岔碎片不误判；无编号回答不产生实验事件（事件仅段 1）；计数"提交 1 段"、上下文 1、无剩余确认项 |
| 32 | `P1` | `INTENT-02-QUESTION-AUTO-OUTPUT-01` 追问/回答结果自动输出 | `REAL_OK` | create 后自动显示追问文本；answer 后自动显示"已填 X 仍缺 Y"；不依赖用户手动"查看待确认问题" | ①执行器 create reason 含问题文本；②`display_shadow_observation` executed 时显示 reason；真实会话 `20260814_110116`：段 1/5/11 create 后直接显示"已创建待确认问题 N：…"、段 10 answer 完整反馈、段 12 confirm 反馈——均自动输出，无需手动查看 |
| 33 | `P1` | `WEB-BRIDGE-01` web 统一链桥迁移（llm_bridge 旧链→统一链） | `REAL_OK` | 网页记录识别接入 `UnifiedUnderstandingProcessor`，不再依赖 src 已标待删的旧 `ExperimentLLMProcessor` | `web/llm_bridge.py` 换处理器 + `extract()` 加 `recent_context` + `input_kind` 标签；`web/api/record.py` 补 `_recent_context()`（最近 5 条口述）；新增 `tests/test_web_llm_bridge.py` 7 项（experiment/control/uncertain/降级/上下文过滤透传）；**环境修复**：`.venv` 补 numpy/sounddevice/soundfile/sherpa-onnx（funasr/torch 无需装，测试未直接 import），requirements.txt 补 numpy；迁移对照登记 `PROJECT_ARCHITECTURE.md` §5.3 WEB-BRIDGE-01 + §5.6；全量 715 项通过。**真实验收**（会话 `20260816_200646`，deepseek-v4-pro）：5 条口述无降级、实体抽取准确，口述 3「帮我看看待确认的问题」`input_kind=control`（旧链做不到）；缺时长未追问对应已登记争议 `LLM-FOLLOWUP-STRICT-01`，非迁移退化 | 功能 REAL_OK；体验验收（UX）待用户走查确认 |
| 34 | `P1` | `WEB-AGENT-FAKE-RECORD-01` 聊天 agent 假记录修复（用户 2026-08-16 在聊天区实测发现） | `REAL_OK` | 聊天 agent 对实验口述口头回复"已记录"却未调 record_observation 工具 → lab_records 无记录（数据丢失隐患） | 根因：`web/agent/core.py` INSTRUCTIONS 未引导模型使用 `record_observation` 工具（工具栏有但提示词没教）。修复：INSTRUCTIONS 新增"实验记录规则"——描述实验操作/数据必须调用 record_observation 并传原文，禁止不调工具就回复"已记录"，仅工具成功才可确认，失败须如实说明。新增 `tests/test_web_agent_prompts.py` 5 项提示词合同测试（防规则被误删 + 工具注册/schema 断言）。**真实验收**（重启 web 后 `/chat` 实测）：修复前 task 6830ffe4"已记录"但 lab_records 无新增；修复后 task 77ce319c"已记录"且 lab_records 新增 id=10「离心机八百转运行十分钟」（extraction_source=rule） | 全量 739 项通过；体验：话术未变但"已记录"变为真话（维 6 改善） |
| 35 | `P0` | `VOICE-WEB-MIGRATION-01` 语音接入 Web 迁移 Phase B（输出层接线） | `REAL_OK` | 把 CLI 统一理解输出层（UnifiedObservation→投影→文案）接入 web：过渡期用**降级生产者**产出**部分** UnifiedObservation，前端退役薄字典平行投影；B 阶段完成后写 5.3/5.4 迁移对照（标等价/降级/丢失） | 计划落点 `docs/VOICE_WEB_MIGRATION_PLAN.md`。**B1 定稿**（容忍部分观察分支）；**B2** partial 字段 13 项 + 降级生产者 12 项 + WebRenderer 10 项；**B3** /record 影子 messages 6 项；**B4** 前端 4 文件切渲染 messages + 迁移对照 §5.3 WEB-RENDER-01/02 + §5.4 web 侧行。**真实验收通过（2026-08-18/19，REAL_OK）**：用户实测语音记录闭环（灰色圈圈→录音→/record→面板回执"已记录"）+ 选方案缺字段→"小科追问"+ TTS 朗读。验收修复：WEB-RENDER-02 桌面语音死代码、话术撒谎硬问题（拆 RECORDED_NO_STEP/DEGRADED）、lab_panel.js 未注入、语音入口混乱治理（cp-mic 改语音记录、vad 改语音对话）、文案"小科追问"+TTS 不念前缀。**关键定位纠正（用户）**：统一理解链核心是处理命令（control 分支），B 降级生产者只有记录+方案追问，命令处理待 Phase D | **Phase B 全部完成 + 真实验收 REAL_OK**：全量 **800 项通过**；UX 走查证据已收集（反应慢/称呼重复/前端乱/undefined 段口述等），体验最终裁决权在用户 |

### 当前路线为什么这样排

```text
先把“听见了什么”测清楚
    ↓
再定义“用户想做什么”以及风险边界
    ↓
再决定“何时、通过什么渠道告诉用户”
    ↓
最后完成确认收尾、总结、聚合、导出和TTS
```

ASR、意图和展示属于三个不同问题。若同时修改，真实测试失败时无法判断究竟是模型没听清、
路由器理解错，还是消息没有在正确时机展示。

## 3.2 TTS 前阶段路线

### 阶段一：输入可靠性

```text
ASR-CMD-REC-01 语料采集器
→ ASR-CMD-01 固定语料与真实基线
→ ASR-CMD-02 比较ASR增强方案
→ ASR-03/04 专业实验词评测与热词对照
```

完成标志：控制语句和核心专业词都有固定WAV、参考文本和可重复报告，不再凭一次口述感觉调参。

### 阶段二：自然语言控制与安全边界

```text
INTENT-01 自然表达和风险等级
→ INTENT-02 IntentRouter
→ COMMAND-03 自然表达兼容
→ CLARIFY-TARGET-02 按步骤或主题指定回答
→ CLARIFY-07 否定并修正
```

完成标志：低风险查看可以语义容错；暂缓和回答具有明确目标；结束、删除等较高风险动作不能由
LLM猜测后直接执行。

### 阶段三：输出顺序与会话收尾

```text
PRESENT-INTEGRATE-01 最小消息链路
→ PRESENT-03/04/05/06 输出预算、编号和日志分流
→ TIMING-01/02/03 安全输出时机
→ CLOSING-01/02/03 确认收尾阶段
→ LLM-10 会话结束总结
```

完成标志：用户不会在操作后面时突然听到很早以前的无来源问题；可以跳过、回看和结束确认阶段；
屏幕内容、未来朗读内容和开发日志职责清楚。

### 阶段四：数据闭环与导出

```text
CLARIFY-TARGET-PERSIST-01 答复目标持久化
→ EXPERIMENT-EVIDENCE-CONTRACT-01 事件版本化
→ SESSION-02 按session_id聚合
→ EXPORT-01 Markdown/JSON导出
→ STABILITY-01/03/04 真实长会话验收
→ SAFETY-01/02 系统故障分级和用户消息
```

完成标志：一次实验从原始口述、结构化事件、确认答复到总结都能追溯，并可导出为真正可用的记录。

### 阶段五：TTS及表现层

```text
TTS-01 接口和假客户端
→ TTS-02 系统TTS
→ TTS-03/04/05 SPEAKING状态、降级和打断（半双工第一版）
→ FULL-DUPLEX-01~06 全双工增强（可选，回声能力达标后）
→ GPT-SoVITS
→ Live2D
→ Word/PDF美化导出
```

完成标志：TTS失败不会影响录音和记录；用户开始说话时系统能停止朗读；Live2D崩溃也不会破坏核心数据。

## 3.3 暂不提前开展的任务

| 优先级 | 任务 | 暂缓原因 | 重新启动条件 |
|---|---|---|---|
| `P3` | TTS（含全双工）、GPT-SoVITS、Live2D | 会把当前输出时序问题放大，且难以判断故障来源 | 阶段三和阶段四达到验收条件 |
| `P3` | Word/PDF报告美化 | 当前还没有完整SessionRecord可供可靠导出 | Markdown/JSON第一版真实导出通过 |
| `P3` | 多工具Agent | 外部写入和高风险动作尚未建立统一确认边界 | 安全等级、白名单和确认流程完成 |
| `P3` | 模型微调（LoRA）与本地推理（见第 4 节 K 组） | 数据量与质量未评估；当前问题可由提示词 + RAG 覆盖；需数据清洗与 GPU 投入；微调只解决"知道但做不对"，不解决"不知道" | RAG Phase 2（QUERY-ANSWER-01 等）落地且有足够真实确认样本后评估 |

> **注意**：RAG/用户画像和实验风险知识库已从"暂缓"移入正式任务总表第 I 节。
> 其中类型定义（QUERY-TYPES-01、SAFETY-TYPES-01、KNOWLEDGE-PROTOCOLS-01）为 P1 准备阶段；
> 完整实施（SAFETY-INTEGRATE-01、QUERY-ANSWER-01 等）为 P2，在 INTENT-02 清理和 PRESENT 阶段后展开。

## 3.4 个人开发范围与团队分工（待团队确认）

本节把“整个产品需要什么”和“当前开发者本人必须完成什么”分开。它来自现阶段讨论，属于建议稿，
在三人共同确认前不代表正式派工。

### A：当前开发者本人主责

这些模块决定语音实验记录主链是否可靠，应由本人持续维护和最终验收：

| 领域 | 主责内容 | 为什么适合本人负责 |
|---|---|---|
| 音频入口 | 唤醒、VAD、录音、WAV、播放期间资源协调 | 已有真实链路和故障经验，继续维护最容易保证原始证据 |
| ASR质量 | 固定语料、人工标签、基线、热词/模型对照 | 能直接从真实录音定位“截音、识别、意图”分别哪里错 |
| 自然意图 | InteractionCommand、IntentRouter、风险分层 | 它位于ASR与实验LLM之间，是语音助手安全边界 |
| 会话控制 | 状态机、后台队列、顺序、背压、优雅退出 | 已有完整上下文，交给多人同时修改容易产生时序故障 |
| 实验理解 | LLMClient、结构化事件、原文保护、降级 | 当前项目的核心差异化能力 |
| 追问确认 | PendingClarification、指定回答、修正与收尾 | 与语音上下文和实验事件高度相关 |
| 消息协调 | PresentationIntent、Coordinator/Pump、未来TTS播放策略 | 决定何时说、显示什么、失败怎样降级，不等于负责前端样式 |
| 会话记录 | SessionRecord、总结、Markdown/JSON第一版导出 | 负责把现场事实形成完整、可追溯记录 |

### A：建议新增的“跨模块学习型主责”

这些工作能学习接口、后端通信、系统集成和测试，又不需要接管队友内部实现：

| ID | 优先级 | 任务 | 状态 | 学习价值与边界 |
|---|---|---|---|---|
| `ARCH-01` | `P2` | 维护端到端数据流和模块边界图 | `TODO` | 学习系统架构；只描述职责和数据，不替各模块决定内部算法 |
| `CONTRACT-01` | `P2` | 定义设备查询第一版请求/响应/错误契约 | `TODO` | 学习API和Schema；需B共同确认，不能单方面定稿 |
| `PLANNING-CLIENT-01` | `P2` | 定义PlanningClient接口与Fake实现 | `TODO` | 学习依赖倒置和HTTP客户端；不直接访问B的数据库 |
| `PLANNING-CLIENT-02` | `P2` | 实现只读HTTP设备查询适配器 | `TODO` | 学习超时、错误映射和外部服务降级；B负责服务端 |
| `CONTRACT-TEST-01` | `P2` | 固定JSON契约测试 | `TODO` | 学习跨仓库协作；验证双方遵守接口，不测试B的内部函数 |
| `E2E-QUERY-01` | `P2` | 语音查询设备的端到端验收 | `TODO` | 学习系统集成和分层排错；只读查询，不修改日程 |
| `E2E-DEMO-01` | `P2` | 维护2～3分钟稳定Demo脚本和验收表 | `TODO` | 学习产品化和质量保证；三人共同提供模块能力 |
| `OBS-01` | `P2` | 统一跨模块request_id与关键耗时记录 | `TODO` | 学习可观测性；不把debug日志混入用户消息 |

这些任务不立即插队。建议在 `INTENT-02` 稳定后依次开展：

```text
CONTRACT-01
→ PLANNING-CLIENT-01 Fake客户端
→ CONTRACT-TEST-01
→ PLANNING-CLIENT-02 真实HTTP
→ E2E-QUERY-01
```

### A：共同参与，但不应独自包揽

| 事项 | 本人适合做什么 | 不应包揽什么 |
|---|---|---|
| 计划与设备后端 | 参与Schema、调用接口、写契约和集成测试 | 数据库表、冲突算法、后端权限和所有API实现 |
| 前端页面 | 定义消息语义、提供Mock事件、验收展示顺序 | 整套页面布局、组件、动画和Live2D渲染 |
| GPT-SoVITS服务 | 定义TTSClient、超时、缓存和降级要求 | 同时承担服务部署、训练、音色调优和播放状态全部工作 |
| 报告导出 | 定义SessionRecord并实现Markdown/JSON内容 | 同时包揽前端预览、Word/PDF美化和队友计划数据生成 |
| 安全规则 | 定义语音意图风险、确认和降级接口 | 单独制定实验室SOP、设备权限和全部业务规则 |
| 比赛集成 | 维护主链验收、故障注入和演示脚本 | 一个人修复所有队友模块内部缺陷 |

### 建议由B主责

```text
实验计划与设备数据库
→ 设备稳定ID和资源状态
→ 时间冲突与预约规则
→ 待确认计划提案及其持久化
→ 确认后写入、幂等、权限和审计
→ FastAPI服务端及OpenAPI文档
```

A可以通过Fake客户端、契约测试和代码评审学习这些知识，但生产实现和数据责任应有明确负责人。

### 建议由C主责

```text
Web展示页面
→ 用户/助手消息布局和状态可视化
→ 实验时间线、设备状态、待确认问题和报告预览
→ WebSocket或事件订阅适配
→ Live2D表现、口型、演示模式和展示打包
```

A负责提供稳定消息协议和Mock数据，不应让前端直接读取 `main.py` 的终端输出。

### “多学习但不包揽”的执行规则

1. 每个生产模块只有一个明确主责人，其他人通过评审、测试和接口参与。
2. 想学习队友领域时，优先写Fake、契约测试、客户端或小型实验，不复制一套生产服务。
3. 联调故障先定位所属层，再由主责人修复内部实现；集成人负责提供可重复证据。
4. 共同任务必须写清最终拍板人，避免“三个人都负责”等于没人负责。
5. 当前个人任务一次仍只推进一个可独立验证能力，跨模块学习任务不得打断当前ASR主线。

### 第一次团队确认只需要决定的事项

| 需要确认 | 建议默认值 |
|---|---|
| A/B/C长期边界 | A语音会话；B计划设备；C前端展示 |
| 第一条联合链路 | 只读查询一号离心机是否空闲 |
| 公共字段 | equipment_id、start_at、end_at，时间带时区 |
| 写入安全 | 第一轮完全只读；后续修改必须提案+明确确认 |
| 接口变更方式 | 先改契约和示例，再改双方实现 |
| 联合验收责任 | A维护端到端步骤，B/C各自修复所属模块 |

## 4. 任务总表

### 0. 本地开发环境

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `ENV-01` | `P1` | 修复或重建主 `.venv` | `REAL_OK` | Python 3.11.9与`.venv`均正常；先前失败是Codex沙箱拒绝执行AppData解释器造成的误判；沙箱外复验218项全量测试和真实SenseVoice对照均通过 |
| `ENV-02` | `P3` | 保留 Python 3.14 备用环境 | `REAL_OK` | 已恢复为 `.venv-py314`，不作为正式开发与验收环境 |
| `ENV-03` | `P2` | 建立可复现的依赖锁定文件 | `TODO` | 当前requirements只列直接依赖且未固定版本；应在功能稳定后生成3.11锁定版本 |

### A. 音频、唤醒与 ASR 基础

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `AUDIO-01` | `P0` | 麦克风录音和 WAV 保存 | `REAL_OK` | 多次真实口述已生成 `audio/recordings/*.wav` |
| `VAD-01` | `P0` | 检测开始说话和自然停顿 | `REAL_OK` | 真实日志包含“检测到人声/检测到说话结束” |
| `KWS-01` | `P1` | 离线唤醒“小科小科” | `REAL_OK` | 真实日志多次唤醒成功 |
| `ASR-01` | `P0` | FunASR/SenseVoice 中文识别 | `REAL_OK` | 真实实验口述已识别并保存 |
| `ASR-02` | `P0` | 专业词错误保留原文 | `REAL_OK` | “一液枪/微生”等原文未被覆盖 |
| `ASR-03` | `P2` | 建立实验专业词固定评测集 | `TODO` | 真实验收发现专业词错词较多；需固定音频、期望文本和错词统计；复用 ASR-CMD 系列的固定语料评测工具与报告格式，不另建一套 |
| `ASR-04` | `P2` | 专业词热词/文本后处理对照实验 | `TODO` | 当前识别调用未传热词；必须在 ASR-03 后比较，且保留模型原文 |
| `ASR-05` | `P0` | 固定中文语言参数对照测试 | `REAL_OK` | 14条真实WAV对照：auto文本8/14、意图9/14；zh文本8/14、意图10/14；zh有一项意图改善但也产生两项文本回退，暂不修改main默认auto |
| `ASR-CMD-01` | `P0` | 建立通用控制命令文本/音频语料和基线 | `REAL_OK` | 新增accepted尝试→真实ASR清单/基线生成器；24条人工接受WAV使用SenseVoice language=auto、use_itn=True、batch_size_s=60两次真实运行汇总一致：文本精确13/24、精确规则意图11/24、控制漏触发13、普通内容误触发0；进一步用人工参考文本诊断出规则覆盖不足13、ASR额外造成意图漏触发0；全量297项通过；本地识别清单和报告不上传 |
| `ASR-CMD-REC-01` | `P2` | 独立采集控制命令固定语料 | `REAL_OK` | 正式入口真实完成24/24；共31次尝试，24次accepted、7次retry_requested；三条待补样本通过断点恢复再次采集；24个样本ID各有且只有一条接受记录，31个WAV路径全部存在；本地音频与尝试清单不上传GitHub |
| `ASR-CMD-REC-DATA-01` | `P0` | 定义语料提示项和录音尝试数据对象 | `AUTO_OK` | 新增不可变CommandCorpusPrompt、RecordingAttempt及状态枚举；11项专项测试通过；严格校验确认、失败、跳过和基线资格；JSON路径跨平台统一为正斜杠 |
| `ASR-CMD-REC-STORE-01` | `P0` | 追加式保存录音尝试清单 | `AUTO_OK` | 原子临时文件替换；attempt_id防重复；允许同一句不同attempt；损坏旧文件和替换失败不覆盖；新增6项存储测试，专项17项及全量152项通过 |
| `ASR-CMD-REC-COORD-01` | `P0` | 通用录音、回放、人工决策和证据保存协调器 | `AUTO_OK` | 接受/截断/重复/重录/跳过/录音失败/播放失败统一转换为RecordingAttempt；WAV优先保留；7项专项、全量203项通过 |
| `ASR-CMD-REC-PROMPTS-01` | `P0` | 固定提示稿计划和断点恢复 | `AUTO_OK` | schema_version=1严格加载；拒绝额外字段/重复ID/未知意图；正式24条覆盖7类意图；只有accepted算完成；7项专项、全量210项通过 |
| `ASR-CMD-REC-CLI-01` | `P0` | 正式独立命令行采集入口 | `AUTO_OK` | 可恢复会话运行器5项测试；正式--status烟雾测试显示0/24及尝试号；入口复用计划/协调器/存储；全量215项通过 |
| `ASR-CMD-02` | `P0` | 使用固定命令集比较 ASR 增强方案 | `DESIGN` | 固定中文参数真实对照已完成，未显示无代价全面改善；下一步比较热词；同一批音频一次只改一个变量 |
| `ASR-CMD-02-LANGUAGE-01` | `P0` | language=auto与固定中文参数对照 | `REAL_OK` | Python3.11运行28次真实识别并生成language_comparison.json；auto文本8/14、意图9/14、漏触发5；zh文本8/14、意图10/14、漏触发4；普通内容误触发均为0；暂不改main |
| `ASR-CMD-02-HOTWORD-01` | `P2` | 无热词与固定热词参数对照 | `BLOCKED` | FunASR 1.4.1通用AutoModel声明hotword参数，但当前SenseVoiceSmall.inference不读取模型级hotword；直接传参会被kwargs吞掉，无法形成可信单变量对照；待未来换用明确支持热词的ASR模型后复验 |
| `ASR-CMD-02-POSTPROCESS-01` | `P2` | 固定专业词模糊后处理对照 | `REAL_OK` | 使用24条已保存原始ASR文本、固定目标词移液枪/水浴/滴定管、阈值0.85；只生成候选不覆盖原文；修改4条，目标术语0/4→4/4，严格文本13/24→16/24，意图11/24不变，文本/意图回退均0；新增4项测试、全量301项通过；样本内选词存在过拟合风险，未接main。**接入计划（用户 2026-08-14 决策）：等组长确定演示实验领域（生物/物理/医药）后，重启该领域术语采集 + 独立语音复验 + 接入**（工厂给 SenseVoiceBackend 注入术语后处理函数，下游无感） |
| `ASR-BACKEND-CONTRACT-01` | `P1` | 模型无关ASR后端合同与工厂 | `REAL_OK` | 新增ASRBackend Protocol、SenseVoiceBackend和create_asr_backend；main及三个独立真实脚本不再直接构造具体模型；ASR_BACKEND集中配置且默认sensevoice，未知后端在加载模型前明确拒绝；保留ASRResult、原始模型文本和旧ASR_MODEL兼容名；新增7项Fake/临时WAV测试、ASR下游38项及全量308项通过；通过新工厂真实识别18.072秒固定WAV，模型iic/SenseVoiceSmall、识别1.922秒；尚未实现第二模型 |
| `ASR-EVIDENCE-CONTRACT-01` | `P0` | ASR、LLM与用户消息原始证据命名合同 | `REAL_OK` | `ASRResult`升级为不可变schema v2：`asr_model_raw_text`保存ASR引擎直接文本字段，`asr_transcript`保存确定性去标签后的忠实可读转写；新写入不再生成含糊的`text/raw_text`键，旧构造与只读属性仅作过渡。新增独立不可变`TranscriptCorrectionCandidate`，源转写与候选必须不同，纠错不能回写证据。`ASRResultStore.load_all()`严格读取v1/v2并保留会话来源，损坏行明确报行号；182条现有v1历史记录全部读取成功且文件SHA-256前后不变。SenseVoice适配器、main、命令/确认处理、评测和真实脚本已迁移到明确字段；测试Fake也改为正式ASRResult而非半对象。新增10项合同/存储测试，专项17项、下游47项、Python3.11全量318项通过；真实18.072秒固定WAV输出schema v2，模型原始文本与忠实转写均非空且不同，识别1.482秒。LLM原始响应仍由现有严格Processor边界管理，本轮未重命名ExperimentEvent或PresentationMessage字段，未批量迁移历史文件 |
| `ASR-CMD-02-MODEL-CANDIDATE-01` | `P2` | 热词模型候选验证 | `TODO` | 候选优先SeACo/contextual Paraformer；先用源码/能力探针证明推理路径真正读取模型级hotword，再以同一批24条accepted WAV完成SenseVoice原始、SenseVoice＋文本后处理、候选模型无热词、候选模型有热词四组对照；固定热词为移液枪/水浴/滴定管；保留各模型原文并记录模型标识、配置、耗时、峰值内存、目标术语命中、严格文本、意图、普通内容误触发及改善/回退；候选验证不得替换当前模型、不得接main、不得上传WAV/模型权重/逐条本地报告。通过门槛：有热词相对候选无热词目标术语改善，意图和普通句无新增回退，并在独立新增语音上复验；否则保留SenseVoice与后处理方案 |
| `INTENT-01` | `P0` | 定义自然控制表达与风险等级 | `AUTO_OK` | 新增IntentRisk、IntentEvidence、IntentDisposition、IntentPolicy和IntentDecision；7项专项及全量225项通过；精确结束可执行，语义/LLM结束必须确认，LLM不得直接写确认状态；尚未接main |
| `INTENT-02` | `P0` | 实现 ASR 与实验LLM之间的轻量 IntentRouter | `DESIGN` | 精确路由子步骤已AUTO_OK：IntentRouter组合InteractionCommandParser与IntentPolicyEvaluator，返回不可变IntentRouteResult；7项路由测试、相关30项及全量232项通过；尚未接自然语义、协调器或main |
| `INTENT-02-EXACT-01` | `P0` | 精确命令统一路由 | `AUTO_OK` | 普通口述进入实验链路；查看/答复进入上下文；精确结束进入执行；保留raw_text和答复编号；自然表达不猜测；7项专项通过 |
| `INTENT-02-CLASSIFIER-01` | `P0` | 定义LLM意图分类接口和候选结构 | `AUTO_OK` | 新增IntentClassificationInput、IntentCandidate、IntentClassifier协议、FakeIntentClassifier及IntentClassifierError；严格拒绝缺失/额外/越权字段；10项专项、全量242项通过；未调用真实LLM |
| `INTENT-02-CLASSIFIER-ROUTE-01` | `P0` | Fake分类器接入IntentRouter | `AUTO_OK` | 精确命令绕过分类器；未命中才分类；候选统一经过风险策略；结束候选只REQUEST_CONFIRMATION；超时保留raw_text并降级为普通链路且记录错误；新增6项集成测试，全量248项通过；未接main |
| `INTENT-02-PROMPT-01` | `P0` | 意图弃权状态与严格提示词合同 | `AUTO_OK` | IntentCandidate新增matched/uncertain；uncertain必须清空意图/编号/答案；新增稳定System Prompt和JSON User Prompt构造；Router显式标记classification_uncertain并禁止控制动作；提示词2项、相关27项、全量252项通过 |
| `INTENT-02-LLM-ADAPTER-01` | `P0` | LLMIntentClassifier适配器 | `AUTO_OK` | 新增src/llm/intent_classifier.py；复用LLMClient.generate_json和提示词，将字符串解析为顶层JSON对象后严格构造IntentCandidate；合法、uncertain、非法JSON/非对象、额外字段、客户端异常5项通过；全量257项通过 |
| `INTENT-02-LLM-INTEGRATION-01` | `P0` | LLM适配器与IntentRouter模块集成 | `AUTO_OK` | FakeLLMClient→LLMIntentClassifier→IntentRouter→IntentPolicy完整链路7项通过；精确绕过、自然查看、高风险结束、uncertain、非法JSON、客户端异常、普通实验均覆盖；全量264项通过 |
| `INTENT-02-LLM-REAL-01` | `P0` | DeepSeek意图分类烟雾与延迟验收 | `REAL_OK` | 独立脚本固定5条非敏感文本全部符合预期；normal/review/end/uncertain/targeted_answer及策略出口正确；均1次成功，耗时1.700～1.884秒，平均约1.808秒；未接main，未保存/上传逐条响应 |
| `INTENT-02-ARCH-01` | `P0` | 独立意图调用与统一LLM调用架构决策 | `DESIGN` | 决策为“精确规则本地快速路径＋未命中统一一次LLM理解”；两组完整真实配对中独立两次为5.809/5.621秒，统一一次冷缓存10.980秒、热缓存2.636秒；统一首次格式失败后补齐跨字段规则；另两次统一请求遇SSL断连，证据不足归因架构；先正式化合同再扩大评测 |
| `INTENT-02-UNIFIED-CONTRACT-01` | `P0` | 统一输入理解三分支数据合同 | `AUTO_OK` | 新增UnifiedUnderstandingResult及experiment/control/uncertain不可变分支；严格拒绝缺失、额外、混合、原文篡改和uncertain伪装control；失败可降级为保留原文的未分类NOTE且不产生控制候选；新增7项专项、全量276项通过；未接真实LLM、main或ReplyCoordinator |
| `INTENT-02-UNIFIED-PROCESSOR-01` | `P0` | 正式统一提示词与Processor | `AUTO_OK` | 新增可信输入上下文、封闭三分支Prompt和UnifiedUnderstandingProcessor；Fake覆盖experiment/control/uncertain、非法JSON、客户端失败、指标与来源注入；相关15项、全量284项通过；未接真实LLM和main |
| `INTENT-02-UNIFIED-REAL-01` | `P0` | 正式统一理解真实烟雾 | `REAL_OK` | 固定5条非敏感文本真实验收；首轮实验分支因amount_value返回数字被严格拒绝并安全降级，补充“数值也必须是字符串”后完整复验5/5；均首次成功，耗时1.614～2.441秒；未打印/保存逐条原始响应，未接main |
| `INTENT-02-UNIFIED-ROUTE-01` | `P0` | 精确快速路径与统一理解模块组合 | `AUTO_OK` | 新增UnifiedUnderstandingRouter和单一路径UnifiedRouteResult；精确控制绕过完整LLM链，未命中才统一理解；自然结束经过风险策略只请求确认，指定回答DO_NOT_EXECUTE；experiment、uncertain、非法JSON、客户端失败和指标均覆盖；新增7项集成测试、全量293项通过；未接main |
| `INTENT-02-UNIFIED-DISPATCH-01` | `P0` | 统一路由结果分派合同 | `AUTO_OK` | 新增不可变UnifiedDispatchPlan、UnifiedDispatchDestination、UnifiedDispatchPermission和纯UnifiedDispatchPlanner；六类目标为实验链路、待确认上下文、精确结束执行候选、LLM结束确认、安全弃权、降级NOTE。统一优先规则为：degraded优先隔离、uncertain明确弃权、其余控制服从IntentDisposition、始终原样保留路由输入；目标与最小权限非法组合立即拒绝。Planner无存储、状态机、ReplyCoordinator或TTS依赖，不执行任何副作用；10项专项、4项真实Router→Planner Fake集成、连同既有路由共21项及Python3.11全量332项通过；未接main |
| `INTENT-02-UNIFIED-DISPATCH-INTEGRATION-01` | `P0` | 固定文本旁路分派集成 | `AUTO_OK` | 新增UnifiedDispatchBypassInput、UnifiedDispatchBypass和只读UnifiedDispatchObservation；只把最终ASRResult.asr_transcript转成UnifiedUnderstandingInput，明确不转发asr_model_raw_text；Router若替换文本立即失败。观察报告只含转写、路由来源、风险、处置、目标、最小权限和指标，不含执行方法或模型标签文本。独立模块脚本使用五类固定Fake结果验证experiment_pipeline、clarification_context、end_session_confirmation、abstention和degraded_note；首次直接脚本启动因Python导入路径失败，改用`python -m scripts.evaluate_unified_dispatch_bypass`成功。新增6项专项、全量338项通过；未访问网络、麦克风或存储，未接main |
| `INTENT-02-UNIFIED-DISPATCH-WAV-01` | `P0` | 固定WAV真实旁路验收 | `REAL_OK` | 新增独立真实旁路脚本和严格报告字段白名单；2项新测试证明报告不包含ASR模型标签、绝对路径、LLM原始响应或错误详情，真实Processor失败只能进入degraded_note；专项12项、Python3.11全量340项通过。经用户明确授权，固定`03_terms_second.wav`真实SenseVoice转写进入DeepSeek一次：18.072秒音频识别1.593秒，LLM首次成功1.961秒，路由为normal/pass_to_experiment，分派为experiment_pipeline＋forward_experiment_analysis，未降级。未写业务文件、未调用状态机、ReplyCoordinator或TTS；FunASR启动仍检查/刷新模型缓存，继续由MODEL-LOAD-02跟踪 |
| `INTENT-02-DISPATCH-EXECUTION-CONTRACT-01` | `P0` | 分派执行请求与结果合同 | `AUTO_OK` | 新增不可变DispatchExecutionRequest/Result、DispatchExecutionStatus、DispatchExecutor Protocol和无副作用FakeDispatchExecutor。请求绑定request/session/segment、最终ASRResult和UnifiedDispatchPlan，ASR原文不一致立即拒绝；结果回显身份、目标和最小权限，并把accepted/rejected/failed/no_action与state_changed、persisted、message_ids分开，未接受结果不得声称副作用。Plan和Result复用同一目标→权限规则；Fake可按权限接受/拒绝/失败，重复相同request_id返回同一结果且只计一次，不同请求碰撞同一ID立即拒绝。新增10项测试，相关24项、Python3.11全量350项通过；未接main、存储、状态机、ReplyCoordinator或TTS，因此只到AUTO_OK |
| `INTENT-02-EXPERIMENT-ACCEPTANCE-CONTRACT-01` | `P0` | 统一理解实验候选采用合同 | `AUTO_OK` | 新增纯ExperimentCandidateAcceptor、不可变AcceptedExperimentAnalysis和STRUCTURED_EXPERIMENT/DEGRADED_EVIDENCE_NOTE用途分类。采用时核对DispatchExecutionRequest、统一理解分支、request/session/segment、ASR忠实转写、每个事件来源、分派目标/权限、降级错误和事件数量；正常实验只从experiment_pipeline采用，degraded_note只能产生一个不改写原文且需确认的NOTE，降级形状即使伪造degraded=false也不能混入正常采用。旧可变LLMAnalysisResult被转换为规范JSON快照，可信source字段不混入模型业务JSON，需要交给旧存储边界时严格解析成全新对象，绝不再次调用LLM。新增10项测试，相关37项、Python3.11全量360项通过；未写事件、ASR或上下文，因此只到AUTO_OK |
| `INTENT-02-CLARIFICATION-ACCEPTANCE-01` | `P0` | 待确认动作采用合同 | `AUTO_OK` | 新增不可变ClarificationContextSnapshot、ClarificationAction及纯ClarificationActionPlanner。动作分为create/review/defer/answer/confirm/reject_suggestion/no_action，最小权限分为none/read_only/prepare_create/prepare_update；PREPARE只生成带目标clarification_id、display_number和expected_revision的计划，没有commit方法。精确规则查看可只读；暂缓、肯定、否定和指定回答只有目标存在且答案完整时才准备更新；编号不存在、缺答案或无当前问题转为no_action。低风险LLM查看只能只读，所有LLM中风险状态候选即使编号有效也保持abstention/no_action。已采用正常实验的追问可准备CREATE且要求先保存来源ASR；degraded NOTE不创建假问题。新增13项测试，相关43项、Python3.11全量373项通过；未访问或修改ReplyCoordinator、存储、状态机或TTS |
| `INTENT-02-ACCEPTANCE-INTEGRATION-01` | `P0` | 固定文本完整采用链集成 | `AUTO_OK` | 新增UnifiedAcceptanceBypass，把真实UnifiedUnderstandingRouter、UnifiedDispatchPlanner、DispatchExecutionRequest、ExperimentCandidateAcceptor和ClarificationActionPlanner串成无副作用链，配确定性Fake Processor与只读上下文。9项新增测试覆盖普通实验、实验追问CREATE、精确/LLM查看、精确暂缓、编号回答、LLM中风险弃权、degraded NOTE及请求身份/ASR原文贯穿；相关59项、Python3.11全量382项通过。旁路不持有存储、SessionContext、ReplyCoordinator或TTS，且暂不处理结束会话目标，因此只到AUTO_OK |
| `INTENT-02-MAIN-SHADOW-INTEGRATION-01` | `P0` | main影子观察接入 | `REAL_OK` | 新增默认关闭的UNIFIED_SHADOW_ENABLED开关、UnifiedShadowObserver和脱敏ShadowObservation；自动3项隔离、相关16项、Python3.11全量385项通过。用户明确授权本次逐条ASR忠实转写发送DeepSeek后开启本机开关，真实会话`20260810_120209`共4段：前三段进入experiment_pipeline/structured_experiment且只观察不执行；第4段精确结束候选进入旁路未开放的结束目标，被转换为ValueError失败摘要，旧流程继续，证明失败隔离生效。影子没有写业务文件、更新SessionContext/ReplyCoordinator或发TTS。真实结果同时发现追问一致性与旧main命令标准化问题，已拆分任务，REAL_OK只表示影子接线和隔离真实成立，不表示新业务判断全部正确 |
| `INTENT-02-FOLLOWUP-INVARIANT-01` | `P0` | 追问跨字段一致性合同 | `AUTO_OK` | 初步诊断误把旧链保存的missing_fields当成新影子链字段证据。测试优先复核发现src/llm/validation.py原本已计算requires_follow_up，并拒绝三类矛盾：有missing_fields却不追问、needs_confirmation为true却不追问、无任何事件依据却凭空追问；ExperimentCandidateAcceptor生成/物化规范快照时再次调用严格parse_analysis，构成下游复查。新增上游3项、下游2项反例测试，影子摘要新增missing_fields与follow_up_required但不含口述正文；相关25项、Python3.11全量390项通过。下次真实复验可直接区分“未识别缺失字段”和“追问决策矛盾” |
| `INTENT-02-END-NORMALIZATION-UNIFY-01` | `P0` | 结束命令标准化单一来源 | `REAL_OK` | 真实会话第4段ASR“接受实验记录。😔”复现规则漂移后，删除main独立END_SESSION_COMMANDS和独立正则；兼容入口委托InteractionCommandParser。新增情绪尾反例与一致性2项，相关37项、Python3.11全量392项通过。修改后真实短会话仅说结束命令：Python主程序已停止；asr_segments在测试前后均186条、experiment_events均133条，最后记录仍为上一会话旧记录，证明本次结束口述在segment分配前被截住，没有进入影子/旧LLM或业务存储；任务升级REAL_OK |
| `INTENT-02-SHADOW-FOLLOWUP-OBSERVE-01` | `P0` | 新链追问字段真实观察 | `REAL_OK` | 真实会话`20260810_180242`的ASR为“将溶液加热。”，业务记录从186增至187、事件从133增至134，结束命令未落库。影子终端与同一保存证据的单独重放一致：experiment_pipeline、structured_experiment、missing_fields=()、follow_up_required=false、clarification_action=no_action；旧链同句提取temperature/duration并生成追问。对比Prompt发现旧版明确规定操作缺少有意义的体积/浓度/温度/时间时登记missing_fields，新统一Prompt只规定missing_fields非空后的追问一致性，因此这是能力规则遗漏，不是跨字段合同失效 |
| `INTENT-02-UNIFIED-PROMPT-MISSING-FIELDS-01` | `P0` | 统一Prompt缺失字段能力对齐 | `REAL_OK` | 统一Prompt实验规则新增一行”操作缺少对当前实验有意义的体积、浓度、温度或时间时，写入missing_fields并生成一个简短追问”；Prompt合同测试新增关键词验证；全量392项通过；真实DeepSeek以”将溶液加热。”复验成功输出missing_fields=['temperature','duration']、should_ask_follow_up=True、follow_up_question=”加热到什么温度？需要加热多长时间？”，1次成功2.32秒 |
| `INTENT-02-LLM-TOKENS-01` | `P2` | 意图分类独立token上限 | `TODO` | 烟雾响应仅约33～50 completion tokens，但当前沿用LLM_MAX_TOKENS=2000；若保留独立调用，应增加较小的专用配置并复验截断 |
| `INTENT-02-REPLY-GATE-01` | `P1` | LLM答复候选进入ReplyCoordinator前的目标校验 | `AUTO_OK` | 新增ClarificationExecutor+ClarificationExecutionResult把ClarificationAction映射为ReplyCoordinator原子操作；ReplyCoordinator新增register_clarification/defer_clarification/confirm_clarification/find_clarification并重构_register_clarification委托到新方法；新增23项测试覆盖7种动作类型及全生命周期；全量415项通过；未接main.py，ANSWER暂不填充字段 |
| `INTENT-02-SEMANTIC-01` | `P3` | 本地自然表达穷举 | `TODO` | 不作为当前主线；仅在未来有离线、低延迟或特定短语需求时补充，不能要求用户背命令语料 |
| `MODEL-LOAD-01` | `P1` | ASR 和唤醒模型在进程内只加载一次 | `REAL_OK` | 当前 `main()` 启动时创建一次并跨会话复用 |
| `MODEL-LOAD-02` | `P2` | 固定FunASR模型修订并关闭不必要的启动更新检查 | `TODO` | 2026-08-08烟雾测试仍访问ModelScope master并检查/下载文件；需验证缓存和断网启动 |
| `AUDIO-PREROLL-01` | `P0` | 录音句首预缓冲 | `DESIGN` | 缓冲、时间线、组装和VadAudioRecorder假设备接入已完成；仍需“这/查/跳”各3次真实WAV回听与ASR分离验收 |
| `AUDIO-PREROLL-BUFFER-01` | `P0` | 固定容量PreRollBuffer | `AUTO_OK` | deque保存float32单声道块；溢出只丢最旧采样；输入和snapshot均复制隔离；10项专项测试及全量162项通过 |
| `AUDIO-PREROLL-INTEGRATE-01` | `P0` | 将预缓冲与语音段安全组装 | `AUTO_OK` | 新增无状态PreRollSpeechAssembler；重叠量必须显式给出且重复采样必须完全一致；11项专项测试及全量173项通过 |
| `AUDIO-PREROLL-TIMELINE-01` | `P0` | 为预缓冲标记绝对采样区间 | `AUTO_OK` | PreRollSnapshot使用半开区间[start,end)；溢出后保留绝对end；clear重置下一次录音；7项专项及全量180项通过 |
| `AUDIO-PREROLL-RECORDER-01` | `P0` | 按采样时间线接入VadAudioRecorder | `AUTO_OK` | 触发时冻结快照；用segment.start计算重叠；成功/超时均reset VAD；连续录音隔离；时间线7项、录音器4项，全量191项通过 |
| `AUDIO-PREROLL-REAL-TOOL-01` | `P0` | 真实句首WAV录制、即时回放和分阶段ASR工具 | `AUTO_OK` | 录制阶段只回放并保存人工结论；只有显式--asr才识别人工接受的WAV；4项专项及全量195项通过 |
| `AUDIO-PREROLL-REAL-01` | `P2` | 句首预缓冲真实WAV验收 | `TODO` | 首轮5/9完整、4/9截断、0重复；提示时机已修复；因用户当前不方便录音而后推，恢复时执行第二轮同样9句复验 |

### B. LLM 结构化与降级

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `LLM-01` | `P1` | 统一 LLMClient 接口 | `REAL_OK` | DeepSeek 真实请求通过 |
| `LLM-02` | `P1` | 严格 JSON 协议和额外字段拒绝 | `REAL_OK` | 自动测试通过；真实结构化成功 |
| `LLM-03` | `P0` | 保留 raw_text，不直接覆盖 ASR | `REAL_OK` | 真实事件同时保留 raw/normalized |
| `LLM-04` | `P1` | 空响应、超时、429、5xx 有限重试 | `AUTO_OK` | 重试单测通过；尚缺真实故障注入验收 |
| `LLM-05` | `P1` | DeepSeek 关闭 thinking 模式 | `REAL_OK` | 真实日志 `thinking.type=disabled` |
| `LLM-06` | `P2` | 尝试次数和处理耗时 | `REAL_OK` | 真实 JSONL 含 attempts/seconds |
| `LLM-07` | `P1` | 操作、观察、测量、异常分类 | `REAL_OK` | 会话 `20260806_102742` 四类结果正确 |
| `LLM-08` | `P1` | 缺少关键参数时产生追问 | `REAL_OK` | “将溶液加热”产生温度/时间追问 |
| `LLM-09` | `P1` | 阶段总结接口 | `AUTO_OK` | processor/validation 单测通过，未接主流程 |
| `LLM-10` | `P1` | 会话结束总结接入 | `TODO` | 依赖确认收尾流程 |
| `PROTOCOL-01` | `P0` | 实验方案数据合同、严格方案库、选择结果与确定性缺失字段 | `AUTO_OK` | frozen dataclass严格校验；实体字段白名单动态来自`dataclasses.fields(ExperimentEntities)`；3份种子方案可加载；79项专项、全量501项通过 |
| `PROTOCOL-INTEGRATION-01` | `P0` | 方案选择与当前步骤接入会话主链路 | `TODO` | 下一轮任务；先定义会话级已选方案/当前步骤状态，再让程序计算缺失字段；保留无方案自由记录，避免直接修改现有统一理解合同 |

### C. 后台队列与会话上下文

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `QUEUE-01` | `P1` | LLM 后台处理，录音可继续 | `REAL_OK` | 真实日志显示 LLM 请求期间仍在录音 |
| `QUEUE-02` | `P1` | 单线程顺序保证 | `AUTO_OK` | 队列顺序测试通过 |
| `QUEUE-03` | `P1` | 最大积压和背压 | `AUTO_OK` | backpressure 测试通过 |
| `QUEUE-04` | `P1` | 会话结束优雅等待 | `REAL_OK` | 真实结束时等待剩余任务完成 |
| `SESSION-WORK-CONTRACT-01` | `P1` | 通用会话工作项与完成结果合同 | `TODO` | 当前CompletedSegment绑定旧ProcessOutcome[LLMAnalysisResult]；改为只表达任务身份、类型、完成/拒绝/失败状态和业务载荷，使队列只负责顺序、背压与异常隔离，不猜测所有任务都是旧实验LLM；与 INTENT-02 清理同步执行，否则旧 ProcessOutcome[LLMAnalysisResult] 耦合残留于队列层 |
| `CTX-01` | `P1` | 最近事件上下文 | `REAL_OK` | 上下文进入真实提示词，单测通过 |
| `CTX-02` | `P0` | NOTE 使用 raw_text | `AUTO_OK` | SessionContext 单测通过 |
| `SESSION-CONTEXT-CONTRACT-01` | `P1` | 结构化会话上下文证据项 | `TODO` | 用不可变ContextEvidenceItem保存来源、证据类型、忠实文本、规范候选、确认与降级状态；给LLM前再格式化为字符串，避免当前deque[str]丢失来源和可信等级；与 INTENT-02 清理同步执行，否则旧 deque[str] 上下文残留于会话层；其结构将被 `RAG-CONTEXT-CONTRACT-01` 的 EnrichedContext.recent_events 消费，定结构时预留拼接边界 |

### D. 存储、会话与导出

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `STORE-01` | `P0` | ASR JSONL 保存 | `REAL_OK` | 真实会话记录存在 |
| `STORE-02` | `P0` | 实验事件 JSONL 保存 | `REAL_OK` | `experiment_events.jsonl` 已核验 |
| `STORE-03` | `P0` | 事件可追溯到 session/segment | `REAL_OK` | 真实事件 source id 正确 |
| `STORE-04` | `P1` | LLM 降级元数据保存 | `REAL_OK` | 真实历史日志出现降级 NOTE |
| `EXPERIMENT-EVIDENCE-CONTRACT-01` | `P1` | 版本化实验事件证据合同 | `TODO` | 为事件记录增加schema_version、严格from_dict、未知字段拒绝、历史兼容读取、request_id、ASR证据引用、生成路径和采用状态；坚持新写新版本、旧读旧版本、不原地覆盖历史 |
| `SESSION-01` | `P0` | 每次实验使用独立 session_id | `REAL_OK` | 会话编号已进入 ASR/事件记录 |
| `SESSION-IDENTITY-CONTRACT-01` | `P1` | 会话内身份与编号合同 | `TODO` | 区分request_id、utterance_id、segment_id、experiment_step_id和clarification_id，规定生成者、唯一范围和跨记录引用，解决内部口述编号与用户实验步骤编号混用；是 `PRESENT-04` 编号分离的前置合同，须在 PRESENT-04 之前定稿 |
| `SESSION-02` | `P1` | 按 session_id 查询完整实验 | `TODO` | 尚无统一查询命令 |
| `EXPORT-01` | `P1` | 导出单次实验 Markdown/JSON | `TODO` | TTS 前建议完成第一版 |
| `EXPORT-02` | `P3` | 导出报告文档 | `TODO` | 后期白名单工具功能 |

### E. 待确认与回复协调

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `CLARIFY-01` | `P1` | PendingClarification 数据结构 | `AUTO_OK` | 单元测试通过 |
| `CLARIFY-02` | `P1` | ReplyCoordinator 登记和部分解决 | `AUTO_OK` | 单元测试通过 |
| `CLARIFY-03` | `P1` | 每个安全间隙最多一条回复 | `AUTO_OK` | main 集成测试通过，尚缺真实验收 |
| `CLARIFY-04` | `P1` | 回复带来源段号和原文 | `AUTO_OK` | main 集成测试通过，尚缺真实验收 |
| `CLARIFY-05` | `P1` | 会话结束显示遗留项 | `AUTO_OK` | 已接 main，尚缺真实验收 |
| `CLARIFY-06` | `P1` | 明确肯定答复关闭最早 ASR 确认项 | `REAL_OK` | 会话 `20260806_203255` 已用真实语音关闭第 1 段确认项 |
| `CLARIFY-07` | `P1` | 否定并提供修正内容 | `TODO` | 当前“不是”不会自动关闭 |
| `CLARIFY-08` | `P2` | 问题优先级、合并、过期 | `TODO` | 当前主要按最早段号 |
| `CLARIFY-09` | `P1` | 待确认项支持暂缓、回看和稳定编号 | `AUTO_OK` | 新增9项生命周期测试；全量118项通过；暂缓问题可被后续字段补全，尚待真实口述 |
| `CLARIFY-TARGET-01` | `P1` | 用户按问题编号指定回答目标 | `REAL_OK` | 会话20260808_185630中“问题二，是的，是水域温度60摄氏度加热10分钟”成功解决问题2；随后回看只剩问题1；全量130项基线 |
| `CLARIFY-TARGET-02` | `P2` | 用户按实验步骤或唯一主题指定回答目标 | `TODO` | 支持“第2步”“离心时间”；匹配不唯一时必须追问，不自动选择 |
| `CLARIFY-TARGET-PERSIST-01` | `P1` | 持久化编号答复与目标问题的关联 | `TODO` | 当前答复原始ASR和结构化事件已保存，target_clarification_id只随内存后台任务传递；导出前需形成可审计关联记录 |
| `COMMAND-01` | `P0` | 定义统一 InteractionCommand 与命令解析器 | `AUTO_OK` | 暂缓/回看已通过处理器接main；结束/肯定仍沿用旧入口，待后续统一迁移 |
| `COMMAND-02` | `P0` | 命令匹配忽略 SenseVoice 句尾情绪符号 | `REAL_OK` | 会话20260808_144408中“这个先跳过。😔”成功暂缓问题1，“查看待确认问题。😔”成功回看；原文保留且均未进入实验事件 |
| `COMMAND-03` | `P0` | 自然命令表达的保守兼容策略 | `AUTO_OK` | Parser新增安全前缀+后缀和自然模式；Prompt新增uncertain兜底；418项通过；已知限制：如果用户在实验台前指着步骤列表说”这个先跳过”，会被判为DEFER——目前语音交互场景下概率极低，若复现则删对应前缀即可 |
| `CLARIFY-MAIN-01` | `P1` | 暂缓和回看命令接入main | `REAL_OK` | 会话20260808_141435中准确命令各执行2次；原始ASR已保存，命令未进入实验事件 |

### F. 确认答复持久化与主流程

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `CONF-STORE-01` | `P1` | ConfirmationRecord 数据结构 | `REAL_OK` | 会话 `20260806_203255` 生成真实确认记录 |
| `CONF-STORE-02` | `P1` | ConfirmationStore JSONL 保存 | `REAL_OK` | confirmations JSONL 已保存真实肯定答复 |
| `CONF-MAIN-01` | `P1` | ASR 确认答复接入 main | `REAL_OK` | 真实语音答复已完成 prepare/save/commit |
| `CONF-MAIN-02` | `P1` | 确认成功终端反馈 | `REAL_OK` | 真实流程显示“已保存对第 1 段的确认答复” |
| `CONF-MAIN-03` | `P0` | 确认答复不作为普通实验事件 | `REAL_OK` | ASR 共 4 条、实验事件仅 3 条，确认答复只进入确认记录 |

### G. 回复时机与会话收尾

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `TIMING-01` | `P1` | LLM 完成后不必等下一段才显示 | **REAL_OK** | 显示搬到后台 worker（display 回调注入），结果算完当场打印；会话 111049/112341 验证 [统一链] 结果插空出现 |
| `TIMING-02` | `P1` | 用户正在说话时不输出/播放回复 | `TODO` | TTS 前硬性依赖 |
| `TIMING-03` | `P1` | 明确安全回复判断接口 | `TODO` | 供终端和未来 TTS 共用 |
| `CLOSING-01` | `P1` | 增加 CONFIRMING 收尾阶段 | `TODO` | 结束记录后仍可回答遗留项 |
| `CLOSING-02` | `P1` | “跳过确认/直接结束”指令 | `TODO` | 避免无法退出收尾阶段 |
| `CLOSING-03` | `P1` | 全部确认完成后进入 IDLE | `TODO` | 状态机集成测试和真实验收 |

### H. TTS 前稳定性验收

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `STABILITY-01` | `P1` | 连续至少 10 段实验口述 | `TODO` | 检查顺序、丢失、积压和延迟 |
| `STABILITY-02` | `P1` | 空响应/网络失败真实降级演练 | `TODO` | 原始数据不得丢失 |
| `STABILITY-03` | `P1` | 确认答复完整真实闭环 | `TODO` | 包含肯定、否定和遗留项 |
| `STABILITY-04` | `P1` | 会话结束总结和记录核验 | `TODO` | 结束后结果可使用 |

### H2. 用户输出与呈现策略

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `PRESENT-01` | `P1` | 定义 PresentationMessage 数据结构 | `RETIRED` | 早期探索合同帮助识别 kind/priority/target 与渠道/状态/朗读策略的边界；稳定主链改用 `PresentationIntent` 后，旧对象及10项专属测试已由 `PRESENT-LEGACY-MESSAGE-CLEANUP-01` 删除 |
| `PRESENT-02` | `P1` | 当前回答回执优先于旧后台追问 | `REAL_OK` | 会话20260808_141435中暂缓/回看回执先展示，随后才展示ASR期间完成的旧后台结果 |
| `PRESENT-03` | `P1` | 按认知负担预算组成语音消息组 | `DESIGN` | 默认最多2条、50字、1个问题；支持“回执+相关问题” |
| `PRESENT-04` | `P1` | 内部口述编号与用户实验步骤编号分离 | `TODO` | 确认答复占号导致实验步骤从2跳到4；依赖 `SESSION-IDENTITY-CONTRACT-01` 的编号合同，先定合同再改展示，避免打补丁 |
| `PRESENT-07` | `P1` | 指定编号答复完成后的明确状态回执 | `TODO` | CLARIFY-TARGET-01已能正确路由，但后台完成后暂未直接显示“问题N已解决/仍缺少哪些字段”；当前可用回看命令核验 |
| `PRESENT-05` | `P1` | 用户输出与 debug 日志分离 | `TODO` | 状态、路径、token、耗时默认不展示/不朗读 |
| `PRESENT-06` | `P1` | 输出顺序真实验收 | `TODO` | 先确认回执，再在后续安全间隙提出新问题 |
| `PRESENT-INTEGRATE-01` | `P1` | 建立会话级呈现系统与单一输出权 | `AUTO_OK` | v2 设计已确认；A-1 不可变 `PresentationIntent`；A-2a 记录回执文案目录；A-2b 追问/回答/确认/暂缓文案 + 字段名中文化（修 UX-07）；A-3 `TerminalRenderer`（封装 ui_mode + review 多行文案）；A-4 投影层（业务事实→Intent，补 answer 结构化字段）。**子步 A 全部完成**。专项 projection 13 + copy 29 + renderer 5 + intent 7、正式全量 544 项通过。尚未接 main 或 Coordinator；下一小步 **子步 B**（Coordinator + pump + 接线 + 真实验收）。B-1 Coordinator 纯逻辑、B-2 Renderer 协议 + 有状态队列 + pump、B-3a 后台接线、B-3b DEBUG 分流、B-3c 主循环用户消息→pump 已完成；**main.py 零 print 残留，达成"单一输出入口 + 后台不直显 + 旧 print 已删 + 无开关 + 测试绿"前 5 条，第 6 条真机无退化待 B-4 真实验收**。子步 B 完成标准见 PRESENT_DESIGN.md §10。 |
| `PRESENT-STYLE-01` | `P2` | 分离消息语义语调与具体前端/TTS样式 | `DESIGN` | 消息只表达kind/priority/channel/speech policy及可选抽象语调；颜色布局、音色、语速和具体情感参数由适配器决定 |

### H3. 系统故障与实验安全

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `SAFETY-01` | `P1` | 定义系统故障分类和严重程度 | `TODO` | 区分问题类型、严重程度、消息优先级；先覆盖可由程序确定的故障。与 `SAFETY-TYPES-01` 的实验风险分类不同域：本项管“系统可靠性故障”（存储不可写/音频失败），后者管“实验操作安全”（高温/危险化学品），两者不得共用一套枚举 |
| `SAFETY-02` | `P1` | 将确定的存储/音频故障转换为用户消息 | `TODO` | 存储不可写等关键故障必须明确提醒；可降级故障不得冒充严重危险 |
| `SAFETY-03` | `P3` | 确定 Demo 实验后建立风险规则白名单 | `TODO` | Demo、SOP 和术语尚未确定，当前不提前绑定具体实验风险规则。规则集定义已细化到 I 节 `SAFETY-RULES-01`，本项仅作“Demo 实验定型”的前置提醒，不再重复定义规则 |
| `SAFETY-04` | `P2` | 实验风险提示的证据等级与确认流程 | `TODO` | 区分 confirmed、suspected、unknown；疑似 ASR 错词不得直接判定危险 |

### H4. 跨模块集成与个人能力拓展

这一组由A维护总体证据，但接口定稿和真实联调必须由相关队友共同确认。它们是“学习更多但不包揽”
的主要入口，不能提前打断ASR和IntentRouter主线。

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `ARCH-01` | `P2` | 维护端到端数据流和模块边界图 | `TODO` | INTENT-02后更新；必须标出数据所有者、失败边界和适配器，不画成所有模块互相调用 |
| `CONTRACT-01` | `P2` | 设备只读查询请求/响应/错误契约 | `TODO` | A/B共同确认；统一equipment_id及带时区时间；契约变更需版本记录 |
| `PLANNING-CLIENT-01` | `P2` | PlanningClient接口和Fake实现 | `TODO` | CONTRACT-01后；A可独立单测，不依赖B服务或数据库 |
| `CONTRACT-TEST-01` | `P2` | 跨仓库JSON契约测试 | `TODO` | Fake和真实服务对同一正常/错误样例给出兼容结构 |
| `PLANNING-CLIENT-02` | `P2` | 只读设备查询HTTP适配器 | `TODO` | 超时、服务不可用和非法响应不得破坏实验原始记录 |
| `E2E-QUERY-01` | `P2` | 语音查询设备端到端验收 | `TODO` | ASR→IntentRouter→PlanningClient→消息；有空/冲突/缺时间/服务失败四类路径 |
| `OBS-01` | `P2` | 跨模块request_id和关键耗时 | `TODO` | 调试信息进入开发日志，不默认显示或朗读给用户 |
| `E2E-DEMO-01` | `P2` | 2～3分钟Demo脚本和验收表 | `TODO` | 三人共同；连续跑通至少3次并包含断网或服务失败降级 |

### I. 查询识别、安全警示与知识库增强

这一组分两阶段推进：**Phase 1 铺类型和扩展点**（纯合同，不改行为，P1），**Phase 2 接真实能力**（知识库检索、安全规则引擎，P2）。

#### I.1 Phase 1：类型合同 + 扩展点准备（P1，INTENT-02 清理后立即启动）

```
准备阶段的目标：
  1. 三组类型合同就位（query / safety / knowledge）
  2. unified 管线能识别 QUERY 类输入（第 4 分支）
  3. 分派层能把 QUERY 路由到 KNOWLEDGE_BASE 目标
  4. 检索证据、用户画像与实验事实保持独立合同
  5. 新能力开关默认关闭，并对非法组合做配置校验
  6. ~22 项新测试 + 现有测试数据更新 → 全量 ~444 项通过
  7. main.py 行为完全不变（feature flag 全关 = 与今天一模一样）
```

**Phase 1a — 纯新文件（技术上独立，但按当前优先级在 P0 清理后执行）**

| ID | 优先级 | 任务 | 为什么现在能做 |
|---|---|---|---|
| `QUERY-TYPES-01` | `P1` | `src/core/query_types.py`：QuerySubKind enum、QueryUnderstanding、QueryAnswerResult | 全新文件，不被任何现有代码 import |
| `SAFETY-TYPES-01` | `P1` | `src/core/safety_check.py`：SafetyConcernType(7种)、SafetyCheckDisposition(3级)、SafetyConcern、SafetyCheckResult、SafetyCheck Protocol + FakeSafetyCheck | 同上 |
| `KNOWLEDGE-PROTOCOLS-01` | `P1` | `src/knowledge/` 包：KnowledgeBase Protocol、UserProfile、KnowledgeHint、KnowledgeBaseResult、FakeKnowledgeBase | 只依赖 `QUERY-TYPES-01.QuerySubKind` |
| `QUERY-RECOGNIZE-TEST-01` | `P1` | `tests/test_query_recognition.py` ~8 项 | 只测新类型，不碰现有测试 |
| `SAFETY-CHECK-TEST-01` | `P1` | `tests/test_safety_check.py` ~8 项 | 同上 |
| `KNOWLEDGE-PROTOCOLS-TEST-01` | `P1` | `tests/test_knowledge_protocols.py` ~6 项 | 同上 |

> 这 6 个做完：类型合同和 Fake 就位，并以恢复后的实际测试数作为新基线；不预先污染 ExperimentEntities 或 PendingClarification。

检索命中（标准术语、SOP 来源、置信度）应保存在独立 `KnowledgeHit` 或
`KnowledgeEvidence` 中，而不是加入 `ExperimentEntities`；追问的知识依据应通过动作证据关联，
而不是加入 `PendingClarification` 生命周期对象。只有真实用例证明字段属于该领域对象后才扩展 schema。

**Phase 1b — 扩展现有管线，清理完后做（依赖 INTENT-02-CLEANUP-VERIFY-01）**

| ID | 优先级 | 任务 | 为什么必须等清理 |
|---|---|---|---|
| `UNIFIED-QUERY-01` | `P1` | `UnifiedInputKind` 加 `QUERY`；`UnifiedUnderstandingResult` 四选一；`TOP_LEVEL_FIELDS` 加 `"query"`；`parse_unified_understanding` 加 query 解析；`unified_prompts.py` 加 query 规则 | 所有测试数据 dict 需同步加 `"query": None`——8 个测试文件、20+ 处 fixture。清理后管线干净，改一处只影响一处 |
| `DISPATCH-QUERY-01` | `P1` | `UnifiedDispatchDestination` 加 `KNOWLEDGE_BASE`；`UnifiedDispatchPermission` 加 `FORWARD_QUERY_TO_KNOWLEDGE`；`UnifiedDispatchPlanner.plan()` 加 QUERY→KNOWLEDGE_BASE 分支 | 依赖 `UNIFIED-QUERY-01`；枚举完整性测试需同步更新 |
| `BYPASS-QUERY-01` | `P1` | `UnifiedAcceptanceBypass.inspect()` 加 `KNOWLEDGE_BASE` 分支（当前行为同 ABSTENTION：不产生实验分析，NO_ACTION） | 依赖 `DISPATCH-QUERY-01` |
| `CONFIG-QUERY-SAFETY-01` | `P1` | 新能力开关默认关闭；若采用 observe/execute 双开关，配置层必须验证依赖关系 | 在旧 shadow flag 删除后设计，避免复制当前非法组合问题 |
| `RAG-CONTEXT-CONTRACT-01` | `P1` | 定义独立 EnrichedContext（recent_events + user_profile + knowledge_hits），由适配器转换为 prompt 输入 | 不直接向现有 SessionContext 塞空字典；先固定数据所有者和信任边界 |

> 这 5 个做完：管线能识别和路由 QUERY 类输入，feature flag 关闭时行为与今天无差异。

**Phase 1 完成标志**：全量 ~444 项测试通过 + 启动 main.py 行为与修改前完全一致。

#### I.2 Phase 2：真实能力接入（P2，PRESENT 阶段稳定后）

| ID | 优先级 | 前置依赖 | 任务 |
|---|---|---|---|
| `SAFETY-INTEGRATE-01` | `P2` | Phase 1 + `SAFETY-01/02` | `ExperimentCandidateAcceptor` 前插入 `SafetyCheck.check()`；有警告走 `MessageKind.SAFETY_ALERT` |
| `SAFETY-RULES-01` | `P2` | `SAFETY-INTEGRATE-01` | 定义 Demo 实验危险操作规则集（高温阈值、危险化学品列表等） |
| `SAFETY-E2E-01` | `P2` | `SAFETY-RULES-01` | 真实口述触发警告；WARN_BUT_PROCEED / BLOCK_UNTIL_ACKNOWLEDGED 两类路径验收 |
| `RAG-CONTEXT-01` | `P2` | Phase 1 + `RAG-CONTEXT-CONTRACT-01` | 将真实 user_profile + knowledge_hits 组装为 EnrichedContext，再转换为 prompt 输入 |
| `RAG-RETRIEVE-01` | `P2` | `RAG-CONTEXT-01` | 实现真实 KnowledgeBase（SOP 文档索引 + 设备状态查询） |
| `QUERY-ANSWER-01` | `P2` | `RAG-RETRIEVE-01` | KNOWLEDGE_BASE 目标接真实 KnowledgeBase.search() → QueryAnswerResult → projection → PresentationIntent |
| `QUERY-E2E-01` | `P2` | `QUERY-ANSWER-01` | 真实 ASR→统一理解→知识库→回答；设备占用/实验时间/协议参考/通用知识四类验收 |

#### I.3 为什么不倒过来（先接能力再补类型）

```text
当前管线：experiment / control / uncertain 三选一
         ↓
想加 QUERY：必须先让 UnifiedInputKind 接受第 4 种值
         ↓
不先定义 QueryUnderstanding：parse 函数不知道 query 分支长什么样
         ↓
不先定 QuerySubKind：LLM prompt 不知道查询有几种子类型
         ↓
不先铺 KnowledgeBase Protocol：query 到了 KNOWLEDGE_BASE 目标后不知道调用什么接口

结论：类型合同是管线的"地基"。Phase 1 定了 vocabulary，
     Phase 2 只是"往 vocabulary 里填真实实现"，不用再回头改合同。
```

#### I.4 优先级总览

```text
P0 (当前): ENV-RECOVERY-02 → MAIN 三项一致性修复 → INTENT-02-CLEANUP-* 五步
P1 (下一批):
  Phase 1a: QUERY-TYPES-01 + SAFETY-TYPES-01 + KNOWLEDGE-PROTOCOLS-01 + 三项测试
  Phase 1b: UNIFIED-QUERY-01 → DISPATCH-QUERY-01 → BYPASS-QUERY-01 → CONFIG + ENRICHED-CONTEXT合同
P2 (远期): SAFETY-INTEGRATE → RAG-CONTEXT → RAG-RETRIEVE → QUERY-ANSWER → E2E
P3 (TTS后): AGENT-01 多工具Agent
P3 (远期): FINE-TUNE-* 微调（LoRA）与本地推理（在 RAG Phase 2 与 TTS 之后，见第 4 节 K 组）
```

### J. TTS 与后续阶段

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `TTS-01` | `P3` | 定义 TTSClient 接口 | `TODO` | 先假客户端单测；操作签名只保留播放本质：`stop()` 打断、`is_speaking` 状态、播放生命周期回调（开始/分句结束/全部结束，供分句播放与 Live2D 口型）、失败回退；音色/语速/音量等可变选项收进可扩展的 TTSOptions 对象，不铺开成签名参数，将来加音色/克隆只扩 options 不破坏调用方 |
| `TTS-02` | `P3` | 系统 TTS 第一版 | `TODO` | 不先接 GPT-SoVITS |
| `FULL-DUPLEX-01` | `P3` | 音频会话协调合同（半双工/全双工通用） | `TODO` | 定义“播放+监听”协调接口和 Fake，半双工/全双工是同一接口的两种实现；依赖 `TTS-01` 的 TTSClient 接口；`TTS-03` 是其第一个实现 |
| `TTS-03` | `P3` | 增加 SPEAKING 状态 | `TODO` | 半双工第一个实现：走 `FULL-DUPLEX-01` 接口，播放期间暂停 KWS/VAD |
| `TTS-04` | `P3` | 分句播放、失败降级 | `TODO` | TTS 失败回退终端文本 |
| `TTS-05` | `P3` | 用户打断策略 | `TODO` | 需要状态机和音频资源管理 |
| `TTS-06` | `P3` | 唤醒提示替换为“我在，请说” | `TODO` | 系统 TTS 稳定后 |
| `TTS-07` | `P3` | web `local_tts.js` 打断后 blob URL 未回收 | `TODO` | 软问题（不影响功能，仅内存回收）：`play()` 被 `stopSpeech()` 的 `currentAudio.pause()` 打断时 `onended` 不触发，`URL.revokeObjectURL(url)`（`local_tts.js` 第34行）不执行，长会话连续 barge-in 会累积 blob 内存到页面刷新才释放；修法=在 stopSpeech 或 play 的 onpause 补 revoke |

> **全双工（full-duplex）增强组**：`FULL-DUPLEX-01` 已把“播放+监听”抽象为统一接口，
> 半双工（`TTS-03`）是全双工的第一个实现，全双工只是给同一接口加回声消除后
> “播放期间继续监听”。半双工下 `TTS-05` 的打断退化为播放分句间隙检测，
> 真正的连续打断由 `FULL-DUPLEX-02` 承担。核心难点是回声消除（AEC），高度依赖硬件/系统能力。
> 本组在真实 TTS 接入（`TTS-02`）后展开，任何一项失败都不影响半双工主链。

| `FULL-DUPLEX-02` | `P3` | 打断（barge-in）状态机 | `TODO` | SPEAKING 下检测到用户人声即停止播放并进入 LISTENING；用 Fake TTS 驱动，覆盖打断成功/失败/无说话路径 |
| `FULL-DUPLEX-03` | `P3` | 回声消除（AEC）能力探测 | `TODO` | 探测当前 Windows 环境可用 AEC（声卡硬件 AEC / 系统回声通道 / WebRTC AEC），产出可行性结论；这是全双工的“决策门”，不达标则后续走降级 |
| `FULL-DUPLEX-04` | `P3` | 播放期间 KWS/VAD 自声抑制 | `TODO` | TTS 播放时不把自己的声音误判为唤醒词或人声；覆盖播放中唤醒、播放中人声边界 |
| `FULL-DUPLEX-05` | `P3` | 真实全双工验收 | `TODO` | 真实 TTS + 真实麦克风验证回声消除、打断和不误判；连续边听边说不污染 ASR 原文 |
| `FULL-DUPLEX-06` | `P3` | 全双工降级策略 | `TODO` | 回声不达标/打断失败时自动退回半双工或提示用耳机，录音与记录不受影响 |
| `SOVITS-01` | `P3` | GPT-SoVITS HTTP 服务 | `TODO` | TTS 第一版之后；必须实现 `TTS-01` 接口，供 `SOVITS-02` 与系统 TTS 切换回退，禁止另起炉灶 |
| `SOVITS-02` | `P3` | 超时、缓存、系统 TTS 回退 | `TODO` | 外部服务失败不影响主流程 |
| `LIVE2D-01` | `P3` | Live2D 表现层接入 | `TODO` | TTS 稳定后；口型/表情依赖 `TTS-01` 的播放生命周期回调，不在表现层另做 TTS 驱动 |
| `AGENT-01` | `P3` | 白名单计时器/提醒/查询/导出 | `TODO` | TTS 与记录闭环后 |

### K. 微调（LoRA）与本地推理（远期规划）

> **登记背景（2026-08-16，用户提出"项目成熟后如何加入模型微调"）**：定位澄清——三条路线
> 解决不同问题，是接力不是替代：**提示词工程**（教模型"怎么答"，零成本）→ **RAG**
> （给模型"喂资料"，管"不知道"，任务库第 I 节已规划）→ **微调/LoRA**（给模型"练肌肉"，
> 管"知道但做不对"，如输出格式不稳、术语常错）。判断口诀：模型不知道→RAG；知道但做不对
> →微调；偶尔错→继续提示词工程。
>
> **本组是路线登记，不在 PRESENT 收口清单内，不改变当前执行顺序**。最稀缺资源不是 GPU
> 而是数据：`results/` 三份 JSONL（asr_segments / experiment_events / experiment_confirmations）
> 与 `evaluation/narration_robustness/narration_plan.json`（28 段带期望标注）是现成 SFT 样本来源
> ——"ASR 转写 → 期望结构化 JSON"即为标准有监督微调样本。目标场景：统一理解输出格式稳定性
> （对应任务库 LLM 格式降级类问题，如 3.1A 看板第 23 项）。接入口已由 `LLMClient` Protocol +
> `create_llm_client` 工厂预留（见 `PROJECT_ARCHITECTURE.md` 4.2 节）。

| ID | 优先级 | 任务 | 状态 | 验收证据/备注 |
|---|---|---|---|---|
| `FINE-TUNE-DECISION-01` | `P3` | 微调适用边界与场景确认 | `TODO` | 判定"哪些问题归 RAG、哪些归微调"：输出格式不稳定/术语常错→微调；知识缺失→RAG。用现有鲁棒性旁路报告（ASR-ROBUSTNESS 缺口分布）和 LLM 格式错误记录做证据，不拍脑袋定 |
| `FINE-TUNE-DATA-AUDIT-01` | `P3` | 现有会话数据量与质量评估 | `TODO` | 统计三份 JSONL 可清洗出多少对"ASR转写→期望结构化JSON"样本；只计用户确认过/最终采纳的记录，降级 NOTE、误识别段剔除或标注；产出数量与占比结论，决定是否值得做微调 |
| `FINE-TUNE-DATA-CONTRACT-01` | `P3` | 微调数据集清洗合同 | `TODO` | 定义清洗规则与 alpaca 格式输出（instruction 复用 `unified_prompts.py`；input=ASR 转写；output=期望结构化 JSON）；严格 schema + 测试拒绝脏样本；不覆盖、不回写原始 JSONL（沿用"先存原始数据，后推断"原则） |
| `FINE-TUNE-TRAIN-01` | `P3` | LoRA 训练闭环 | `TODO` | 选开源可下载权重模型（候选 Qwen2.5-7B-Instruct）+ LLaMA-Factory/Unsloth；LoRA 低秩适配器（r/alpha/epoch 默认参数起步），产物是几十 MB adapter 而非整个模型；训练/数据文件不入仓库 |
| `FINE-TUNE-EVAL-01` | `P3` | 微调前后对照评估 | `TODO` | 复用 `narration_plan.json` 28 段语料跑"微调前 vs 微调后"报告 + 现有合同测试；标准=意图准确率/格式合规率提升且不破坏原有能力（与 `ASR-CMD-02-POSTPROCESS-01` 同一方法论：单变量对照、保留原文、量化回退） |
| `FINE-TUNE-INTEGRATE-01` | `P3` | vLLM 本地推理接入 | `TODO` | vLLM 起 OpenAI 兼容服务（/v1/chat/completions）；`create_llm_client` 工厂 + `LLMClient` Protocol 增加配置项指向本地地址，下游零改动；失败降级沿用现有 `UnavailableLLMClient` 策略，不得破坏主流程 |

## 5. TTS 开始条件

以下任务至少达到指定状态后，才开始 `TTS-01`：

| 前置任务 | 最低状态 |
|---|---|
| `CONF-STORE-01/02` | `AUTO_OK` |
| `CONF-MAIN-01/02/03` | `REAL_OK` |
| `TIMING-01/02/03` | `REAL_OK` |
| `CLOSING-01/02/03` | `REAL_OK` |
| `CLARIFY-07` | 至少 `AUTO_OK` |
| `LLM-10` | 至少 `AUTO_OK` |
| `STABILITY-01` | `REAL_OK` |
| `STABILITY-03` | `REAL_OK` |
| `PRESENT-01/02/03/04/05/06` | `REAL_OK` |
| `SESSION-02` | 至少 `AUTO_OK` |
| `EXPORT-01` | 至少 `AUTO_OK`，并完成一次真实会话导出验收 |
| `SAFETY-01/02` | 至少 `AUTO_OK` |

### TTS 前的功能推进顺序

第一版系统 TTS 不应早于输入可靠性、自然控制、输出协调和实验记录闭环。详细执行顺序以
第3.1～3.2节的当前看板和五阶段路线为准，概括如下：

```text
固定语料与ASR基线
→ 自然意图与风险路由
→ 输出协调和确认收尾
→ 会话总结、SessionRecord与Markdown/JSON导出
→ 系统TTS
→ 全双工增强（可选，回声消除能力达标后）
→ GPT-SoVITS、Live2D与Word/PDF美化
```

TTS 前至少完成 `SessionRecord` 聚合和 Markdown/JSON 第一版导出，用来证明：

```text
口述 → 识别 → 结构化 → 确认 → 总结 → 可用记录
```

Word/PDF 属于表现层增强，可以在系统 TTS 之后完成。

## 6. 维护日志

| 日期 | 变更 | 自动测试 | 真实验收 | 下一项 |
|---|---|---:|---|---|
| 2026-08-06 | 建立任务总表；整理当前完成度 | 65 tests OK | 使用既有会话证据 | `CONF-STORE-01` |
| 2026-08-06 | 建立 ConfirmationRecord 与 ConfirmationStore | 73 tests OK | 未进行真实写入验收 | `CONF-MAIN-01` |
| 2026-08-06 | 明确肯定答复以两阶段方式接入 main | 79 tests OK | 等待真实口述与三份JSONL核验 | `CONF-MAIN-01/02/03` |
| 2026-08-06 | 真实验收发现实验专业词错词较多 | 未改代码 | 当前 SenseVoiceSmall 未配置专业词增强 | 先完成确认闭环验收，再做 `ASR-03` |
| 2026-08-06 | 会话203255发现用户对话、状态和调试输出混杂 | 未改业务代码 | 确认回执被新追问插队，实验步骤编号跳号 | 先定义 `PRESENT-01` |
| 2026-08-06 | 核验会话203255的三类 JSONL 并确定输出分层策略 | 79 tests OK | 4 条 ASR、3 条实验事件、1 条确认记录；确认项已解决 | `PRESENT-01` |
| 2026-08-06 | 新增统一展示消息协议和语音认知负担预算 | 新增8项单测通过；当前代理环境无法启动项目venv完成全量回归 | 未接入main，不需要真实口述 | 验收 `PRESENT-01` 后做问题暂缓生命周期 |
| 2026-08-06 | 固定 TTS 前的数据闭环顺序，并登记安全任务和新问题维护规则 | 未改业务代码 | 不需要真实验收 | 先完成 `PRESENT-01` 自动回归验收 |
| 2026-08-06 | 补登记用户指定待确认问题能力 | 未改业务代码 | 不需要真实验收 | `CLARIFY-09` 后依次完成 `CLARIFY-TARGET-01/02` |
| 2026-08-06 | 固定命令、问题状态、消息调度、屏幕和TTS职责边界 | 未改业务代码 | 不需要真实验收 | PRESENT验收后新增统一命令解析器 |
| 2026-08-06 | 澄清领域记录、展示消息和输出适配器边界 | 10项协议单测通过；全量回归仍待项目venv | 未接main，不需要真实口述 | 完成PRESENT-01全量回归后进入COMMAND-01 |
| 2026-08-07 | 新增统一交互命令协议和保守解析器 | 新增15项单测通过；消息协议、命令、协调器共40项通过 | 未接main，不需要真实口述 | 项目venv全量回归后进入CLARIFY-09 |
| 2026-08-07 | 执行COMMAND-01验收并检查全量环境 | 相关40项全部通过；全量发现71项但7个测试模块导入失败 | 主venv失效；py314环境缺dotenv且ffmpeg权限失败 | 先修复统一测试环境，再确认全量基线 |
| 2026-08-07 | 完成待确认项暂缓生命周期和稳定编号 | 新增9项测试通过；命令、消息、生命周期、协调器共49项通过 | 未接main，不需要真实口述 | 环境恢复后接入main的暂缓/回看闭环 |
| 2026-08-07 | 暂缓/回看命令接入main并调整当前回复顺序 | 处理器新增5项测试；相关核心54项通过；main语法检查通过 | 待真实口述“这个先跳过/查看待确认问题” | 真实验收后做按问题编号回答 |
| 2026-08-08 | 恢复统一Python 3.11.9测试和运行环境 | 全量118项通过；src.main导入成功 | VAD、KWS、SenseVoice和FSMN-VAD模型加载成功 | 真实口述验收暂缓/回看闭环 |
| 2026-08-08 | 验收暂缓/回看并兼容SenseVoice情绪后缀 | 会话20260808_141435；全量121项通过 | 准确命令和回执顺序通过；带😔命令曾误入事件，现已修复待复验；模糊错词仍不猜测 | 真实口述复验 `COMMAND-02` |
| 2026-08-08 | 真实复验SenseVoice句尾情绪命令 | 会话20260808_144408；沿用全量121项基线 | 带😔的暂缓和回看均成功，原文保留且未进入事件；发现3种自然命令表达误入事件，登记COMMAND-03 | `CLARIFY-TARGET-01` |
| 2026-08-08 | 按稳定问题编号路由同句答案并接入main | 新增6项测试；全量127项通过；main语法检查通过 | 编号不存在/无答案不调用LLM；同字段多问题只更新目标；目标关联尚未独立持久化 | 真实口述验收 `CLARIFY-TARGET-01` |
| 2026-08-08 | 首次真实验收编号回答并修复混合确认死循环 | 会话20260808_183942；新增3项测试；全量130项通过 | LLM已提取水浴/60摄氏度/10分钟，但旧确认标志未关闭；现用明确肯定元数据关闭目标确认且排除疑问句；通用命令误识别登记ASR-CMD-01 | 复验目标回答后立即做命令ASR稳定性 |
| 2026-08-08 | 复验编号回答并确定自然语音演进方向 | 会话20260808_185630；沿用全量130项基线 | 问题2成功解决且问题1保留；“看待确认问题”误入事件并生成问题3，证明应先建命令语料和ASR基线 | `ASR-CMD-01` 先建语料与基线 |
| 2026-08-08 | 收束自然交互、意图路由和消息表现层设计 | 未改业务代码；全量基线仍为130项 | 明确混合路线：ASR尽量准确、低风险意图语义容错、高风险命令确认；消息协议已定义但尚未接main | 明日按 `NEXT_SESSION_HANDOFF_2026-08-09.md` 开始ASR-CMD-01 |
| 2026-08-09 | 建立控制命令固定语料、清单校验器和静态基线报告 | 新增5项测试；全量135项通过 | 使用4次历史真实会话的14条WAV；2条原话因证据不足保持needs_user_label，未自行猜测 | 试听标注2条音频并复跑基线，随后进入ASR-CMD-02 |
| 2026-08-09 | 重整近期执行看板和TTS前五阶段路线 | 未改业务代码；沿用135项基线 | 不需要真实验收；保留完整任务库和历史证据 | `ASR-CMD-REC-01` 独立语料采集器 |
| 2026-08-09 | 用户回听并补齐两条历史音频标签 | 静态基线复跑成功：文本8/14、意图9/14、漏触发5、误触发0 | 两条提示均为“这个先跳过”，但WAV实际只录入“个先跳过”；已分开保存prompt与reference，未把截音归咎于ASR | `ASR-CMD-REC-01` 需改善句首截音并采集24条新语料 |
| 2026-08-09 | 人工复核新会话的6条歧义音频 | 未改业务代码；正式14条基线不变 | “查看/跳过”2条确认句首截断；“记录/移液枪/放入离心机”音频完整但ASR错误；第1条再次确认WAV与ASR均为“那我再问”，属于音频内容与提示稿不同 | 采集器解决句首保留并增加录后确认，再用标准流程重录 |
| 2026-08-09 | 定义控制命令语料采集数据结构 | 新增11项测试；全量146项通过 | 未接真实麦克风；不需要真实录音验收 | `ASR-CMD-REC-STORE-01` 追加式JSONL存储 |
| 2026-08-09 | 根据三人分工讨论补充个人范围和跨模块学习任务 | 未改业务代码；沿用146项基线 | 分工尚待团队确认；明确A主责语音会话，同时通过契约、客户端、集成和E2E学习整体工程，不接管B数据库或C前端 | 当前仍先做`ASR-CMD-REC-STORE-01`；INTENT-02后启动CONTRACT-01 |
| 2026-08-09 | 完成语料录音尝试的原子JSONL存储 | 新增6项存储测试；专项17项、全量152项通过 | 未接麦克风；不需要真实录音验收 | `AUDIO-PREROLL-01` 先实现纯PreRollBuffer |
| 2026-08-09 | 完成纯音频PreRollBuffer | 新增10项测试；全量162项通过 | 未接麦克风和现有VAD，不代表句首问题已真实解决 | `AUDIO-PREROLL-INTEGRATE-01` 假边界组装测试 |
| 2026-08-09 | 完成预缓冲与VAD语音段的安全组装契约 | 新增11项测试；全量173项通过 | 未接VadAudioRecorder和真实麦克风；明确重叠才去重，声明不一致立即失败；确认Sherpa SpeechSegment提供start | `AUDIO-PREROLL-RECORDER-01` 假流时间线接入 |
| 2026-08-09 | 为预缓冲增加录音会话内的绝对采样时间线 | 新增7项测试；全量180项通过 | 未接VadAudioRecorder；PreRollSnapshot已能表达[start,end)，溢出和clear行为明确 | 继续`AUDIO-PREROLL-RECORDER-01`假流接入 |
| 2026-08-09 | 将句首预缓冲按Sherpa采样时间线接入VadAudioRecorder | 时间线对齐7项、录音器4项；全量191项通过 | 使用假音频流/假VAD验收；尚未证明真实设备上的句首完整性 | `AUDIO-PREROLL-REAL-01`真实WAV回听 |
| 2026-08-09 | 为当前看板、暂缓项、学习型任务和任务总表增加P0～P3优先级 | 文档结构检查通过；沿用191项代码测试基线 | 不涉及真实功能验收 | 仍为`P0 AUDIO-PREROLL-REAL-01`真实WAV回听 |
| 2026-08-09 | 建立真实句首验收工具并严格分开人工回听与ASR阶段 | 新增4项测试；验收工具+录音器专项8项、全量195项通过 | 等待用户真实录制9条并标记完整/截断/重复 | `P0 AUDIO-PREROLL-REAL-01`真实WAV回听 |
| 2026-08-09 | 首轮句首真实验收失败并修复麦克风就绪提示时机 | 新增1项顺序测试；专项9项、全量196项通过 | 9个最终样本中5完整、4截断、0重复；另保留1次人工重录；定位提示早于InputStream打开 | 第二轮同样9句复验，通过后再运行ASR和提交GitHub |
| 2026-08-09 | 用户暂不方便录音，保留真实复验并完成通用语料采集协调器 | 新增7项测试；相关28项、全量203项通过 | 未新增真实录音；首轮失败证据和待复验状态完整保留 | `P0 ASR-CMD-REC-PROMPTS-01`提示稿计划与断点恢复 |
| 2026-08-09 | 完成版本化24条控制语料计划和断点恢复规则 | 新增7项测试；相关18项、全量210项通过 | 不需要真实录音；专项9条脚本已改为从JSON计划加载 | `P0 ASR-CMD-REC-CLI-01`正式独立采集入口 |
| 2026-08-09 | 完成正式独立控制语料采集入口 | 新增5项会话测试；--status烟雾测试通过；全量215项通过 | 未打开真实麦克风；真实24条采集按用户条件后推 | `P0 ASR-CMD-02-LANGUAGE-01`既有14条WAV中文参数对照 |
| 2026-08-09 | 建立SenseVoice固定中文参数对照工具 | 新增3项比较测试，连同静态基线共8项先在3.14纯逻辑环境通过 | 已从当前安装源码确认支持`zh`；当时将沙箱拒绝执行误判为`.venv`目标消失，下一行已纠正 | 复核3.11环境并运行语言对照脚本 |
| 2026-08-09 | 纠正环境误判并完成固定中文参数真实对照 | Python3.11全量218项通过；比较工具8项通过 | `.venv`始终正常，先前为沙箱执行限制；14条WAV结果为auto文本8/14、意图9/14，zh文本8/14、意图10/14，但存在文本回退 | 先做错误归因和`INTENT-01`，热词后推 |
| 2026-08-09 | 定义统一意图风险与执行边界 | 新增7项专项测试；全量225项通过 | 纯策略层不需要麦克风；未接main且未启用语义或LLM候选 | `P0 INTENT-02`第一步连接精确解析与策略决策 |
| 2026-08-09 | 完成精确IntentRouter | 新增7项路由测试；路由/策略/解析器相关30项、全量232项通过 | 不需要真实麦克风；自然表达仍保守返回normal；未接协调器和main | `P0 INTENT-02-SEMANTIC-01`第一批本地自然表达候选 |
| 2026-08-09 | 定义LLM意图分类接口与严格候选结构 | 新增10项专项测试；全量242项通过 | Fake实现不调用外部服务；模型候选无执行权，非法/越权JSON被拒绝 | `P0 INTENT-02-CLASSIFIER-ROUTE-01`先用Fake接路由 |
| 2026-08-09 | FakeIntentClassifier接入精确路由与风险策略 | 新增6项集成测试；全量248项通过 | 无网络和真实LLM；精确优先、自然查看、高风险结束、指定答复、普通记录和超时降级均已验证；尚未调用ReplyCoordinator | `P0 INTENT-02-LLM-01`适配器与严格提示词 |
| 2026-08-09 | 增加模型弃权状态和严格意图提示词合同 | 提示词2项、意图相关27项、全量252项通过 | 未调用真实LLM；uncertain安全降级且不执行控制动作；动态输入以不可信JSON传递 | `P0 INTENT-02-LLM-ADAPTER-01`Fake客户端适配器 |
| 2026-08-09 | 实现LLMIntentClassifier适配器 | 新增5项适配器测试；全量257项通过 | Fake LLMClient，无网络；提示词传递、matched/uncertain、非法响应和客户端异常已覆盖 | `P0 INTENT-02-LLM-INTEGRATION-01`模块整链路 |
| 2026-08-09 | 完成Fake LLM意图模块整链路 | 新增7项模块集成测试；全量264项通过 | 无网络；从Fake客户端到风险出口的七类分支全部通过，未接main和ReplyCoordinator | `P0 INTENT-02-LLM-REAL-01`独立DeepSeek烟雾与延迟 |
| 2026-08-09 | 建立并完成真实DeepSeek意图烟雾 | 脚本结构及指标测试新增2项；全量266项通过 | 固定5条非敏感文本5/5符合预期；均1次请求；1.700～1.884秒，平均约1.808秒；高风险结束只请求确认 | `P0 INTENT-02-ARCH-01`先解决两次串行调用取舍 |
| 2026-08-09 | 对比独立两次与统一一次LLM理解 | 新增3项统一响应合同测试；全量269项通过；比较脚本可保留完整配对并记录失败轮次 | 首次统一输出因追问字段不一致被严格拒绝后补规则；有效配对：独立5.809/5.621秒，统一10.980冷/2.636热；后续统一请求两次遇SSL断连，未伪造完整均值 | 采用精确快速路径＋统一理解方向，先做`INTENT-02-UNIFIED-CONTRACT-01` |
| 2026-08-09 | 正式化统一输入理解数据合同 | 新增7项专项测试；Python3.11全量276项通过 | 三分支显式互斥；模型不能覆盖raw_text、夹带未选分支或把uncertain伪装成control；网络/格式失败边界为未分类NOTE且无控制候选 | 下一轮单独定义正式统一提示词与Processor，仍不接main |
| 2026-08-09 | 正式统一Prompt与Processor通过Fake验收 | 合同与Processor相关15项、Python3.11全量284项通过 | 动态上下文作为不可信JSON发送；三类合法输出严格解析；格式/网络失败保留原文和指标并降级为NOTE，不产生控制候选 | `INTENT-02-UNIFIED-REAL-01`固定非敏感文本真实烟雾，仍不接main |
| 2026-08-09 | 正式统一理解完成真实DeepSeek烟雾 | 新增2项脚本测试；Python3.11全量286项通过 | 首轮4/5，实验实体数值类型漂移被合同拒绝；修正Prompt后5/5，均1次成功、1.614～2.441秒；原始响应未打印/保存 | `INTENT-02-UNIFIED-ROUTE-01`先做精确快速路径＋统一理解Fake模块组合 |
| 2026-08-09 | 组合精确快速路径与正式统一理解 | 新增7项Fake模块集成测试；Python3.11全量293项通过 | 精确控制零LLM调用；未命中一次统一理解；所有LLM控制候选继续经过风险策略；不确定和失败不执行控制 | `INTENT-02-UNIFIED-DISPATCH-01`先定义安全分派合同，不直接改main |
| 2026-08-09 | 完成24条控制命令真实语料采集 | 24/24 accepted；31次尝试；31个WAV全部存在 | 7次重录请求作为失败证据保留；断点恢复只展示3条未接受样本，补录后每个样本恰有一条accepted | `ASR-CMD-01`后续使用这批固定WAV生成可重复的新基线；音频不上传GitHub |
| 2026-08-09 | 生成24条新语料真实ASR基线 | 新增4项Fake测试；Python3.11全量297项通过；同参数两次真实运行汇总一致 | 文本13/24、精确规则意图11/24、控制漏触发13、误触发0；13条漏触发全部由精确规则不覆盖自然表达造成，ASR额外意图漏触发0 | 保留统一意图理解路线；专业词“移液枪/水浴/滴定管”等再进入单变量ASR增强对照 |
| 2026-08-10 | 完成专业词后处理候选对照 | 新增4项Fake测试；Python3.11全量301项通过；24条真实保存文本完成对照 | SenseVoice不支持模型级hotword，任务BLOCKED；后处理候选术语0/4→4/4、文本13/24→16/24、零回退，原文未覆盖 | 不接main；回到`INTENT-02-UNIFIED-DISPATCH-01`安全分派合同 |
| 2026-08-10 | 新建热词模型候选验证任务 | 仅更新任务合同；沿用全量301项基线 | 新任务`ASR-CMD-02-MODEL-CANDIDATE-01`定义能力探针、四组同源对照、指标与独立语音复验门槛；不把可接收参数误当成模型已消费参数 | 当前唯一主线仍为`INTENT-02-UNIFIED-DISPATCH-01`；候选验证后续独立执行，不换模型、不接main |
| 2026-08-10 | 完成模型无关ASR后端合同与默认SenseVoice适配 | 新增7项专项、ASR下游38项、Python3.11全量308项通过；新工厂真实识别18.072秒固定WAV，识别耗时1.922秒 | main和真实脚本改由工厂创建后端；统一ASRResult及原始模型文本不变；未知后端提前失败；模型缓存仍在本机且未进入仓库 | `ASR-CMD-02-MODEL-CANDIDATE-01`后续只需新增候选适配器；当前正式主线仍回到`INTENT-02-UNIFIED-DISPATCH-01` |
| 2026-08-10 | 新建ASR与LLM原始证据命名合同任务 | 仅更新任务合同；沿用全量308项基线 | `ASR-EVIDENCE-CONTRACT-01`明确五层命名、不可覆盖边界和旧JSONL兼容迁移要求；本轮未直接重命名生产字段 | 先完成`INTENT-02-UNIFIED-DISPATCH-01`；随后在固定WAV主链路集成前实施证据合同 |
| 2026-08-10 | 完成ASR证据schema v2与历史只读兼容 | 新增10项合同测试；专项17项、下游47项、Python3.11全量318项通过 | 182条历史v1记录可读且SHA-256不变；真实18.072秒WAV生成v2，模型原始文本与忠实转写均非空且不同，识别1.482秒 | 回到`INTENT-02-UNIFIED-DISPATCH-01`；之后固定WAV主链路只传`asr_transcript`，不传模型标签或纠错候选 |
| 2026-08-10 | 完成统一路由结果安全分派合同 | 新增10项Planner专项、4项Router→Planner Fake集成；相关21项、Python3.11全量332项通过 | 纯合同不需要真实麦克风或外部LLM；六类目标及最小权限已固定，分派器没有执行依赖 | `INTENT-02-UNIFIED-DISPATCH-INTEGRATION-01`先做固定输入旁路可观察链路，仍不执行状态写入 |
| 2026-08-10 | 完成固定文本统一路由安全分派旁路 | 新增6项旁路专项；Python3.11全量338项通过；五类固定脚本烟雾输出符合预期 | Fake ASR/Processor，不代表真实模型效果；报告不含模型原始文本且没有执行依赖 | `INTENT-02-UNIFIED-DISPATCH-WAV-01`使用固定WAV和真实ASR/LLM做旁路验收，仍不接main |
| 2026-08-10 | 按教学约定整理累计工作区和交接文档 | Python3.11全量392项重新运行通过；compileall与git diff --check通过 | 当前仍在main，origin仍指向Kyra25906/asr_demo；20个已跟踪文件修改及30个新增代码/脚本/测试文件均为累计工作，未删除或提交；.env、真实录音、results、模型和venv保持忽略 | 下一项仍为`INTENT-02-UNIFIED-PROMPT-MISSING-FIELDS-01`；提交总仓前先确认远程、新建非main分支并按能力拆分提交 |
| 2026-08-11 | 完成统一Prompt缺失字段能力对齐 | Python3.11全量392项通过；1项Prompt合同关键词测试新增 | 真实DeepSeek以"将溶液加热。"复验：missing_fields=['temperature','duration']、should_ask_follow_up=True、follow_up_question="加热到什么温度？需要加热多长时间？"、降级=False、1次成功2.32秒 | 等待用户决定下一项优先级；可选`INTENT-02-REPLY-GATE-01`接入ReplyCoordinator、创建PR或真实验收pre-roll |
| 2026-08-11 | 完成ClarificationAction→ReplyCoordinator执行器 | Python3.11全量415项通过（+23项新测试） | ReplyCoordinator新增4个原子方法；新建ClarificationExecutor覆盖7种动作类型；项目拆平消除嵌套路径问题 | 下一步可接入main.py影子位或创建PR推远程 |
| 2026-08-11 | 项目拆平+影子真实复验+推送远程 | 415项通过；推送到total/codex/asr-demo-unified-understanding | 会话`20260811_103134`影子正确输出create+('temperature','duration')；旧流程正常创建追问；keywords.txt编码修复（UTF-16 LE→UTF-8） | 下一项设为`COMMAND-03`自然控制表达兼容 |
| 2026-08-11 | 完成COMMAND-03自然控制表达兼容 | 418项通过（+3项parser/评测测试） | DEFER新增6个安全前缀+跳过后缀；REVIEW新增2条自然模式；Prompt新增uncertain兜底 | 下一项`INTENT-02-REPLY-GATE-02`ANSWER实体填充 |
| 2026-08-11 | 完成REPLY-GATE-02 ANSWER实体填充 | 422项通过 | AnswerEntityExtractor+answer_clarification；统一理解control分支supplied_entities优化 | 下一项`INTENT-02-REPLY-GATE-03`影子接入执行器 |
| 2026-08-11 | 完成REPLY-GATE-03 影子位接入执行器 | 422项通过 | 真实会话`20260811_143031`验证CREATE+ANSWER闭环；4轮真实验收修复3个bug（重复ID/cls参数/缺extractor） | 下一项：关旧ingest_analysis或处理已知问题 |
| 2026-08-12 | 关旧ingest_analysis；修复ControlUnderstanding ValueError未包装回归 | 422项通过 | display_completed_segments新增skip_ingest参数；run_experiment_session内_display包装器自动检测UNIFIED_SHADOW_EXECUTE_ENABLED；新链路活跃时旧LLM分析不再进入ReplyCoordinator | 下一项：真实验收确认无重复问题，然后进入阶段三PRESENT-INTEGRATE-01 |
| 2026-08-12 | 真实验收INTENT-02-UNIFIED-CUTOVER-01升级REAL_OK | 422项通过 | 会话`20260812_100807` 5段无重复追问，CREATE/ANSWER/REVIEW闭环，结束正常 | 下一项：进入阶段三PRESENT-INTEGRATE-01或先关旧LLM调用 |
| 2026-08-12 | 关旧SegmentProcessor重复LLM调用→REAL_OK | 422项通过 | 会话`20260812_114401`：6段全部新路径，零旧LLM；修NameError+非实验回退+answer竞态三个bug | `PRESENT-INTEGRATE-01` |
| 2026-08-12 | 登记新旧路线交接清理5个子任务 | 未改代码 | 不需要真实验收 | `INTENT-02-CLEANUP-FLAGS-01` 去标志位 |
| 2026-08-12 | 完成项目架构设计文档 + 登记查询/安全/RAG 三类未来任务 | 未改业务代码 | 不需要真实验收 | 先完成 INTENT-02 清理，再做 QUERY-TYPES-01 等类型准备 |
| 2026-08-12 | main 只读运行审计并同步 docs | `main.py` 语法通过；`.venv` 失效导致导入和全量测试 BLOCKED | 未启动麦克风、ASR或LLM；发现 flag 非法组合、状态先于证据、SessionContext 断链等风险 | `ENV-RECOVERY-02` → 三项 main 一致性修复 → INTENT-02 清理 |
| 2026-08-12 | 纠正环境误判并恢复可信自动测试基线 | 基础Python与`.venv`均3.11.9；核心依赖/main导入成功；422项1.562秒全部通过 | 未启动麦克风或真实LLM；main导入冷启动约113秒 | `MAIN-FLAG-INVARIANT-01` |
| 2026-08-13 | 完成 MAIN-FLAG-INVARIANT-01 配置组合不变量 | Python3.11 全量 427 项通过（+5 项配置测试） | config 新增 `validate_shadow_flags` 纯函数并在加载时 fail-fast 拒绝 execute=true/enabled=false；补 `.env.example` 的 `UNIFIED_SHADOW_EXECUTE_ENABLED` | `MAIN-EVIDENCE-COMMIT-01` 澄清动作证据优先提交 |
| 2026-08-13 | 完成 MAIN-EVIDENCE-COMMIT-01 澄清动作证据优先提交 | Python3.11 全量 428 项通过（+1 项测试） | observe 拆出 `pending_action` 不再执行；main 编排 persist ASR/事件 → commit 状态；证据失败时 ReplyCoordinator 状态不变 | `MAIN-SESSION-CONTEXT-01` 恢复统一链路上下文 |
| 2026-08-13 | MAIN-EVIDENCE-COMMIT-01 真实验收升级 REAL_OK | 428 项通过 | 会话 20260813_104732：4 段口述 CREATE✅ ANSWER✅ REVIEW✅ 结束✅；ASR 3 段 + 事件 1 段落盘、零重复 LLM；证据先于状态提交 | `MAIN-SESSION-CONTEXT-01` 恢复统一链路上下文 |
| 2026-08-14 | 完成 MAIN-SESSION-CONTEXT-01 恢复统一链路上下文（AUTO_OK） | Python3.11 全量 430 项通过（+2 项） | main 的 observe 传入 `session_context.as_prompt_context()`；事件落盘成功后 `add_analysis(outcome.value)`；新增 shadow 上下文透传 2 项 + 提示词 recent_context 断言 1 项；未改配置、未动麦克风/LLM | `MAIN-SESSION-CONTEXT-01` 真实会话复验 → `MAIN-RUNTIME-HARDEN-01` |
| 2026-08-14 | MAIN-SESSION-CONTEXT-01 真实验收升级 REAL_OK | 435 项通过（+5 项核验工具测试） | 会话 20260814_092200：2 段口述，结束打印"最终上下文包含 2 条事件"= 已落盘事件数；第 2 段 prompt_tokens 959→971、cached 896 不变证明前文进入提示词；结束命令未进入分段（3 录音文件仅 2 条 ASR 记录）；新增 `scripts/verify_session_context.py` 按会话核验证据 | `MAIN-RUNTIME-HARDEN-01` |
| 2026-08-14 | 完成 MAIN-RUNTIME-HARDEN-01 运行边界整理（AUTO_OK） | Python3.11 全量 443 项通过（+8 项） | 计数：`is_experiment_evidence` 属性 + main 两分支拆分；退避：`src/core/retry.py` + main 唤醒循环接线；死代码：删重复 `if not supplied_fields`；未动麦克风/LLM | `MAIN-RUNTIME-HARDEN-01` 真实口述验收 → `INTENT-02-CLEANUP-FLAGS-01` |
| 2026-08-14 | MAIN-RUNTIME-HARDEN-01 真实验收升级 REAL_OK | 443 项通过 | 会话 20260814_093515：3 段口述（实验/控制命令/实验），结束打印"共处理 3 段、提交 2 段实验口述"，控制命令不占计数；事件记录仅段 1、3（ASR 88 条 +3、事件 48 条 +2）；上下文计数 2 = 事件数 | `INTENT-02-CLEANUP-FLAGS-01` 去标志位 |
| 2026-08-14 | 完成 INTENT-02-CLEANUP-FLAGS-01 去标志位（AUTO_OK） | Python3.11 全量 438 项通过（−5 项开关测试） | 删 config 两个 flag + validate_shadow_flags + fail-fast；main 观察器/执行器无条件创建、删旧 submit 分支与观察-only 提前显示、skip_ingest 恒 True、删 flag import；删 test_config.py；.env.example 清理；代码零残留 | `INTENT-02-CLEANUP-FLAGS-01` 真实会话不退化复验 → `INTENT-02-CLEANUP-SUBMIT-01` |
| 2026-08-14 | INTENT-02-CLEANUP-FLAGS-01 真实验收升级 REAL_OK | 438 项通过 | 会话 20260814_095506：启动打印"统一理解链已启用（唯一默认路径）"；6 段口述（2实验+2查看+1弃权+1旧门卫查看），结束"提交 2 段实验口述"，控制/弃权不占计数；误识别"看待确认问题"被统一链正确理解；"还有什么问题？"精确快速路径零 LLM；ASR 94 条 +6、事件 50 条 +2（仅段 1、3）；上下文 2 = 事件数 | `INTENT-02-CLEANUP-SUBMIT-01` 删旧 submit 残留 |
| 2026-08-14 | 用户提问发现统一链 review 无查看结果输出（登记 INTENT-02-REVIEW-OUTPUT-01） | 未改代码 | 会话 095506 中"看待确认问题"（ASR 误识别）被统一链接住，只有"第 N 段已保存"、无"当前没有待确认问题"；ClarificationExecutor REVIEW 分支无显示职责；旧门卫显示只服务精确匹配；与 CLEANUP-COMMAND-01 同步修复 | `INTENT-02-REVIEW-OUTPUT-01`（随命令入口统一） |
| 2026-08-14 | 用户提出 ASR 误识别鲁棒性评测（登记 INTENT-02-ASR-ROBUSTNESS-01） | 未改代码 | 095506 证明新链 LLM 兜底能接住误识别（"看待确认问题"→review）；用户建议清理后把容忍度变成可重复评测：Fake 确定性断言 + 真实 DeepSeek 旁路报告，数据用真实会话误识别样例；与 VERIFY-01"说歪了"场景衔接 | `INTENT-02-ASR-ROBUSTNESS-01`（清理后执行） |
| 2026-08-14 | 用户指示"先不改代码、只记录"鲁棒性复验补充观察（登记 ASR-ROBUSTNESS-RULE-GAPS-02） | 未改代码 | 112047/112445 复验新发现 5 项（DEFER 漏识别×2、否定修正未接住、自然结束语 ValueError、仍需补充空显示 bug、再加50毫升半路弃权）+ 缺口②不稳定复现；按用户指示只登记等确认 | 用户确认后逐项定案 |
| 2026-08-14 | 完成 INTENT-02-CLEANUP-SUBMIT-01 去旧 submit 残留（AUTO_OK） | Python3.11 全量 433 项通过（−5 项旧显示链测试） | main 删除旧链全部残留：create_experiment_llm_processor、SegmentProcessor/SessionProcessingQueue/CompletedSegment、四个旧显示函数、_display、collect_ready/finish/pending_count、外层 finally 队列收尾；统一链改用 main 的 event_store 落盘；main.py 净删 847 行；未动麦克风/LLM | `INTENT-02-CLEANUP-SUBMIT-01` 真实会话不退化复验 → `INTENT-02-CLEANUP-COMMAND-01` |
| 2026-08-14 | SUBMIT-01 首轮复验抓出重构 Bug 并修复 | 433 项通过 | 会话 20260814_101632/101744：每段报"事件保存失败：NameError: name 'event_store' is not defined"，事件全丢、上下文 0——重构把 `segment_processor.event_store` 改为 `event_store` 但未把 event_store 作为参数传入 `run_experiment_session`（跨函数作用域错误）；单测不执行主循环故全绿；补传参修复 | `INTENT-02-CLEANUP-SUBMIT-01` 复验重跑 |
| 2026-08-14 | SUBMIT-01 复验通过升级 REAL_OK | 433 项通过 | 会话 20260814_102122：3 段口述"提交 2 段实验口述"、上下文 2 = 事件数、无事件保存失败、无"当前待处理任务数"（ASR 105 条 +3、事件 52 条 +2 仅段 1、3） | `INTENT-02-CLEANUP-COMMAND-01` 统一命令入口 |
| 2026-08-14 | 完成 INTENT-02-CLEANUP-COMMAND-01 统一命令入口（AUTO_OK） | Python3.11 全量 432 项通过（−4 门卫测试 +3 工厂测试） | 删三道门卫+补丁，统一链唯一命令路径；review 显示（REVIEW-OUTPUT-01）、确认记录持久化（from_executed_confirmation + find_clarification）、执行反馈搬进新链；删 test_confirmation_main.py；未动麦克风/LLM | `INTENT-02-CLEANUP-COMMAND-01` 真实会话验收 → `INTENT-02-CLEANUP-NAMING-01` |
| 2026-08-14 | COMMAND-01 真实验收升级 REAL_OK | 432 项通过 | 会话 20260814_104104：20 段口述——查看显示多次生效、create 追问 3 次、answer 解决 2 问题、计数"提交 6 段"、上下文 6 = 事件数、剩余问题列出（ASR 125 条 +20、事件 58 条 +6）；确认记录真实路径未触发（无 needs_confirmation 场景），单测覆盖，VERIFY-01 补 | `INTENT-02-CLEANUP-NAMING-01` 去影子命名 |
| 2026-08-14 | 用户观察"移液枪未被纠正"（登记 UNIFIED-PROMPT-ASR-ERROR-CONFIRM-01） | 未改代码 | 会话 104104 第 14 段"一夜枪/微生"未触发确认；统一提示词缺"疑似识别错误→needs_confirmation"规则（旧链有，历史 confirmation_reason 为证），与 MISSING-FIELDS 丢失同款；原文保留不受影响（ASR-02） | `UNIFIED-PROMPT-ASR-ERROR-CONFIRM-01` 补规则+测试+真实复验 |
| 2026-08-14 | 用户观察"回答好几遍才 ANSWER 下来"（登记 INTENT-02-ANSWER-UX-01） | 未改代码 | 会话 104104："时间为10分钟"被当新实验事件而非回答；部分回答后无"仍缺字段"反馈（COMMAND-01 删门卫丢失旧话术），用户多次重复；两个子项：反馈补缺 + 无编号回答识别 | `INTENT-02-ANSWER-UX-01` 反馈话术 + 提示词规则 + 真实复验 |
| 2026-08-14 | 用户观察"追问创建后不自动输出"（登记 INTENT-02-QUESTION-AUTO-OUTPUT-01） | 未改代码 | 会话 104104 第 3 段 create 后仅显示摘要、无问题文本；根因 display_coordinated_reply 随 SUBMIT-01 删除；最小显示现在补（并入命令结果显示收尾轮），完整消息管线留 PRESENT-INTEGRATE-01 | `INTENT-02-QUESTION-AUTO-OUTPUT-01` 最小显示 → PRESENT 统一管线 |
| 2026-08-14 | 完成 A+B：命令结果自动输出 + 提示词能力对齐（AUTO_OK） | Python3.11 全量 433 项通过（+1 合同测试） | A：执行器 create reason 含问题文本、answer reason 含"仍需补充"、display_shadow_observation executed 时显示 reason（原被吞）；B：统一提示词补两条规则（疑似错词→确认、无编号回答单/多问题区分）+ 合同测试；未动麦克风/LLM | A+B 真实复验（无编号回答/追问自动显示/错词确认）→ `INTENT-02-CLEANUP-NAMING-01` |
| 2026-08-14 | 完成无编号回答纯函数兜底（用户拍板"字段相关性+纯函数"） | Python3.11 全量 467 项通过（+11 兜底测试，其中 +1 防混） | 新增 `src/core/answer_fallback.py`：`extract_entity_fields`（温度/时间/体积/浓度确定性提取）+ `decide_unnumbered_answer`（单问题+短句+提取字段⊆缺失字段才判回答，夹带无关字段的实验记录绝不路由成回答）；main 弃权(no_action)时构造 ANSWER 动作交执行器；提示词规则收紧（"仅提供无关事实时保持原分类"）回应鲁棒性缺口⑤；合同测试更新；未动麦克风/LLM | 真实复验"时间为10分钟"被接住（单问题）→ 35 REAL_OK |
| 2026-08-14 | 兜底真实复验升级 35 REAL_OK | 467 项通过 | 会话 20260814_113237（4 段）：段 3"时间为10分钟"→ abstention 被兜底接住为 answer（"已填 ['duration'] 仍需补充：temperature"）；段 4"60摄氏度"→"问题已解决"；段 2"分中"听岔碎片不误判；事件仅段 1（回答不产生实验事件）；计数"提交 1 段"、上下文 1、无剩余确认项（ASR 176 条 +4、事件 63 条 +1） | `INTENT-02-CLEANUP-NAMING-01` 改名（或用户定夺 GAPS-02 各项） |
| 2026-08-14 | 完成显示一致性修复（用户指示"现在修"） | Python3.11 全量 468 项通过（+1 仍需确认测试） | ①兜底命中时 observation 的显示字段跟随实际动作（answer/clarification_context），不再出现"待确认动作=no_action 却已执行 answer"矛盾；②`_execute_answer` 的 resolved_note：字段补齐但确认未完成时输出"仍需确认"而非"仍需补充：空"；新增 AnswerConfirmationPendingTests；未动麦克风/LLM | 显示一致性真实复验（短会话）→ GAPS-02 项 E 结案 |
| 2026-08-14 | 显示一致性复验通过升级 REAL_OK | 468 项通过 | 会话 20260814_113958（2 段）：段 2"时间为10分钟"→ 兜底接住且显示自洽（"目标=clarification_context，待确认动作=answer；已执行：已将对问题 1 的答复的实体字段 ['duration'] 填入。仍需补充：temperature。"）；计数"提交 1 段"、上下文 1、剩余问题列出（ASR 178 条 +2、事件 64 条 +1） | GAPS-02 项 E 结案 → `INTENT-02-CLEANUP-NAMING-01` 改名（或用户定夺 GAPS-01/02 其余项） |
| 2026-08-14 | 用户逐项决策 GAPS-01/02 并确认行动计划（仅记录，未改代码） | 未改代码 | 决策：①接受当实验+加回答编号提示（`GAPS-FIX-ANSWER-HINT-01`）；②转 ASR 层；③PHG 再测；④否定修正不做（当实验记录）；⑤再测（旁路复验）；A/B 修（`GAPS-FIX-DEFER-01` defer_targeted）；C 纠正定性（非 deny）；D 方案二固定结束语（`GAPS-FIX-END-01`，方案一留后）；E 已修再测；F 不管；复验安排（`GAPS-REVERIFY-01`） | 用户确认后实施 |
| 2026-08-14 | 完成 INTENT-02-CLEANUP-NAMING-01 去影子命名（AUTO_OK） | Python3.11 全量 468 项通过 | 机械改名：observer/observation/display/request_id/显示前缀/docstring 全部去 shadow（改名清单见看板行 27）；`tests/test_unified_shadow.py` 重命名 `test_unified_observer.py`；src/tests 零 shadow 残留；未动麦克风/LLM | 轻量真实会话不退化复验（显示前缀 [统一链]）→ `INTENT-02-CLEANUP-VERIFY-01` |
| 2026-08-14 | A+B 真实验收升级 REAL_OK（34/35/36） | 433 项通过 | 会话 20260814_110116（13 段）：create 追问文本自动显示（段1/5/11）、answer 完整反馈（段10"问题已解决"）、confirm 反馈（段12）；错词确认生效（段11"一夜枪"→needs_confirmation=True"疑似ASR识别错误：'一夜枪'可能应为'移液枪'"→确认问题→段12"是的"→confirm）→ **确认记录首次真实落盘**；无编号回答段2"时间为10分钟"→abstention（安全未误判但未接住，部分达成）；计数"提交 4 段"、上下文 4 = 事件数（ASR 138 条 +13、事件 62 条 +4） | `INTENT-02-CLEANUP-NAMING-01` 改名 → VERIFY-01 |
| 2026-08-14 | 用户要求提前执行 ASR 鲁棒性评测（INTENT-02-ASR-ROBUSTNESS-01 REAL_OK，只建评测体系与记录问题，不改代码） | Python3.11 全量 454 项通过（+21 语料测试） | 新增 28 段噪声口述语料 + 严格 schema + 21 项确定性断言（13 实验段零误触发；"看待确认问题"依赖 LLM 容错；"还有什么问题"精确命中；双回答/错编号/只有编号已知限制文档化）；确定性报告 零误触发13/依赖LLM 7/精确命中 5/已知限制 3；**真实 DeepSeek 旁路 21/28 一致、7 缺口**（只读，未写业务数据）；用户明确指示：**先不改代码，缺口记录待定案** | 登记 `ASR-ROBUSTNESS-RULE-GAPS-01`（7 缺口）→ 按用户决定与 NAMING-01 顺序推进 |
| 2026-08-15 | RESTORE-NONBLOCK-01 恢复非阻塞录音 + 拆两句谎话（REAL_OK） | Python3.11 全量 483 项通过（+8 队列 +6 工人 +1 集成） | 真实会话 20260815_094954（连说 10 段不卡）：非阻塞实锤（每段 [LLM响应] 插空出现在下一段录音期间）；计数正确（共10段/提交8段/上下文8=事件数）；结束命令不入段；无崩溃；两句谎话已拆（111→"ASR 原文已保存"，320 现为真）。体验：用户接受当前"结果延后显示"节奏，前瞻要求 TTS 不乱序朗读（登记 TIMING-02） | `GAPS-FIX-END-01`（结束语追问确认） |
| 2026-08-15 | 三个硬 GAPS + TIMING-01（REAL_OK/AUTO_OK） | Python3.11 全量 488 项通过（+1 结束确认旁路 +1 defer 生命周期 +1 暂缓 current +1 紧邻） | 会话 111049：END 确认通过（"今天先记录到这里吧"→"是否结束？"→"是"→结束）；会话 112341：DEFER 通过（"这个问题先跳过"→"defer 操作完成"→查看"已暂缓"），真实验收抓出"register_clarification 不设 current"根因并修复；ADJACENCY 单测覆盖；TIMING-01 结果算完当场显示 | `GAPS-REVERIFY-01`（兜底+各缺口复测）或继续软问题 |
| 2026-08-15 | GAPS-REVERIFY-01 + defer_targeted + 降级提示（REAL_OK） | Python3.11 全量 490 项通过（+1 解析器 +1 旁路） | 真实旁路 21/31 一致（③PH/⑤电流/D结束语已闭环，②同音错词走ASR层）；真实会话 115134：E/③/D 三验证点全闭环；defer_targeted 按编号暂缓补完；降级人话提示补上；**发现"是"单字易被ASR听成"Sure."，结束确认提示改为引导说"是的"** | 硬问题清零，进 PRESENT |
| 2026-08-15 | PRESENT 子步 A-1：定义不可变 PresentationIntent（AUTO_OK） | 新增 7 项专项并全部通过；正式 `.venv` 全量 497 项通过 | 新合同不含最终文案和可变 status；复制并只读封装 args；拒绝 DEBUG 混入及非法 id/段号/参数键；未接 main，用户输出零变化，跳过 UX 走查。首次在受限环境启动失败被误判为环境损坏，正常权限复核证明环境无问题 | 下一小步单独做文案目录，仍不接 main |
| 2026-08-15 | PRESENT 子步 A-2a：记录回执文案目录（AUTO_OK） | 新增 9 项专项；正式 `.venv` 全量 506 项通过 | 新增 user/admin 文案；recorded/degraded/failed 三结果严格区分，修正原设计中两个 `degraded=true` 无法区分失败与降级的歧义；非法模式、缺失/未知结果、非法步骤号和错误 kind 均拒绝。未接 main，用户输出零变化，跳过 UX 走查 | 下一小步扩展追问/回答文案，仍不接 main |
| 2026-08-16 | PRESENT 子步 A-2b：追问/回答/确认/暂缓文案 + 字段名中文化（AUTO_OK） | 专项 31 项（copy 24 + intent 7）全部通过；正式 `.venv` 全量 521 项通过（+15） | `copy_for_intent` 扩展 CLARIFICATION（追问独立成句，修 UX-02）、CONFIRMATION_ACK（ANSWERED 三态 已解决/仍需补充/仍需确认 + CONFIRMED）、CLARIFICATION_DEFERRED（暂缓）；新增字段名→中文术语表（temperature→温度 等 10 项，修 UX-07 开发语言泄漏）；追问不加句号、回执统一加句号（去双句号，修 UX-06）；未知字段名保留原样兜底。未接 main，用户输出零变化，跳过 UX 走查。REVIEW 列表文案留到 renderer（多行布局属 renderer 职责，现状已友好） | 下一小步 TerminalRenderer（A-3） |
| 2026-08-16 | PRESENT 子步 A-3：TerminalRenderer + review 文案（AUTO_OK） | 专项 41 项（copy 29 + renderer 5 + intent 7）全部通过；正式 `.venv` 全量 531 项通过（+10） | 新增 `TerminalRenderer`（封装 ui_mode，提供 Intent→终端文本唯一转换点，是子步 B 单一输出入口的前置接缝）；文案目录补 CLARIFICATION_REVIEW（`ReviewItem` + 多行列表，复用现有友好文案"当前共有 N 个待确认问题：- 问题 N（待回答/已暂缓）：…"）；review 列表不区分 user/admin（列表本身就是定位信息）。未接 main，用户输出零变化，跳过 UX 走查 | 下一小步投影层（业务事实→Intent 纯函数） |
| 2026-08-16 | PRESENT 子步 A-4：投影层 + answer 结构化字段（AUTO_OK） | 专项 57 项（projection 13 + executor + processor + observer）全部通过；正式 `.venv` 全量 544 项通过（+13） | 新增 `presentation_projection.py`（`messages_for_observation` + `messages_for_review`，业务事实→Intent 纯函数）；前置补 answer 结构化字段：`ClarificationExecutionResult` 加 `remaining_fields`/`resolved`、`UnifiedObservation` 加 `answer_remaining_fields`/`answer_resolved`、`unified_segment_processor` 透传——修掉"剩余字段散在 reason 字符串"的缺口，投影层不再解析中文。未接 main，用户输出零变化，跳过 UX 走查。**子步 A 全部完成** | 下一小步子步 B（Coordinator + pump + 接线 + 真实验收） |
| 2026-08-16 | PRESENT 子步 B-1：Coordinator 纯逻辑（AUTO_OK） | 专项 8 项全部通过；正式 `.venv` 全量 552 项通过（+8） | 新增 `presentation_coordinator.py` 纯函数 `coordinate`：FIFO 保持顺序 + 相邻语义等价去重 + 单问题限制（多个 CLARIFICATION 只放优先级最高一个，其余返回 deferred 延后不丢弃）。未接 main，用户输出零变化，跳过 UX 走查 | 下一小步 B-2（Renderer 协议 + 有状态队列 + pump） |
| 2026-08-16 | PRESENT 子步 B-2：Renderer 协议 + 有状态队列 + pump（AUTO_OK） | 专项 15 项（coordinator 12 + pump 3）全部通过；正式 `.venv` 全量 559 项通过（+7） | 新增 `presentation_pump.py`（`Renderer` 协议 + `PresentationPump`，唯一 stdout 写入权）；`PresentationCoordinator` 加线程安全队列（`submit` 投递 / `drain` 阻塞取货 / deferred 放回队首）。pump 依赖 `Renderer` 协议而非 `TerminalRenderer` 类（鸭子类型，将来 Web/TTS 渲染器实现同一协议即可）。未接 main，用户输出零变化，跳过 UX 走查 | 下一小步 B-3（接 main + 删旧 print + DEBUG logging，动 main 需真实验收） |
| 2026-08-16 | PRESENT 子步 B-3a：后台 display 回调改投影→投递→pump（AUTO_OK） | 全量 559 项通过（无新增测试，纯接线） | `main.py` 接线：`run_experiment_session` 创建 coordinator + `TerminalRenderer` + pump；`display_segment_outcome` 从直接 print 改成"投影 `messages_for_observation`/`messages_for_review` → `coordinator.submit`"；删 `display_observation`/`display_review_summary` 旧函数；开发详情走 `logging.debug`；`experiment_step_counter` 只对 structured_experiment 递增（编号分离 UX-07）；config.py 加 `UI_MODE`；投影层 `experiment_step_number` 改可选。集成测试 test_main_nonblocking 通过。**真实验收 + UX 走查待 B-3 全部完成后统一做** | 下一小步 B-3b（DEBUG 分流） |
| 2026-08-16 | PRESENT 子步 B-3b：DEBUG 分流（基础设施 + main 开发语言迁 logging） | 全量 559 项通过（无新增测试） | `llm/client.py`（[LLM请求]/[LLM响应]）、`asr/sensevoice_backend.py`（加载/识别）、`core/state_manager.py`（状态变化）print → logger；`main.py` 的"统一理解链已启用"/"处理失败"/"最终上下文"迁 logging；`main()` 加 `configure_logging`（user 写 `results/debug.log`，admin 输出屏幕）。屏幕不再有 token/路径/状态变化/[LLM请求] 开发语言 | 下一小步 B-3c（主循环用户消息 print → pump，达成单一输出入口） |
| 2026-08-16 | PRESENT 子步 B-3c：主循环用户消息 → pump（单一输出入口） | 全量 562 项通过（+3 透传测试） | 文案目录加透传 kind（TRANSCRIPT/WAKE_ACK/STAGE_SUMMARY/SESSION_SUMMARY/SYSTEM_ISSUE，args text 透传）；main.py 加 `emit` 闭包，主循环/结束汇总/待确认列表 print → emit；`recognize_one_segment` 提示移到主循环；`display_unresolved_clarifications` 改为投递 CLARIFICATION_REVIEW（去掉"来源第N段"开发语言，修 UX-08）；main() 启动/唤醒/异常/退出 print → logging。**main.py 零 print 残留，达成"单一输出入口 + 旧 print 已删"** | 下一小步 B-4（真实验收 + 九维走查，需授权数据外发） |
| 2026-08-16 | PRESENT 子步 B-4：真实验收（会话 20260815_212615，用户自启） | 全量 562 项通过（真实验收未加测试） | 用户自启真实会话 6 段口述（缓冲液/加热60度/问题一/查看/离心/结束）。**发现 4 个软问题**（按硬软判据归类，均不阻塞主流程、数据未丢）：①开发输出泄漏——`vad_recorder.py`/`recorder.py`/`wakeword/detector.py` print + FunASR 进度条未迁 logging，屏幕有路径/rtf/音频时长，维1/7 失败；②投影层 no_action 无容错反馈——段3"问题一"因问题1不存在→no_action→屏幕沉默，维6 失败；③**LLM 缺字段追问漂移**——`加热到60摄氏度` duration=null 但 missing_fields=[]，历史 08-11/12 同类"将溶液加热"稳定追问 {temperature,duration}；`git log -S` 证实追问规则（unified_prompts.py 第64-65行）自 08-11 引入后未改，故是 DeepSeek 模型服务端行为漂移，暴露"缺字段追问 100% 靠 LLM、无确定性兜底"；④ASR 误识别——"加热到60摄氏度APP"尾音、"结束实验记录"被 language=auto 误判粤语(yue)"要车翻圈啦"。**通过项**：编号分离（实验步骤1/2/3）、结束汇总用户语言、回执及时（维4/5/9 通过）、DEBUG 落 debug.log | 先修①②（PRESENT 收尾），③加确定性兜底，④走 ASR 线 |
| 2026-08-16 | WEB-BRIDGE-01：web 统一链桥迁移（REAL_OK） | 全量 715 项通过（+7 web 桥接测试；此前 15 errors 系 `.venv` 缺依赖，非代码问题） | **环境修复**：`.venv` 缺 numpy/sounddevice/soundfile/sherpa-onnx 致 15 errors，逐包补齐（清华镜像），requirements.txt 补 numpy 显式声明；funasr/torch 无需装（测试未直接 import）。**迁移**：`web/llm_bridge.py` 换 `UnifiedUnderstandingProcessor`、`extract()` 加 `recent_context` 与 `input_kind`；`web/api/record.py` 补 `_recent_context()`。**真实验收**（会话 `20260816_200646`，deepseek-v4-pro @ api.deepseek.com/v1）：5 条口述（加热60度/加5毫升盐酸/帮我看看待确认的问题/离心机800转10分钟/溶液变蓝）全部无降级、实体抽取准确，口述 3 识别为 `input_kind=control` 零错误卡片（旧链做不到）；缺时长未追问对应当前未定案争议 `LLM-FOLLOWUP-STRICT-01`。前端零改动（消费的 entities/degraded/evaluation 字段格式不变）。迁移对照：`PROJECT_ARCHITECTURE.md` §5.3 WEB-BRIDGE-01 + §5.6 | 功能 REAL_OK；体验验收（UX 九维走查）待用户确认；下一步按用户路线决策：web 纯规则业务下沉（planner/tools 两步确认等）或先收团队标准 §2/§3 例外条款 |
| 2026-08-16 | WEB-AGENT-FAKE-RECORD-01：聊天 agent 假记录修复（REAL_OK） | 全量 739 项通过（+5 提示词合同测试） | 用户实测发现：聊天区输入「离心机八百转运行十分钟」，agent 回复"已记录"但 lab_records 无记录（task 6830ffe4，数据丢失隐患）。根因：`agent/core.py` INSTRUCTIONS 未引导 record_observation 工具。修复：提示词强制"描述实验操作必须调工具、工具成功才可确认已记录、失败须如实说明"。真实验收（重启 web 后 `/chat` 实测）：task 77ce319c 回复"已记录"且 lab_records 新增 id=10（rule 抽取），话术未变但行为变真；对话历史 4 条历史假记录（加热/离心机/溶液/查看）未落盘的事实已留存，用户可重输补录 | 聊天区实验记录已真实落盘；提醒用户历史 4 条假记录需重输；下一步同 WEB-BRIDGE-01 待办 |
| 2026-08-17 | 登记微调（LoRA）与本地推理远期路线：新增第 4 节 K 组 6 项任务（边界确认/数据审计/清洗合同/训练/评估/接入）+ 3.3 暂缓表与优先级总览各补一笔；任务 ID 与桌面真实项目 2026-08-16 既有登记对齐 | 未改代码；沿用全量 739 项基线 | 文档登记，无用户输出变化 | 当前唯一下一项不变：`CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01` |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B1 敲钉子定稿（DESIGN，纯设计不写码） | 全量 755 项通过（基线复验，零代码改动） | 用户指示按 `docs/VOICE_WEB_MIGRATION_PLAN.md` 推进。**B1 决策**：选"容忍部分观察的分支"，否掉拼富字段方案——①"记录成功"路径需 step_number（CLI 由会话级计数器提供），web 降级生产者契约禁止托管有状态会话，语义缺口无法诚实补齐；②拼 `ClarificationAction` 需伪造 asr_transcript/reason/mutation_permission 等样板值，违反"模型推断不覆盖原始事实"。降级生产者填 10 字段（身份 3 + status/partial/destination/acceptance_kind/missing_fields/follow_up_required/partial_question）；`UnifiedObservation` 加 `partial: bool=False` + `partial_question: str\|None=None`（partial=True 放宽 OBSERVED 校验，CLI 完整路径不变）；投影层 OBSERVED 内加 partial 分支（有追问→CLARIFICATION / 无→RECORD_ACK）；真观察器 drop-in（D3）时分支自然闲置、调用点零改动。现状确认：web `/record` 的 `evaluation`（`domain.evaluate`→`evaluate_segment` 薄字典）即计划要消灭的平行投影，前端 voice_asr/mobile/views/lab_panel 四处直接读它——B2 起替换。顺带修正 checklist"恢复工作时先运行"仍写桌面路径（改 107） | 下一步 B2：实现降级生产者 + `WebRenderer`（意图→结构化 JSON）+ 全单元测试，零真实服务 |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B2-1：输出层支持"部分观察"（DESIGN 内闭环） | 专项 37 项通过（13 新 + 24 回归）；**全量 768 项通过（+13）** | **改动**：① `src/core/unified_observer.py` `UnifiedObservation` 加 `partial: bool=False` + `partial_question: str\|None=None`；`__post_init__` 分叉——partial=True 放宽 OBSERVED 校验（不强制 destination/clarification_action），且四道反向校验：部分只能是成功观察 / 成功不能带错误 / 追问文本非空白 / 追问文本仅 partial 允许（防完整路径夹带）；CLI 完整路径（partial 默认 False）校验原样。② `src/core/presentation_projection.py` `messages_for_observation` 在 FAILED 检查后加 partial 分支：有追问文本→CLARIFICATION（screen_target=CURRENT_QUESTION）/ 无→RECORD_ACK 降级（复用现成 `_clarification`/`_record_ack`，零新增辅助函数）。③ 新增 `tests/test_observation_partial.py` 13 项（8 构造 + 5 投影，含 3 个 CLI 完整路径回归：老校验不放宽、完整路径不能带追问、CLI 投影不变）。**层边界确认（用户纠正）**：投影只产意图（不含中文），话由 copy 层 + 渲染器生成——已固化进迁移计划 B1 结论块与学习日志知识 4。**当场完整展开 + 学习日志唯一存档**（用户要求"当场记录与写入日志同样重要"；2026-08-18 用户定不另建卡片文件）：六要素当场在对话完整展开，归档只进正式学习日志 | 下一步 B2-2：降级生产者（`evaluation` → 部分 `UnifiedObservation`，web 侧模块 + 单测，零真实服务） |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B2-2：降级生产者（DESIGN 内闭环） | 专项 12 项通过；**全量 780 项通过（+12）** | **改动**：① 新增 `web/degraded_producer.py`——`produce_partial_observation(*, request_id, session_id, segment_id, evaluation) -> UnifiedObservation` 纯函数，把 web 现有 `evaluation`（`domain.evaluate` 薄字典产物）按 B1 的 10 字段清单翻译成部分观察：有非空追问文本→追问观察（destination=clarification_context / acceptance_kind=None）；无→记录观察（destination=experiment_pipeline / acceptance_kind=degraded_evidence_note）；`missing_fields` list→tuple；`follow_up_required` 如实抄录但不参与判定。**判定以追问文本非空为准（与投影层消费同源）**，避免"标志为真、文本为空"的矛盾状态；**畸形输入（evaluation 非 dict）降级为 FAILED 观察，永不抛异常**。② 新增 `tests/test_degraded_producer.py` 12 项（追问/记录映射、身份透传、tuple 转换、标志-文本矛盾、空 evaluation、None/非 dict 畸形输入、与投影层联动 3 项）。**设计决策**：fail-fast（创建点严格校验）与 fail-safe（转换点容错）分属两层；纯函数生产者保证可测试、可 drop-in 抽换。教学硬规则生效：六要素当场对话完整展开，归档只进正式学习日志（2026-08-18 用户定不另建卡片文件） | 下一步 B2-3：WebRenderer（意图→结构化 JSON，web 侧模块 + 单测，零真实服务） |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B2-3：WebRenderer（B2 收官） | 专项 10 项通过；**全量 790 项通过（+10）** | **改动**：① 新增 `web/web_renderer.py`——`WebRenderer` 类（ui_mode 默认 user），`render(intent) -> dict` 把意图渲染成前端可消费 JSON：intent_id/kind/screen_target/priority（转 int 保证可序列化）/source_segment_id/text（`copy_for_intent(intent, ui_mode)` 生成，词在后端）；**不透传 args**（防前端拿参数二次判断，契约 4"前端只画不判"）；不实现 CLI pump 的 Renderer 协议（产出 dict 而非 str，web 无 stdout pump，角色一致、形态不同）。② 新增 `tests/test_web_renderer.py` 10 项（字段映射 6、JSON 可序列化、admin 来源追加、copy 不支持 kind 明确抛错、降级生产者→投影→渲染全链路 2 项）。**知识存档形态修订（用户 2026-08-18 定）**：撤销 `docs/learning_notes/` 卡片目录（删除 3 张卡片，内容已并入学习日志 B1/B2-1/B2-2 条目），改为"当场对话完整展开 + 学习日志唯一存档"，CLAUDE.md 教学硬规则第 2 条同步修订 | 下一步 B3：`/record` 影子式新增 `messages` 字段（降级生产者→投影→WebRenderer 全链在 `/record` 内联，**保留原始 evaluation**；肉眼核对顺序 + 单问题闸门生效） |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B3：/record 影子 messages（DESIGN 内闭环） | 专项 6 项通过；**全量 796 项通过（+6）** | **改动**：`web/api/record.py`——① import 增 `uuid`/`degraded_producer`/`web_renderer`/`messages_for_observation`；② `record()` 在 `domain.evaluate(entities)` 后内联影子接线：`produce_partial_observation(request_id=f"web-{uuid.uuid4().hex[:12]}", ...)` → `messages_for_observation` → `WebRenderer().render` 列表；③ `saved = save_record(item)` 后 `saved["messages"] = messages` 再返回——**evaluation 及其余字段零改动**；messages **不入库**（save_record 九列白名单之外，派生数据随用随算）；畸形 evaluation（None）由降级生产者兜底为失败消息，接口不崩。**设计决策**：影子模式（新输出旁观、旧输出照旧、可回退）；request_id 用 uuid4（全局唯一、不依赖 session/segment 内容）；messages 挂接口返回而非落库（消费者是本轮交互的前端，不是历史存档）。**测试**：`tests/test_web_record_messages.py` 6 项（追问→clarification 影子字段结构、原始字段保留、无追问→record_ack、落库 item 不含 messages、None→失败消息、JSON 可序列化），mock 掉 llm_bridge/数据库/domain.evaluate。**下一步需要真实验收**：肉眼核对 /record 返回 messages 顺序 + 单问题闸门（每请求一条） | 下一步 B4：前端切渲染 messages（退役正则分类）+ 写 5.3/5.4 迁移对照 |
| 2026-08-18 | VOICE-WEB-MIGRATION-01 B4：前端切渲染 messages（Phase B 收官，AUTO_OK） | 全量 796 项通过（无新增测试；前端 JS 无单测框架，靠合同测试 + 语法检查 + 待真实验收） | **改动（4 个前端文件）**：① `speak.js` +`labSpeakMessages`（朗读 messages 中追问，一次一条避免抢播）；② `lab_panel.js` `labRender` 从读 evaluation 渲染追问/偏差改为按 messages kind 渲染（追问 lab-ask / 回执 lab-ok；保留实体标签；修掉替换时丢失的 lab-step 闭合 div）；③ `voice_asr.js` /record 响应改 `labRender(d)` + `labSpeakMessages(d.messages)`，删除 evaluation.follow_up_required/deviations 拼话播报；④ `mobile.js` `handleRecordResult` 改 messages 渲染（isAsk=kind=clarification 或 screen_target=current_question → 追问气泡+speak）。**保留点（标注）**：`views.js` 历史视图仍读 evaluation（messages 不入库，历史无 messages，属存储数据展示）；`labEvaluate` 面板走 /protocols/evaluate（非 /record 链）。**合同测试更新**：`test_web_mobile_page.py` 断言新合同（messages/screen_target/clarification）+ 旧字段退役（assertNotIn follow_up_question/deviations）。**迁移对照**：`PROJECT_ARCHITECTURE.md` §5.3 WEB-RENDER-01 + §5.4 web 侧 5 行——追问播报**等价**、偏差播报**丢失**（登记：降级生产者/投影层补 deviations 消息，随 D 阶段）、"本步现场记录已完整"**降级**（D 阶段 structured_experiment 恢复）、实体展示与历史视图**等价**。**JS 语法**：node --check 4 文件通过。**Phase B（B1-B4）全部完成** | 下一步：真实验收 + UX 走查——启动 web，/record 肉眼核对 messages 顺序/单问题闸门，B4 前端实际渲染与追问播报，按九维表走查（最终裁决权在用户）；通过后进 Phase C |
| 2026-08-18 | 真实验收发现并修复 WEB-RENDER-02：桌面语音链死代码（用户实测"称量磷酸盐"返回 agent 话术） | 全量 796 项通过（零回归；JS 语法 node --check OK） | **真实验收暴露**：用户语音说"称量磷酸盐"，界面返回聊天 agent 话术（"好的，请问称量了多少克磷酸盐？"），非 B4 的 messages 话术（copy 层"小科：…"）——查证 `voice_asr.js`：`if (input && form) { requestSubmit(); return; }` 聊天框分支优先，B4 改的 `/record` 直连分支因 `return` 在前**从未执行（死代码）**；单测/语法/全量全绿但用户路径未走通——印证真实验收不可替代。**用户拍板**：桌面语音也直连 /record（"当然要改"）。**修复**：删除 voice_asr.js 聊天框分支，语音口述一律 `fetch('/record')` → labRender(messages) + labSpeakMessages；保留 `labStepsReload` 延迟刷新。**文字聊天（composer→/chat）不动**。**迁移对照**：`PROJECT_ARCHITECTURE.md` §5.3 增 WEB-RENDER-02（等价提升：桌面与 /m 统一 messages 渲染）。**知识**：死代码只有真实验收能暴露（学习日志 2026-08-18 条目）。**待用户刷新页面复验**（Ctrl+F5 → 录音说"加入五毫升缓冲液" → 预期面板回执、聊天区不再出现 agent"⚙记录实验口述"） | 下一步：用户复验桌面语音直连 + /m 页验证 + 九维走查 |
| 2026-08-18/19 | Phase B 真实验收通过（REAL_OK）+ 一轮验收修复 | 全量 **800 项通过**（硬问题修复 +4） | **真实验收闭环**：用户实测语音记录链路（灰色圈圈→录音→/record→面板"第 N 段口述"+回执"已记录"）+ 选方案缺字段→"小科追问"+TTS 朗读纯问题。验收逐项修复：① **话术撒谎硬问题**——"结构化成功却说不可用"（`RecordAckResult` 增 `RECORDED_NO_STEP`"已记录"；降级生产者按"有没有抽到实体"填 `partial_recorded`/`degraded_evidence_note`；投影层据此出话术）；② **lab_panel.js 未注入**——app.py 注入脚本漏了它，labRender 不存在、结果无处渲染（补注入 + 恢复被 `void init` 禁用的面板 init）；③ **语音入口混乱治理**——4 入口职责混杂：cp-mic 误触发电话（删电话分支改"语音记录"）、vad"自动语音"改"语音对话"、通话保留独立；④ **文案**——"助手追问"→"小科追问"（统一称呼、去重复）、TTS 不念"小科："前缀（labRender/speak/mobile 三处去前缀）；⑤ 前端容错——空语音提示"没听清"、/record 400 显示错误（修"第 undefined 段口述"）；⑥ cache-busting——voice_asr/speak/mobile/lab_panel 加版本号防浏览器缓存。**关键定位纠正（用户）**：统一理解链核心是**处理命令（control 分支：查看/暂缓/确认/结束/回答）**，B 降级生产者只有"记录+方案追问"，命令处理待 **Phase D** 接真观察器（含 LLM）。**遗留软问题登记**：ASR 数字误识别（5→65，SenseVoice 层）；录音停止到反馈 3-5 秒无"处理中"提示（维 5/9） | 下一步：Phase C（语音收敛：三张嘴单一 window.speak、TTS 读 copy 文案、真机 barge-in）或 Phase D（命令处理迁入）；方向待用户定 |
| 2026-08-18 | 教学硬规则增补（CLAUDE.md 第 5 条，用户 2026-08-18 定） | 未改代码；沿用全量 790 项基线 | CLAUDE.md"教学执行硬规则"新增第 5 条：**设计原因必须展开取舍过程**——候选对比（差异精确到代码形态"哪一行有/没有"）+ 事故推演（从一行代码推到用户面前的 bug：越权入口/双份逻辑/正则倒退）+ 未来影响（对后续 B4/C2 阶段）+ 能合并主线先讲主线。源于 B2-3 WebRenderer 讲解时用户要求"设计原因把取舍思考过程再展开、深度再深一点"；用户确认后固化进规则 | 下一步不变：B3 `/record` 影子 messages |

## 7. 每轮结束时必须更新

1. 更新对应任务的状态。
2. 填写自动测试数量和结果。
3. 如果进行了真实验收，记录 session_id 或日志证据。
4. 更新“当前唯一下一项”。
5. 在维护日志追加一行。
6. 如果文件结构变化，同步更新任务备注和交接文档。
7. 开发、测试或真实验收中发现的新问题，必须在本清单登记任务 ID 或写入维护日志，不能只保留在对话中。
8. 新问题需要注明发现来源、影响、依赖关系和建议处理时机；未确定方案时标记为 `TODO` 或 `DESIGN`，不得假装已经解决。

---

## 合并补充：protocol / TTS / 危化品三层（2026-08-14）

以下内容来自与主线并行开发的分支，合并时以主线记录为基底，本节仅补充主线未覆盖的部分。

最后更新：2026-08-12
- 全量自动测试：`517 tests OK`（项目 `.venv`，2026-08-12）
- 最近真实连续口述会话：`20260811_143031`
- 最近真实会话已验证：CREATE✅、ANSWER✅（extractor提取实体→已执行）；新老并行重复问题（已知）；LLM不稳定偶尔abstention（已知）；启动慢（MODEL-LOAD-02）
> `PROTOCOL-INTEGRATION-01`：把已选方案和当前步骤接入会话级状态；本轮已先完成新语义纯数据合同，接线前仍不修改 `main.py`。
| 17 | `P0` | `PROTOCOL-01` 实验方案合同、方案库与确定性缺失字段 | `AUTO_OK` | 将“方案目标值”和“现场必须记录值”拆开，并为实体值保留来源、偏差和显式步骤游标 | 新增协议来源值、偏差检测、步骤游标3个纯数据模块；种子方案改用`protocol_values`/`must_record`；新增16项专项测试；全量517项通过；保留旧字段读取兼容但新逻辑只看新字段；未改main、未接LLM/ASR/OCR/上传 |
| `TTS-01` | `P3` | 定义 TTSClient 接口 | `AUTO_OK` | 本轮以TTSBackend Protocol、CancelScope、InterruptibleTTSPlayer和NullTTSBackend完成纯契约；新增17项测试，未接真实引擎、声卡或主流程 |
| 2026-08-12 | 修正PROTOCOL-01字段语义：方案目标值与现场实测值分离；新增值来源、字符串偏差检测和显式步骤游标 | 新增16项专项；项目`.venv`全量518项通过；`git diff --check`通过 | 纯数据、纯函数和本地JSON读取，无外部服务或真实设备验收；3份重写后的本科中文方案均由ProtocolStore成功加载；未修改main、未接LLM/ASR/OCR/上传、未提交或推送 | `PROTOCOL-INTEGRATION-01`接入会话级方案/步骤状态；继续保留自由记录模式 |
# 补充内容
知识库+RAG 帮 LLM 更精准地结构化口述（补全缺省参数、纠正专业词、发现 SOP 偏差），用户画像 减少重复追问（记住个人默认值和偏好），两者都是增强现有链路质量而非新增功能模块。
当前预留接口建议（3 处，不动业务逻辑）
1. SessionContext 扩展一个可选字段
当前 CTX-01 传"最近 N 条事件"给 LLM。在构建上下文时增加一个可选参数，现在什么都不传：
# 构建 LLM prompt 时
context = {
    "recent_events": [...],   # 已有
    "user_profile": {},       # 新增，当前为空字典
    "knowledge_hints": [],    # 新增，当前为空列表
}
user_profile 以后填：默认离心转速、常用体积、交互详细程度等。
knowledge_hints 以后填：SOP 匹配片段、术语纠错候选、安全提示等。
两个字段今天为空，LLM prompt 构造逻辑不需要改，只是数据结构上占位。
2. PendingClarification 追问增加来源标记
当前 CLARIFY-01/09 的追问结构里，追问只有 source_segment_id 和 missing_fields。增加一个可选字段标记追问的"知识来源"：
{
    "source_segment_id": 3,
    "missing_fields": ["离心时间"],
    "knowledge_source": null   # 新增，以后可以是 "sop:protocol_42" 或 "rag:exp_20260801"
}
用途：以后知识库触发的追问和 LLM 自己猜的追问可以区别对待——知识库触发的可以降低重复询问频率，LLM 猜的保持现有确认逻辑。
3. ExperimentEvent 实体字段预留标准化引用
当前 LLM-07 产出操作/观察/测量/异常四类事件。实体信息（试剂名、设备名、数值）目前混在 normalized_text 里。在数据结构中增加一个可选的对象字段*：
{
    "type": "observation",
    "normalized_text": "溶液变为蓝色",
    "entities": {               # 新增，当前为 null
        "reagent": null,
        "equipment": null,
        "measured_value": null,
        "matched_term": null
    }
}
matched_term 以后存知识库匹配到的标准术语（如 ASR 的"一液枪"匹配到标准词"移液枪"），reagent 以后可以关联到化学品属性库。
┌─────┬─────────────────┬─────────────┬───────────────────────────┐
│ 序  │      位置       │    成本     │           收益            │
│ 号  │                 │             │                           │
├─────┼─────────────────┼─────────────┼───────────────────────────┤
│ 1   │ SessionContext  │ 改一处构造  │ 画像和 RAG 都有了注入点   │
│     │ 加两个空字段    │             │                           │
├─────┼─────────────────┼─────────────┼───────────────────────────┤
│     │ PendingClarific │ 改一个数据  │ 区分"有依据的追问"和"猜测 │
│ 2   │ ation 加 knowle │ 结构        │ 追问"                     │
│     │ dge_source      │             │                           │
├─────┼─────────────────┼─────────────┼───────────────────────────┤
│ 3   │ ExperimentEvent │ 改一个数据  │ 实体可追溯、可纠错、可关  │
│     │  加 entities    │ 结构        │ 联外部库                  │
└─────┴─────────────────┴─────────────┴───────────────────────────┘
三处都是纯数据结构预留，不改一行业务判断逻辑。
注：这个可能已在你的领域记录设计中被覆盖（OUTPUT_PRESENTATION_POLICY.md 2.1 节的 ExperimentEvent 提到"实体"），如果已有字段就直接用，不需要重复加。
## 2026-08-12 本轮维护记录：PROTOCOL-01旧字段语义清理
- 任务：迁移 `tests/test_protocol.py`、`tests/test_protocol_missing_fields.py`、`tests/test_protocol_selection.py`、`tests/test_protocol_store.py` 中的旧 `required_fields` / `expected_values` 用法。
- 源码：删除 `src/storage/protocol_store.py` 的旧字段读取兼容；正式 JSON 只接受 `protocol_values` 与 `must_record`。
- 语义：`protocol_values` 是方案固定值，不参与缺失追问；`must_record` 只表示本次现场必须产生的实测字段。
- 测试：用户指定的全量命令最终通过，`Ran 518 tests ... OK`。
- 验收边界：本轮只处理纯数据合同、存储读取和测试迁移，不修改 `src/main.py`，不接入 LLM 或会话主流程。
## 2026-08-12 本轮维护记录：可打断TTS纯逻辑地基
- 任务：定义按块产出的TTS后端合同、基于代数计数器的取消范围、可注入音频sink的播放结果合同和null占位工厂。
- 新增：`src/audio/cancel_scope.py`、`src/audio/tts_backend.py`、`src/audio/null_tts_backend.py`、`src/audio/tts_player.py`、`src/audio/tts_factory.py`、`tests/test_tts.py`；配置同步加入`TTS_BACKEND`和`TTS_ENABLED`，`.env.example`同步更新。
- 测试：TTS专项17项通过；全量自动测试从518项增加到535项，`Ran 535 tests ... OK`；`git diff --check`通过；新增和修改文件均通过UTF-8读取与中文字符自检。
- 设计边界：取消检查放在每个音频块进入sink之前；单写者+多读者前提下不加锁；有意不实现真实播放接入所需的过时输出丢弃队列。
- 验收边界：本轮不修改`src/main.py`、`InteractionCommandType`、`AssistantState`接线，不引入sounddevice输出流或任何真实TTS依赖，不接模型、不碰声卡；因此状态为`AUTO_OK`，不是`REAL_OK`。
- 下一步：`PROTOCOL-INTEGRATION-01`仍是项目主线；TTS方向下一步再评估真实后端和播放设备接入，必须先补半双工状态、输出协调和真实设备验收方案。
## 2026-08-17 本轮维护记录：手机演示页 /m（扫码即用第一版落地）
- 任务：为比赛"扫码即用"演示提供手机专用页 `/m`（大录音按钮 + 转写/追问展示），复用现有 `/asr/transcribe` + `/record` 接口，不依赖桌面版 shell/composer 布局。
- 新增：`web/frontend/mobile.html`、`web/frontend/mobile.js`（PCM 采集 → 16kHz WAV → 上传 → 结构化 → speechSynthesis 播报）、`web/app.py` 的 `GET /m` 路由、`tests/test_web_mobile_page.py`（4 项：路由注册/页面结构/接口约定/不依赖桌面脚本）。
- 测试：专项 4 项通过；全量 `Ran 743 tests ... OK`（基线 739 + 4）。
- 部署实况：本机 HTTPS 局域网服务可运行（自签证书 SAN=10.101.192.18）；SenseVoice 模型在 ModelScope 缓存中，warmup 后零下载。
- 登记新问题（部署线，均待修）：
  - `WEB-DEMO-IP-DETECT-01`：`phone_access.lan_ip()` 用 UDP connect 选出口网卡，会被代理虚拟网卡（Mihomo 198.18.0.1）抢先，导致二维码/证书 SAN 指向不可达地址；需改为优先真实网卡（过滤保留段 198.18.0.0/15 与虚拟网卡）。
  - `WEB-DEMO-TUNNEL-BIN-01`：`start_phone_tunnel.py` 的 `find_tunnel` 不检查项目 `bin/cloudflared.exe`（`start_best.py` 有检查）；且本机连不上 Cloudflare 边缘（代理干扰），隧道模式暂不可用，现场需预案。
- 体验：手机真机走查由用户进行中（UX_CONFIRMED 待用户确认，不得代填）。
- 下一步：真机验收 `/m` 语音闭环 → 修 `lan_ip` 选网卡 → 现场网络预案（有网/无网两套）。
## 2026-08-17 本轮维护记录：火山引擎 TTS 供应商（第 6 个）
- 任务：接入火山引擎豆包语音合成（openspeech.bytedance.com HTTP 非流式接口），给演示一个确定能出声、音质好于系统语音的 TTS 选项。
- 新增：`web/tts_providers.py` 加 `volcano` 供应商（`tts_api_key` 填 `appid:access_token` 冒号分隔）+ `_volcano()` 合成函数（`Bearer;token;appid` 鉴权、base64 音频解析、业务码校验）+ `tests/test_web_tts_providers.py`（7 项：注册信息/请求构造/鉴权头/密钥格式错误/业务错误码/缺音频）。
- 测试：专项 7 项 + 手机页 6 项通过；全量 `Ran 750 tests ... OK`（743 + 7）。
- 网络判断纠正：本机外网实际可用（python 实测 pypi/github/deepseek/baidu/modelscope 通，仅 huggingface 超时）；此前用 curl.exe 测得的"全 000"是该程序在此执行环境被沙箱拦截的假象，不是电脑没网。cloudflared 隧道不可用原因待复查（可能同样受沙箱/网络策略影响）。
- 待用户操作：在设置面板填 appid:access_token 并测试合成（真实验收，UX 由用户裁决）。
## 2026-08-17 本轮维护记录：ASR 固定中文（ASR_LANGUAGE=zh，防粤语误判）
- 任务：`ASR-DEMO-NOISE-01` 第一条——`language=auto` 曾把"结束实验记录"误判粤语成"要车翻圈啦"，生产链路默认固定 `zh`，不调用云端 ASR。
- 改动：`src/config.py` 新增 `ASR_LANGUAGE`（默认 zh，环境变量可覆盖）；`src/asr/sensevoice_backend.py` `recognize` 默认值改 `ASR_LANGUAGE`；`src/asr/backend.py` Protocol 默认同步；`.env.example` 加 `ASR_LANGUAGE=zh`。评测工具（compare_asr_languages、build_command_corpus_baseline）保留显式 auto 作对比，不受影响。
- 测试：新增 2 项（config 默认 zh、recognize 默认 zh 且传入引擎）；全量 `Ran 752 tests ... OK`（750 + 2）。
- 部署：服务已重启、ASR 已重新预热（warmup 200 loaded）。
- 待验：真实口述复验"结束实验记录"等结束命令不再误判粤语（REAL_OK 待真实验收）。
## 2026-08-17 本轮维护记录：修复设置面板"语音合成"区块不显示（前端三脚本打架）
- 现象：电脑桌面版点左侧"模型与语音"，设置面板只有"模型设置"、没有"语音合成"（用户报障）。
- 根因（写两遍打架）：`settings.js` 创建弹窗 `#settings-modal`；`views.js` 的设置视图把面板 `box` 搬进画布内嵌显示，搬完才通知 TTS；`tts_settings.js` 仍在 `#settings-modal .settings-box` 找 box → 已被搬走 → 找不到就静默 return → "语音合成"永不注入。且 box 被搬进画布后切走视图会被清空，二次进入设置面板空白。
- 修复（3 个前端文件，纯 JS）：`tts_settings.js` attach 改为全局查 `.settings-box`；`views.js` 设置视图不再搬 box，改为弹窗形式打开（box 永驻弹窗）；`shell.js` 切换视图时自动关闭设置弹窗。
- 验证：node --check 三个文件语法 OK；全量 `Ran 752 tests ... OK`（JS 无单测基建，靠语法检查+人工验收）；静态文件改动无需重启服务，浏览器强刷即可。
- 待验：用户电脑 Ctrl+Shift+R 强刷 → 点"模型与语音" → 弹窗应含"语音合成"区块（火山 appid:token 配置入口）。
## 2026-08-17 本轮维护记录：火山 TTS 鉴权头修正（3 段 → 2 段）+ 资源未开通定位
- 现象：火山测试返回 401 code 3001 "invalid amount of Authorization header parts: 3"。
- 诊断（实证）：逐种试鉴权头格式，`Bearer;{token}`（2 段）鉴权通过（不再报 parts 错误）；3 段/4 段均被拒；`Bearer {token}`（空格分隔）报 invalid auth token（分隔符必须分号）。
- 修复：`web/tts_providers.py` `_volcano` 鉴权头 `Bearer;{token};{appid}` → `Bearer;{token}`（appid 本就在请求体）；测试断言同步。
- 剩余阻塞（账号侧，非代码）：鉴权通过后返回 403 `[resource_id=volc.tts.default] requested resource not granted`——应用未开通"语音合成"资源。待用户在火山控制台开通"语音技术/语音合成"服务后重测。
- 测试：专项通过；全量 `Ran 752 tests ... OK`；服务已重启。
## 2026-08-17 本轮维护记录：火山 TTS cluster 配置化（对照官方 demo 补齐）
- 依据：官方 tts_http_demo.py 明确 cluster 是"平台申请的"（FAQ Q1 可查），非写死值；硬编码 volcano_tts 在 cluster 不匹配时返回 403 `volc.tts.default not granted`。
- 修复：`web/tts_providers.py` cluster 改从 `settings.tts_model` 读取（默认 volcano_tts，设置面板"合成模型"框可改）；补齐官方 demo 的 `volume_ratio/pitch_ratio/text_type` 字段；PROVIDERS volcano 项加 `default_model=volcano_tts`。
- 测试：新增 cluster 取自 tts_model 断言；专项通过；全量 `Ran 753 tests ... OK`（+1）；服务已重启。
- 待用户：控制台查 cluster（FAQ Q1）→ 填"合成模型"框 → 确认"语音合成"已开通 → 重测 /tts/test。
## 2026-08-17 本轮维护记录：火山 TTS 错误透传 + 凭据诊断（grant not found）
- 工程改进：`web/tts_providers.py` 火山 HTTP 非 200 时透传响应体（code/message），不再只显示"401 Unauthorized"；测试 +1；全量 `Ran 754 tests ... OK`；服务已重启。
- 凭据诊断结论：当前 appid=60123933355 + 31 位非字母数字 token，火山返回 `code 3001 load grant: requested grant not found in SaaS storage`——该凭据无正式授权记录（体验中心/试用凭据不能调正式 API）。用户需在语音技术控制台创建正式应用，取 appid/token/cluster 三件套。
## 2026-08-17 本轮维护记录：火山 TTS 正式打通（真实凭据 + settings_store 缓存/字段 bug）
- 凭据：用户提供正式应用凭据（appid 6012393335 + 32 位 token）后，直调火山返回 `code 3000` 合成成功（66KB mp3）。
- 发现的工程 bug（`web/settings_store.py`）：① `current()` 有进程内缓存，直改 settings.json 服务端不感知；② 从文件重建配置时只读部分字段，漏 tts_provider/tts_api_key/tts_model/tts_voice/tts_base_url/tts_speed——文件重建丢 TTS 配置。修复：`current()` 补全全部 TTS 字段。
- 测试：新增 `tests/test_settings_store.py`（文件重建读全 TTS 字段）；专项通过；全量 `Ran 755 tests ... OK`（+1）；服务已重启。
- 验收：服务端 `/tts/test` 返回 `ok: True`，合成 66KB、1.3 秒——火山 TTS 演示链路可用（设置面板测试按钮同路径）。
## 2026-08-17 本轮维护记录：火山 TTS 仅女声 + 头像开机动画误导修复
- 女声：试听确认 BV001_streaming 为女声、BV002_streaming 实为男声；PROVIDERS 火山音色精简为仅 BV001（设置面板只剩一个女声选项）；`tts_voice` 固定 BV001。
- 头像误导：`web/frontend/avatar.js` 开机自动播"正在聆听"动画（实未开麦克风），用户误以为自动识别；已删除该动画，头像默认"准备就绪"，仅主动进入通话/识别时才变 listening。
- 验证：node --check + 编码体检通过；全量 `Ran 755 tests ... OK`；静态文件改动浏览器强刷生效（无需重启）。
## 2026-08-17 本轮维护记录：通话模式"正在准备语音引擎"误提示修复
- 现象：每次点"通话"都闪"正在准备语音引擎…"，用户误以为模型每次点击都要重新加载。
- 根因：`phone_call.js` startCall 无条件显示准备提示并调 /asr/warmup（幂等秒回）——即使模型已加载也闪提示。
- 修复：先查 /asr/status，仅模型未加载时才提示"首次使用正在加载语音模型，约需 1 分钟…"并预热；已加载直接进通话。node --check + 编码体检通过；静态文件强刷生效。
## 2026-08-17 本轮维护记录：通话中"开口头像不切回聆听"修复
- 现象：回答播放完后头像归位"准备就绪"（local_tts 正常行为），但用户接着说第二句时，handleFrame 检测到声音却未把头像切回"正在聆听"，头像停留在"准备就绪"。
- 修复：`phone_call.js` handleFrame 开口瞬间（speechFrames 由空变非空）补 `setAvatar('listening')`；与 barge-in 打断同点。node --check 通过；静态文件强刷生效。
## 2026-08-17 本轮维护记录：通话中头像"聆听不持续"修复
- 现象：回答播完后头像归位"准备就绪"，等待下一句时不再显示"正在聆听"。
- 根因：`local_tts.js` 播放完/stopSpeech 无条件 `avatar('idle')`；`phone_call.js` 识别失败也 `setAvatar('idle')`——通话模式进行中不该归位。
- 修复：`local_tts.js` 新增 `isCallActive()`（查 #sh-call.active）+ `settleAvatar()`，通话激活时回"正在聆听"、否则"准备就绪"；`phone_call.js` 识别失败改回"正在聆听"（继续监听等待重试）。node --check 通过；静态文件强刷生效。
## 2026-08-17 本轮维护记录：头像加语音播报开关（TTS 一键开/关）
- 需求：小科头像处加"触发/关闭 TTS"按钮，演示现场一键静音/恢复，无需进设置面板。
- 实现：`avatar.js` 头像左上角加 🔊/🔇 圆钮（点击切 `window.ttsMuted`，localStorage 持久化，stopPropagation 防误触通话）；`local_tts.js` addToQueue 与 `speak.js` speak 开头检查 `ttsMuted` 直接跳过播报。node --check 三个文件通过；静态文件强刷生效。
## 2026-08-17 本轮维护记录：桌面版对话回答朗读断链修复 + 默认开启
- 现象：打字对话时回答不朗读（用户"没听到回答朗读"）。
- 根因：`streaming_chat_v2.js` 朗读判断只看被隐藏的 `#auto-speak` 复选框（默认未勾选），设置面板的 `tts_enabled` 未接入朗读判断——开关断链。
- 修复：`streaming_chat_v2.js` 新增 `shouldSpeak() = autoSpeak.checked || window.ttsEnabled`，页面加载读 `/settings` 初始化 `window.ttsEnabled`；`tts_settings.js`/`settings.js` 保存后同步 `window.ttsEnabled`；`settings.json` `tts_enabled` 默认置 true。
- 验证：node --check 三文件通过；后端 `/settings` 确认 tts_enabled=True、provider=volcano；服务已重启。
## 2026-08-17 本轮维护记录：火山音色列表补全（23 个中文女声/童声，自由选择）
- 需求：用户要"多搞一些音色自由选择"；官方列表中文女声众多（免费 21 款内为主）。
- 修复：`web/tts_providers.py` volcano 音色从 1 个补全到 23 个（通用女声/BV001·2.0、灿灿/BV700·2.0、炀炀、甜美小源、亲切/知性/活泼女声、梓梓、清新文艺、温柔淑女、甜宠少御、古风少御、新闻/促销/鸡汤女声、解说小美、直播一姐、知性姐姐、小萝莉、天才童声）；修正 BV002 为男声（此前误标）。
- 验证：/tts/providers 返回 23 个；全量 `Ran 755 tests ... OK`；服务已重启。用户可在设置面板自由切换试听。
## 2026-08-17 本轮维护记录：通话模式噪音误触加固（能量 VAD 四项防御）
- 现象：环境噪音导致 ASR 误触发严重（用户报障）。
- 修复（`phone_call.js` 纯前端）：① 阈值下限 0.005→0.008、上限 0.022→0.03；② 滞后回滞（hysteresis）——未开始语音需 >1.2×阈值才触发、已进入语音按 0.85×保持，抗噪音突刺与句中断音；③ 静音约 3 秒自动重新校准噪音基线（环境变化自适应），校准期间不再 return（防重校准漏话）；④ MIN_SPEECH_SEC 0.45→0.6 秒，短噪音不送识别。
- 验证：node --check 通过；静态文件强刷生效。
## 2026-08-18 本轮维护记录：web 版关闭模型思考模式（与终端版对齐，提速）
- 需求：小科 web 版调 DeepSeek 时思考模式未关——回复前先等一大段推理，界面出现 `[[LABTHINK]]` 折叠块；要像终端版一样关掉以提速。
- 现状核对：终端版 `src/llm/client.py` 第 282 行已显式 `"thinking": {"type": "disabled"}`；web 版三处调用（`web/agent/core.py` 第 83/112 行 agent 非流式+流式、`web/llm_bridge.py` 第 57 行统一理解链）均未传 thinking 参数 → 模型按默认开启思考。
- 改动：三处 `client.chat.completions.create(...)` 各加 `extra_body={"thinking": {"type": "disabled"}}`（OpenAI SDK 的非标准字段必须走 extra_body），与终端版请求体一致；每处 1 行参数，可随时回退。
- 测试：全量 `Ran 796 tests ... OK`（PYEXIT=0）；test_web_agent_prompts / test_web_llm_bridge 未断言调用参数，不受影响。
- 待验（真实验收）：重启 web 后发一条消息，确认不再出现 `[[LABTHINK]]` 折叠块、回复明显变快（REAL_OK 待用户实测，UX_CONFIRMED 待用户裁决）。
- 风险备注：若在设置面板切换为「中科大校内 LLM」（api.llm.ustc.edu.cn），该代理不保证支持 thinking 字段，届时需评估；当前 DeepSeek 官方接口（api.deepseek.com）与终端版实证兼容。

## 2026-08-20 本轮维护记录：Phase C1/C2a 三张嘴收敛 + 词在后端（voice_text）
- 背景：Phase C 语音收敛。风险 B = 三张嘴（`local_tts.js` / `speak.js` / `mobile.js` 各自 fetch `/tts` 发声），谁后加载谁占 `window.speak`，打断时 `stopSpeech` 停错对象 → barge-in 失灵。
- C1 三张嘴收敛：`speak.js` 整段重写为薄适配层（`labSpeak`/`labSpeakStop`/`labSpeakMessages` 委托 `window.speak`/`window.stopSpeech`）；`mobile.html` 加载 `local_tts.js`；`mobile.js` 删局部 `speak`、追问改调 `window.speak`；`local_tts.js` 补浏览器兜底 + status 空安全。打断现停得住唯一那张嘴。
- C2a 词在后端：`src/core/presentation_copy.py` 的 `copy_for_intent(..., voice=True)` + `_copy_clarification` voice 分支返回纯问题（去"小科："前缀、去来源标注）；`web/web_renderer.py` `render()` 多产出 `voice_text`；前端 `speak.js`/`mobile.js` 改读 `voice_text`、删 `.replace(/^小科：/,'')`。
- 测试：新增 4 项 voice 测试（`test_presentation_copy.py` 3 项 + `test_web_renderer.py` 补断言），全量 800 → 804 项通过。
- 登记：`PROJECT_ARCHITECTURE.md` §5.3 增 VOICE-MOUTH-01（三张嘴收敛）+ VOICE-TEXT-01（voice_text）；`VOICE_WEB_MIGRATION_PLAN.md` C1/C2a 勾选、C2b 暂缓到 Phase D。
- 待验（C3 真机，需用户设备）：外放/耳机分别测 barge-in 漏检/自激；追问念出来是纯问题（无"小科"）；打断能停住。REAL_OK/UX_CONFIRMED 待用户实测裁决。

## 2026-08-20 本轮维护记录：P0 复合确认+实体（CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01）REAL_OK
- 根因：确定性解析器把"是的，是X"短路成 AFFIRM→CONFIRM，`confirm_clarification` 只清标志、不抽实体，`remaining_fields` 留 `[amount_value, amount_unit]`。
- 修复（集合 + 混合方案）：
  ① 意图层定义"回答类命令集合" `{affirm, deny, targeted_answer}` 放行 `supplied_entities`（`unified_prompts.py` + `unified_understanding.py`）；
  ② 动作层定义"回答类动作集合" `{ANSWER, CONFIRM, REJECT_SUGGESTION}` 放行 `supplied_entity_fields`（`clarification_acceptance.py`）；
  ③ 状态机 `confirm_clarification` 加可选 `supplied_fields`（先填再确认，原子）；
  ④ 执行器 CONFIRM/REJECT 配实体提取器时从 `answer_text` 抽实体（混合：确定性判"确认/否定"、LLM 抽实体）；
  ⑤ `interaction_command.py` 的 `AFFIRM_PREFIXES` 恢复 ("是的","没错","确认")、`DENY_PREFIXES` ("不是","不对","错误")——比原"是的是"宽，能抓"是的，50微升"。
- 测试：+4（3 项 ConfirmWithEntitiesTests + 1 项确定性确认抽实体），全量 804 → 808。
- 真实验收（REAL_OK，会话 20260820_122234）："是的，50微升" → 已确认问题 2，并填入实体字段 `['amount_unit','amount_value']`，问题已解决（debug.log 第 619 行）。
- 遗留：ASR 把"是的"听成"日的"（口述 2）→ 属 ASR-CMD-02 线，非 P0；LLM 弃权时 no_action 沉默 → `PRESENT-NOACTION-FEEDBACK-01`（顺带发现）。

## 2026-08-23 本轮维护记录：语音 Web 路线重排（27 项 → 35 项）

- 原因：此前临时 27 项只覆盖“播什么”和入口融合，遗漏“何时播”的独立播放许可层，也把延后、过期、替代、取消、抢占和 TTS 失败边界压进了笼统任务。
- 修正：`PROJECT_TASK_CHECKLIST.md` §3/§3.1-VOICE 与 `VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` §4.0 同步登记 35 个任务 ID；两份文档的任务集合、顺序和状态一致。
- 当前唯一下一项：`VOICE-C5-B1-PLAYBACK-REQUEST-CONTRACT`；只定义带重要性和生命周期信息的播放请求，不实现门控、不接前端、不修改 tool/chat。
- 验证：只读脚本提取两份文档任务 ID，均为 35 个唯一 ID，`ONLY_CHECKLIST` 与 `ONLY_MIGRATION` 均为空。
- 证据边界：本轮只更新计划和任务状态，没有修改业务代码，因此未改变 808 项历史全量测试基线，也不产生新的 AUTO_OK/REAL_OK 结论。

## 2026-08-23 本轮维护记录：VOICE-C5-B1 播放请求合同

- 新增不可变 `PlaybackRequest`，携带意图、业务重要性、语音正文、带时区创建时间、正数 TTL 和可选替代键；`expires_at` 为纯计算属性。
- `VoiceDeliveryItem` 增加 `priority`，由 `PresentationIntent.priority` 原样传入；内容计划仍不读取麦克风、ASR、TTS 或会话状态，也不产生播放决定。
- `PlaybackRequest.from_delivery_item()` 明确成为内容资格进入播放层时补充生命周期信息的唯一合同入口；本项没有实现 Gate、队列、前端接线或工具改造。
- 专项回归：`tests.test_playback_request + test_presentation_delivery + test_voice_delivery + test_web_stream_contract` 共 `21/21` 通过。
- 全量尝试：备用 Python 发现 689 项并报 31 个错误，主要因缺少 `dotenv/fastapi/httpx` 等项目依赖；其中本次签名变化暴露的 4 个 SSE 测试错误已修复并纳入 21 项通过证据。故本项标 `AUTO_OK` 仅限合同相关自动验收，不声称全量或真实设备通过。
- 当前唯一下一项：`VOICE-C5-B2-PLAYBACK-CONTEXT-CONTRACT`。

## 2026-08-23 本轮维护记录：VOICE-C5-B2 播放上下文合同

- 新增不可变 `PlaybackContext`：同一快照包含带时区观察时间、用户是否讲话、ASR 是否收音、TTS 是否播放和高层会话阶段。
- 新增 `PlaybackSessionPhase`：`INACTIVE / ACTIVE / CLOSING / ENDED`；不复用混合设备活动的 `AssistantState`，避免阶段与讲话/收音/播放字段语义重复。
- 快照允许 `user_speaking=True` 与 `tts_playing=True` 同时存在，以忠实表达 barge-in 刚发生、旧播放尚未停止的瞬间；是否抢占留给后续规则。
- 合同严格拒绝无时区时间、整数冒充布尔值及原始字符串冒充阶段枚举；没有启动、停止、播放、入队或决定 API。
- 专项回归：播放上下文、播放请求、DeliveryPlan、语音预算与 SSE 合同共 `28/28` 通过。本项未接真实前端或设备，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-B3-PLAYBACK-DECISION-CONTRACT`。

## 2026-08-23 本轮维护记录：VOICE-C5-B3 播放决定合同

- 新增 `PlaybackDisposition`，固定四种互斥结果：`READY / DEFERRED / DROP / PREEMPT`。
- 新增稳定 `PlaybackReason`：可播放窗口；用户讲话、ASR 收音、TTS 占用、会话未激活；过期、被替代、会话结束、上下文失效；CRITICAL 抢占低优先级。
- 新增不可变 `PlaybackDecision`，严格校验原因所属结果，拒绝 `READY + EXPIRED` 等语义矛盾组合；`as_dict()` 输出稳定小写协议值。
- 测试证明全部原因码各自只被一种结果接受；决定对象没有播放、停止、入队或执行 API。本项只定义结果合同，尚未根据请求和上下文产生决定。
- 专项回归：播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `33/33` 通过。本项未接真实前端或设备，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-B4-PRIORITY-TIMING-RULES`。

## 2026-08-23 本轮维护记录：VOICE-C5-B4 重要性与播放时机纯规则

- 新增纯函数 `decide_playback(PlaybackRequest, PlaybackContext) -> PlaybackDecision`；不读取当前时钟，使用快照的 `observed_at`，不修改请求、上下文或外部状态。
- 规则顺序固定：会话结束 → 过期 → 无语音资格优先级 → 会话阶段 → 用户讲话 → ASR 收音 → TTS 占用/限定抢占 → 空闲可播。
- 非 CRITICAL 不覆盖用户口述或 ASR 收音；`ROUTINE / DEBUG` 丢弃；收尾阶段只允许 `CRITICAL / SUMMARY`；过期边界使用 `observed_at >= expires_at`。
- 为安全抢占补充 `PlaybackContext.active_tts_priority`：当前 TTS 优先级可未知；仅 CRITICAL 且已知当前项更低时返回 PREEMPT，未知或同级时返回 `DEFERRED/TTS_BUSY`，避免误停安全提示。
- 专项回归：纯规则、播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `47/47` 通过。本项没有播放、停止、排队或前端接线，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-C1-PLAYBACK-GATE`。

## 2026-08-23 本轮维护记录：VOICE-C5-C1 无副作用 PlaybackGate

- 新增 `PlaybackGate.evaluate(PlaybackRequest, PlaybackContext) -> PlaybackDecision`，作为后续调度器和多入口应依赖的稳定门控边界。
- Gate 只做合同类型检查并委托唯一 `decide_playback()` 规则函数，不复制业务判断；相同不可变输入重复调用得到相同决定。
- `PlaybackGate` 使用空 `__slots__`，不持有运行时状态；没有 queue/deferred/play/stop/enqueue/cancel 等调度或设备 API。
- 专项回归：Gate、纯规则、播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `51/51` 通过。本项未保存 DEFERRED 项、未调用真实 TTS 或接前端，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-C2-DEFERRED-QUEUE`。

## 2026-08-23 本轮维护记录：VOICE-C5-C2 延后语音队列

- 新增不可变 `DeferredPlaybackEntry`，保存原 `PlaybackRequest` 和导致延后的 `PlaybackDecision`，便于后续重新判断时保留来源证据。
- 新增线程安全 FIFO `DeferredPlaybackQueue`：`defer()` 只接受 DEFERRED，`snapshot()` 只读且不移除，`take_next()` 取出最早项，空队列返回 None。
- 同一 `intent_id` 在队列中只能出现一次，避免重复触发产生双重朗读；取出后可按新上下文重新延后。非法决定写入失败且不改变队列。
- 队列没有 play/speak/stop 或自动评估能力；本项未实现状态变化触发、过期清理、问题替代、会话取消和真实 TTS。
- 专项回归：延后队列、Gate、纯规则、播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `57/57` 通过，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-C3-REEVALUATION-TRIGGERS`。

## 2026-08-23 本轮维护记录：VOICE-C5-C3 状态变化重新判断

- 新增 `ReevaluationTrigger`：`USER_STOPPED_SPEAKING / VOICE_INPUT_BECAME_IDLE / TTS_PLAYBACK_ENDED`；触发器必须与新快照对应字段为 False 一致，否则在队列变化前失败。
- 新增 `reevaluate_deferred()`：只处理调用开始时已在队列中的项目，防止仍为 DEFERRED 的项目本轮重新入队后被无限循环评估。
- 每项通过唯一 `PlaybackGate.evaluate()` 重新判断；仍 DEFERRED 的携带新原因回队尾，READY/DROP/PREEMPT 离队并通过不可变 `ReevaluationOutcome/Batch` 返回调用方。
- Fake 状态转换证明：用户停说可恢复 READY；ASR 结束但 TTS 忙会继续延后并更新原因；TTS 结束按 FIFO 释放全部已有项目；空队列安全返回空批次。
- 专项回归：重新判断、延后队列、Gate、纯规则、播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `63/63` 通过。本项未执行真实播放、专门过期清理、问题替代或会话取消，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-C4-EXPIRY-DROP`。

## 2026-08-23 本轮维护记录：VOICE-C5-C4 超期丢弃

- 新增 `drop_expired(DeferredPlaybackQueue, observed_at=...)`，时间由调用方显式传入且必须带时区，不读取隐藏系统时钟，便于 Fake 时间确定性验收。
- 判定边界与 Gate 一致：`observed_at >= request.expires_at` 即生成 `DROP/EXPIRED`，从延后队列永久移出并通过不可变 `ExpiredPlayback/ExpirySweep` 返回证据。
- 扫描只处理开始时已有项目；未过期项携带原延后决定重新入队，混合队列中的幸存项目保持原 FIFO 顺序和原因。
- 测试覆盖到期前保留、精确边界丢弃、多个过期与幸存项混排、空队列及无时区时间失败且队列不变；扫描结果没有播放、重试或入队执行 API。
- 专项回归：过期扫描、重新判断、延后队列、Gate、纯规则、播放决定、上下文、请求、DeliveryPlan、语音预算与 SSE 合同共 `69/69` 通过。本项未处理问题替代、会话取消或真实 TTS，不产生 REAL_OK 结论。
- 当前唯一下一项：`VOICE-C5-C5-SUPERSEDE`。

## 2026-08-23 本轮维护记录：全量测试环境误判纠正（用户要求固化）

- 错误过程：受限执行中项目 `.venv` 命令未能创建进程后，agent 错误表述为 Python 启动器失效；随后又用另一套 Python 混载 `.venv` 包，触发 `pydantic_core` 二进制扩展不兼容。两者都不能证明项目环境有问题。
- 正确复验：在获准的非受限环境执行项目原命令 `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`，结果 `Ran 889 tests in 7.864s — OK`。
- 永久规则已写入 `CLAUDE.md`：受限环境启动失败先按沙箱限制重试；不得据此诊断 `.venv` 损坏/失效；不得用解释器混载代替正式全量。2026-08-23 用户进一步校准：测试按风险选择，局部内部改动跑专项与相邻回归，共享边界/主流程/阶段收口再跑全量；必须如实说明是否运行全量。
- 当前可信基线：VOICE-C5-C4 专项 `69/69`，全量 `889/889`；没有测试失败，已有 FastAPI/Starlette 弃用警告和损坏 JSON 测试样例警告不影响通过结论。

## 2026-08-23 本轮维护记录：VOICE-C5-C5 新追问替代旧追问

- 新增 `supersede_deferred()`：以新请求的非空 `supersession_key` 为上下文身份，移除队列内全部同 key 旧请求，并为每项返回 `DROP/SUPERSEDED` 证据。
- 无关 key 项保持原 FIFO 顺序与原延后原因；新请求携带 DEFERRED 决定追加到队尾；没有旧匹配时退化为普通入队。
- 为避免半完成状态，缺 key、非 DEFERRED 决定和重复 replacement intent_id 全部在扫描前校验，失败时队列完全不变。
- 验证：播放层专项 `76/76`；项目原 `.venv` 全量 `896/896`，无失败。已有弃用/损坏 JSON 样例警告不影响通过结论。
- 当前唯一下一项：`VOICE-C5-C6-SESSION-CANCEL`。

## 2026-08-23 本轮维护记录：VOICE-C5-C6 会话结束永久取消

- `DeferredPlaybackQueue` 新增关闭生命周期：`close()` 在同一把锁中标记 closed、按 FIFO 取出全部项目并清空 intent 集合；`is_closed` 可只读检查。
- 新增 `cancel_deferred_for_session()`：把关闭时剩余项目逐一映射为 `DROP/SESSION_ENDED`，返回不可变证据，不执行播放。
- 关闭后的迟到 `defer()` 以 RuntimeError 拒绝，防止旧会话结束后被异步事件重新复活；重复取消幂等，第二次返回空结果，队列无法 reopen。
- 测试策略按用户校准改为风险选择：本轮仅改播放层内部队列生命周期，运行会话取消及全部相邻播放模块回归 `82/82`；未运行全量，最近可信全量基线仍为 `896/896`。
- 当前唯一下一项：`VOICE-C5-C7-PREEMPTION`。

## 2026-08-23 本轮维护记录：播放执行架构纳入唯一清单

- 按用户确认，把 Microphone、VAD、ASR、VoiceStateCoordinator、PlaybackContextFactory、PlaybackGate、DeferredPlaybackQueue、PlaybackScheduler、TTSAdapter 的职责边界正式写入迁移计划。
- 原 35 项扩展为 39 项；在抢占之前插入 4 个架构落地项：运行状态协调器、播放上下文工厂、播放调度器、TTS 适配器事件合同。原后续任务顺延但任务 ID 和业务范围不变。
- 固定短停顿语义：`user_speaking=False` 不等于可以播放；只要 `segment_capturing=True`，仍处于同一口述段，PlaybackGate 必须继续阻止插话。
- 固定单一权威：VoiceStateCoordinator 是运行状态唯一写入者，PlaybackScheduler 是 Gate/Queue/TTS 的唯一编排者；TTSAdapter 只执行并报告 `STARTED / FINISHED / STOPPED / FAILED`。
- 本轮只改计划与设计文档，完成 39 项数量、唯一性、顺序一致性和格式校验；未改业务代码，未运行代码回归。
- 当前唯一下一项：第 11 项 `VOICE-C5-C7-RUNTIME-STATE-COORDINATOR`。

## 2026-08-23 本轮维护记录：VOICE-C5-C7 运行状态协调器

- 新增不可变 `VoiceRuntimeState`，独立保存 `user_speaking / segment_capturing / asr_processing / tts_playing / active_tts_priority`，拒绝“讲话但未采集”和 TTS 优先级残留等矛盾状态。
- 新增 `VoiceRuntimeEventType` 与严格 `VoiceRuntimeEvent`；`VoiceStateCoordinator.consume()` 在锁内先归约、成功后才替换状态，是唯一可变状态写入边界。
- 短停顿只清除 `user_speaking`，保留 `segment_capturing`；继续讲话复用同一片段，只有 `SEGMENT_FINALIZED` 才结束采集。ASR 成功/失败和 TTS FINISHED/STOPPED/FAILED 都会清除对应活动事实。
- 非法事件顺序抛错且旧状态对象不变；Coordinator 没有录音、转写、播放、停止、上下文创建、播放决定或入队 API。
- 验证：修改前相邻播放层 `56/56`；新增专项 `13/13`；新模块及相邻播放层组合回归 `69/69`。按风险未跑全量，最近可信全量仍为 `896/896`。
- 纯内部状态合同，无用户可见输出变化，跳过 UX Walkthrough；未接真实设备，不产生 REAL_OK 或 UX_CONFIRMED。
- 当前唯一下一项：第 12 项 `VOICE-C5-C8-PLAYBACK-CONTEXT-FACTORY`。

## 2026-08-23 本轮维护记录：VOICE-C5-C8 播放上下文工厂

- 新增 `PlaybackContextFactory`，依赖注入 `VoiceStateCoordinator` 与时钟；每次 `create()` 只读取一次运行状态和一次时间，产出既有不可变 `PlaybackContext`。
- 兼容映射固定为 `voice_input_busy = segment_capturing or asr_processing`：用户句中停顿和固化片段转写期间都保持输入忙，避免普通语音插话。
- 用户讲话、TTS 播放和当前 TTS 优先级原样复制；会话阶段由调用方显式传入。运行状态后来变化不会反向修改旧快照。
- 工厂没有状态写入、决定、排队、播放、停止或转写 API；无时区时钟结果继续由 `PlaybackContext` 合同拒绝。
- 验证：新增专项 `10/10`；工厂、运行状态及相邻播放层组合回归 `79/79`。本轮按风险未跑全量，最近可信全量仍为 `896/896`。
- 纯内部快照适配，无用户可见输出变化，跳过 UX Walkthrough；未接真实设备，不产生 REAL_OK 或 UX_CONFIRMED。
- 当前唯一下一项：第 13 项 `VOICE-C5-C9-PLAYBACK-SCHEDULER`。

## 2026-08-23 本轮维护记录：VOICE-C5-C9 播放调度器

- 新增 `PlaybackExecutionPort` 最小协议、`PlaybackScheduleAction/Result` 不可变证据和唯一编排入口 `PlaybackScheduler`。
- `schedule()` 固定顺序：ContextFactory 创建一次快照 → Gate 判断一次 → 四种 disposition 各走唯一分支。READY 只交给 play；DEFERRED 只入队；DROP 只返回证据；PREEMPT 只返回 `PREEMPT_REQUIRED`。
- PREEMPT 本轮刻意不调用 stop/play：尚无 STOPPED 事件和复判闭环，提前播放会与旧音频重叠；留给第 14、15 项完成。
- 队列关闭时不播放；Fake TTS 抛错时不返回 `HANDED_TO_TTS`，避免把调用失败伪装成成功。本轮不实现重试，失败隔离仍属于第 16 项。
- 验证：新增专项 `8/8`；Scheduler 及全部相邻播放模块组合回归 `87/87`。本轮按风险未跑全量，最近可信全量仍为 `896/896`。
- 纯内部编排合同，无用户可见输出变化，跳过 UX Walkthrough；Fake 执行端口不产生 REAL_OK 或 UX_CONFIRMED。
- 当前唯一下一项：第 14 项 `VOICE-C5-C10-TTS-ADAPTER-EVENTS`。

## 2026-08-23 本轮维护记录：VOICE-C5-C10 TTSAdapter 执行事件合同

- 新增 `TTSExecutionEventType/Event`：四类互斥事件均携带 `intent_id` 与优先级，FAILED 必须携带非空错误，其他事件禁止错误字段。
- 新增低层 `TTSDriver` 协议与 `TTSAdapter`。Adapter 只暴露 `play/stop` 执行命令；Driver 信号经 Adapter 校验、绑定当前请求后，转换为 Coordinator 的 TTS 运行事件并报告给 event sink。
- 命令和事实分离：调用 play 后仍未播放，收到 STARTED 才设置 `tts_playing=True`；调用 stop 后仍保持播放事实，收到 STOPPED 才清除。FINISHED/FAILED 同样清除活动播放。
- 终止事件必须对应已 STARTED 请求；待启动或播放中拒绝第二次 play；未 STARTED 禁止 stop。Adapter 结构上满足 Scheduler 的 `PlaybackExecutionPort`。
- 验证：新增专项 `9/9`；Adapter、Scheduler、Coordinator 及全部相邻播放模块组合回归 `96/96`。本轮按风险未跑全量，最近可信全量仍为 `896/896`。
- 纯 Fake Driver 内部合同，无真实声音和输出面变化，跳过 UX Walkthrough；不产生 REAL_OK 或 UX_CONFIRMED。
- 当前唯一下一项：第 15 项 `VOICE-C5-C11-PREEMPTION`。

## 2026-08-23 本轮维护记录：VOICE-C5-C11 CRITICAL 限定抢占

- 扩展 Scheduler 执行端口为 `play/stop`；PREEMPT 动作改为 `PREEMPT_STOP_REQUESTED`，明确只代表停止命令已发出，不代表抢占完成。
- Scheduler 通过 TTS 事件保存当前 STARTED `intent_id`；PREEMPT 时原子保存待抢占请求及被停止 intent。未观察到 STARTED 身份时安全拒绝，不盲停未知播放。
- 只有匹配被停止 intent 的 STOPPED 才恢复流程；错误 intent 的 STOPPED 被忽略且不释放待抢占请求。恢复时使用新时钟和事件接线提供的当前会话阶段重新创建上下文并调用 Gate。
- 复判 READY 才 play；等待期间到期或会话结束会 DROP。普通请求在 TTS busy 时只 DEFERRED，同级 CRITICAL 同样不抢占。
- 验证：抢占、Scheduler、Adapter 直接相关测试 `22/22`；新增 6 项抢占测试后全部播放层组合回归 `102/102`。本轮按风险未跑全量，最近可信全量仍为 `896/896`。
- Fake Driver 证明软件顺序和身份匹配，不证明真实播放器停止时延；无输出面变化，跳过 UX Walkthrough，不产生 REAL_OK/UX_CONFIRMED。
- 当前唯一下一项：第 16 项 `VOICE-C5-C12-TTS-FAILURE-BOUNDARY`。

## 2026-08-23 本轮维护记录：VOICE-C5-C12 TTS 失败隔离与阶段收口

- 新增线程安全 `TTSFailureBoundary`、失败阶段枚举及不可变 `TTSFailureRecord/TTSStartOutcome`，集中保存启动命令、活动播放、事件交付三类失败证据。
- 仅 `START_COMMAND` 允许自动重试，默认最多重试 1 次（总尝试 2 次）；最终失败由 Scheduler 返回 `PLAYBACK_FAILED`，携带最后失败证据和原请求，不伪造 `HANDED_TO_TTS`。
- STARTED 后的 FAILED 不自动重播，避免用户已听到部分内容后重复；Coordinator 先清除播放事实，再由 Scheduler 记录失败。event sink 异常由 Adapter 隔离并记录，不回滚已确认的运行事实，也不重播。
- 测试证明永久启动失败严格停止在两次、瞬时失败可在唯一重试成功、播放中失败只调用一次 play、失败结果仍保留原 `voice_text`。本层从不删除或改写屏幕交付对象。
- 验证：失败边界及直接相邻模块 `23/23`；全部播放层组合回归 `108/108`；因第 1–16 项播放架构阶段收口和共享结果合同变化，运行项目原 `.venv` 全量 `954/954` 通过。
- 全量存在既有 FastAPI/Starlette 弃用警告和损坏 JSON 测试样例警告，无测试失败。Fake 边界不证明真实供应商恢复能力；无输出面变化，跳过 UX Walkthrough，不产生 REAL_OK/UX_CONFIRMED。
- 当前唯一下一项：第 17 项 `VOICE-C5-D1-SHARED-RECORD-SERVICE`。

## 2026-08-23 本轮维护记录：播放输入忙字段统一命名

- `PlaybackContext.asr_listening` 无兼容双名改为 `voice_input_busy`；它不是单独的 ASR 状态，而是播放门控使用的“语音输入链仍忙”派生事实。
- `PlaybackContextFactory` 继续使用 `segment_capturing or asr_processing` 生成该字段；两个细粒度运行事实没有合并或删除。
- `PlaybackReason.ASR_LISTENING` 改为 `VOICE_INPUT_BUSY`，`ReevaluationTrigger.ASR_LISTENING_ENDED` 改为 `VOICE_INPUT_BECAME_IDLE`；源码、测试和文档统一使用同一术语。
- 本次为纯命名迁移，不改变业务判断和用户可见输出。

## 2026-08-23 本轮维护记录：VOICE-C5-D1 共享记录应用服务

- 新增 `web/record_service.py`：`RecordCommand` 表达入口无关输入，`SharedRecordService` 统一执行会话/段号、最近上下文、LLM 抽取、规则兜底、确定性评估、落盘、共享结果与语义意图投影。
- 新增不可变 `SharedRecordResult`，只携带 `saved_record / observation_result / intents`；服务不依赖 FastAPI、WebRenderer、麦克风或播放 Scheduler，输出停在 `PresentationIntent`。
- 顺序证据：evaluate 在 save 前，request_id 与投影在 save 后。保存失败转换为 `RecordPersistenceError`，且不会请求投影 ID，因此没有生成成功或追问意图。
- LLM 失败保留错误证据并走规则抽取；最近上下文按旧到新传递；降级记录成功保存后产生 RECORD_ACK 意图。
- 验证：新增专项 `7/7`；共享结果、投影、降级生产者、WebRenderer 和现有 `/record` 相邻回归 `65/65`。本轮未改入口，按风险未跑全量，最近可信全量 `954/954`。
- 当前是过渡状态：新服务可用但旧 `/record` 尚未迁移，存在临时重复编排；第 18 项必须切换并删除旧路，登记职责迁移对照。无用户可见输出变化，跳过 UX Walkthrough。
- 当前唯一下一项：第 18 项 `VOICE-C5-D2-RECORD-USE-SERVICE`。

## 2026-08-23 本轮维护记录：VOICE-C5-D2 `/record` 迁移共享服务

- `web/api/record.py` 的 `record()` 删除内联最近上下文、LLM/规则抽取、评估、保存、成功结果适配和意图投影；改为构造 `RecordCommand` 并调用 `SharedRecordService.record()`。
- 路由现只负责四件事：HTTP 空输入校验、Web/数据库依赖绑定、`RecordPersistenceError` 映射为 HTTP 500、用 WebRenderer 把共享 intents 转为旧响应 messages。
- `_save_record_locked()` 保留既有存储锁但作为注入依赖，服务不认识锁或 SQLite。响应从 `saved_record` 复制后才附加 messages，因此 messages 继续不入库。
- 旧路→新路职责迁移登记为 `PROJECT_ARCHITECTURE.md` §5.3 `RECORD-SERVICE-01`；自动合同质量为等价，真实浏览器 UX 待用户裁决。
- 验证：共享服务与路由直接测试 `16/16`；记录结果、投影、Renderer、手机页相邻回归 `71/71`；因修改桌面/手机共用 HTTP 边界并删除旧路，项目原 `.venv` 全量 `961/961` 通过。
- 既有 FastAPI/Starlette 弃用和损坏 JSON 样例警告不影响通过。未接真实浏览器或 Scheduler，不产生 REAL_OK/UX_CONFIRMED。
- 当前唯一下一项：第 19 项 `VOICE-C5-D3-TOOL-USE-SERVICE`。

## 2026-08-23 本轮维护记录：VOICE-C5-D3 工具迁移共享服务

- `web/lab_tools.py` 的 `record_observation` 删除内联规则抽取、确定性评估、段号分配与保存，改为构造 `RecordCommand` 并调用 `SharedRecordService.record()`。
- 工具适配层继续只返回原合同的 `transcript / entities / missing_fields / follow_up_question / deviations`；共享服务产生的 intents 尚未交给工具呈现链，避免提前进入第 20 项。
- 保存或服务失败仍由既有 `lab_tools.call()` 捕获并返回 `{ok: false, error}`，不会伪造成功结果。
- 新增工具专项测试覆盖共享服务调用、合同兼容和失败边界；专项与记录/呈现相邻回归 `104/104` 通过，`git diff --check` 通过。
- 环境说明：项目 `.venv` 的 Python 启动器仍指向已不存在的 Python 3.11；使用工作区 Python 加载其 site-packages 时，编译版 `pydantic_core` 与 Python 3.14 ABI 不兼容，因此本轮无法可信重跑全量。该环境问题不计作代码测试失败。
- 当前唯一下一项：第 20 项 `VOICE-C5-D4-TOOL-PRESENTATION`。

## 2026-08-23 本轮维护记录：VOICE-C5-D4 工具确定性呈现

- `web/lab_tools.py` 新增内部 `PresentedToolResult`：保持工具原五字段 payload，同时携带从共享 intents 构建的 `PresentationDeliveryPlan`；`lab_tools.call()` 只对支持呈现的工具附加计划，其他工具合同不变。
- 新增 `web/tool_presentation.py`，只消费已构建计划并通过 `WebRenderer.render_plan()` 使用统一 copy 生成屏幕 payload 与确定性回复文本；不调用模型、不授予播放许可。
- `web/agent/core.py` 的同步与流式链新增 `_run_tool_with_presentation()`：公共 `run_tool()` 仍返回旧结果；记录工具成功时，整批同轮工具执行完后直接输出 copy 文案并结束，不再进行第二次模型补写。
- 自动测试证明 RECORD_ACK 继续默认语音静默，CLARIFICATION 的屏幕文案与纯问题 `voice_text` 来自同一 DeliveryPlan；同步/流式 agent 均只调用一次模型，且同轮后续工具不会被跳过。
- 验证：核心与记录/呈现相邻回归 `111/111`，流事件合同另跑 `7/7`；Python 编译检查与 `git diff --check` 通过。组合回归中的旧 `test_web_agent_prompts` 因 `.venv` 启动器失效、工作区 Python 3.14 与原 `pydantic_core` ABI 不兼容而无法导入，不计作业务断言失败，也不宣称全量通过。
- 本项仍通过现有普通 delta 把确定性文本送到浏览器；delta 的显式纯屏幕化、`voice_delivery` 事件和前端 TTS 直通删除分别留给第 21–23 项。
- 当前唯一下一项：第 21 项 `VOICE-C5-D5-CHAT-SCREEN-ONLY-DELTA`。

## 2026-08-23 本轮维护记录：VOICE-C5-D5 chat 正文纯屏幕事件

- `web/stream_contract.py` 新增 `agent_chunk_event()`：普通 assistant 文本统一映射为 `screen_delta_event()`，payload 只有 `type/text`，没有 `voice_text`、TTS 调用或播放决定。
- `web/api/chat.py` 的真实 `/chat/stream` 路由不再手写普通 `delta`，改为调用该合同构造器；用于思考行和工具卡片的 `[[LABTHINK]]/[[LABCARD]]` 暂留旧 `delta`，避免本项顺带设计新的控制事件。
- 实际页面加载的 `web/frontend/streaming_chat_v2.js` 新增 `screen_delta` 分支：只累积 answer、更新 `reply.textContent` 和滚动位置，不检查 TTS 开关、不调用 `enqueueSpeech/window.speak`。
- 旧 `delta` 分支及其中 `enqueueSpeech` 代码明确保留，等待第 23 项删除；本轮没有发送或消费 `voice_delivery`，没有接 PlaybackScheduler。
- 新增自动合同覆盖普通正文、控制标记、空输入、真实路由接线、前端 screen-only 分支和旧路径保留；记录/呈现/流事件组合回归 `124/124`，Python 编译、Node `--check` 与 `git diff --check` 通过。
- 自动证据不证明真实浏览器 SSE、工具卡片视觉或 TTS 真机行为；本项仅标 `AUTO_OK`。
- 当前唯一下一项：第 22 项 `VOICE-C5-D6-VOICE-EVENT-BACKEND`。

## 2026-08-23 本轮维护记录：VOICE-C5-D7 删除 delta TTS 旁路

- 按用户明确指示先实施第 23 项；第 22 项 `VOICE-C5-D6-VOICE-EVENT-BACKEND` 尚未完成，继续保持唯一 `NEXT`，没有把清单错误推进到第 24 项。
- `web/frontend/streaming_chat_v2.js` 删除旧 `delta` 普通文本分支中的 `shouldSpeak() / takeCompletedSentences() / enqueueSpeech()`；该分支继续处理 `LABTHINK/LABCARD` 控制标记并可显示兼容文本。
- 同步清理当前未加载但仍保留在仓库中的 `web/frontend/streaming_chat.js`，防止以后重新启用旧文件时恢复 `delta → enqueueSpeech` 旁路。
- 本轮没有改 `screen_delta`（本来就只上屏），没有删除 `task_queued → enqueueSpeech`（第 24 项），也没有接 `voice_delivery` 或 PlaybackScheduler。
- 测试同时证明活动 v2 与遗留版的 delta 分支仍含屏幕更新、但均不含 `enqueueSpeech/window.speak`；第 20–23 项相关组合回归 `125/125`，两份 JavaScript `node --check` 与 `git diff --check` 通过。
- 自动证据不能证明真实浏览器运行时或扬声器行为；且第 22 项尚缺，当前受控语音候选仍不会通过新事件播放。本项仅标 `AUTO_OK`。
- 当前唯一下一项仍为第 22 项 `VOICE-C5-D6-VOICE-EVENT-BACKEND`。

## 2026-08-23 本轮维护记录：VOICE-C5-D6 后端 voice_delivery 候选事件

- `web/tool_presentation.py` 新增不可变 `ToolVoiceDeliveryBatch`，只允许非空 `VoiceDeliveryItem`；新增 `merge_tool_plans()` 将同轮多个工具计划的全部 screen intents 合并后重新调用 `build_delivery_plan()`，避免每个计划分别享受语音预算而突破整轮 2 条/50 字/1 问上限。
- `web/agent/core.py` 的同步链继续只返回确定性屏幕文本；流式链先 yield 屏幕文本，再仅在合并计划存在 voice_items 时 yield 类型化语音批次。RECORD_ACK 等静默计划不产生空批次。
- `web/stream_contract.py` 新增 `agent_output_event()`，字符串继续映射为 screen/control 事件，类型化批次映射为 `voice_delivery_event()`；未知输出类型直接拒绝。
- `voice_delivery` payload 携带稳定 `intent_id/kind/priority/voice_text`，并新增顶层 `authorization: CONTENT_ELIGIBLE`。该值只表示通过内容政策，不等于 PlaybackGate 的 `READY/PREEMPT`；第 25 项前端不得把候选直接播放，运行时授权留给第 26 项。
- `web/api/chat.py` 识别类型化批次，独立发送 SSE 后立即 continue，因此 voice payload 不进入 `answer_parts`、不写入聊天历史，也不被包装成 `screen_delta`。
- 自动测试覆盖类型映射、稳定 ID、空批次拒绝、静默计划不发事件、同轮问题预算重算和未知类型拒绝；第 20–23 项相关组合回归 `130/130`，Python 编译与 `git diff --check` 通过。
- 本轮没有修改前端消费逻辑，所以真实页面会忽略该事件且不会播放；没有经过 Scheduler，不产生 READY/PREEMPT，不标 REAL_OK。
- 第 22、23 项现均为 `AUTO_OK`；当前唯一下一项：第 24 项 `VOICE-C5-D8-REMOVE-TASK-QUEUED-TTS`。

## 2026-08-23 本轮维护记录：VOICE-C5-D8 删除 task_queued TTS 旁路

- `web/frontend/streaming_chat_v2.js` 的 `task_queued` 分支删除 `shouldSpeak() → enqueueSpeech(answer)`；排队文案仍写入当前回复，conversation_id 仍保存，头像仍切到 listening，任务面板仍刷新。
- 同步清理未加载的遗留 `web/frontend/streaming_chat.js`，防止以后恢复旧客户端时重新获得 task_queued 发声旁路。
- `done` 分支的旧 speechBuffer 收尾和 `web/frontend/task_panel.js` 的后台任务完成/失败轮询播报均未修改；后者是另一条通知路径，不属于 task_queued 事件。
- 自动测试提取活动版与遗留版 task_queued 分支，证明保留屏幕/状态行为且不含 `enqueueSpeech/window.speak`；另有反向测试证明 task_panel 路径仍存在，守住本轮范围。
- 验证：针对性 `24/24`；第 20–24 项相关组合回归 `133/133`；两份 JavaScript `node --check` 与 `git diff --check` 通过。
- 本轮不消费 `voice_delivery`，不把 `CONTENT_ELIGIBLE` 当成播放许可，不接 Scheduler，不标 REAL_OK。
- 当前唯一下一项：第 25 项 `VOICE-C5-D9-FRONTEND-PLAYBACK-EVENT`。

## 2026-08-23 本轮维护记录：VOICE-C5-D9 前端授权播放边界

- 新增 `web/frontend/voice_delivery_client.js` 作为唯一事件消费适配器；`web/app.py` 在活动流式客户端之前加载它，活动与遗留客户端的 `voice_delivery` 分支都只委托 `window.consumeVoiceDelivery(data)`。
- 适配器先校验事件、稳定 intent 字段和非空 voice_text，再检查用户是否启用语音；`CONTENT_ELIGIBLE` 只返回 CANDIDATE_ONLY，DEFERRED/DROP/未知授权/坏 payload 均无 TTS 副作用。
- `READY` 才逐项调用唯一 `window.enqueueSpeech`；`PREEMPT` 才调用 `window.stopSpeech`，再用 `window.speak` 替换播放首项并把剩余项排队。缺少 TTS 能力时返回 TTS_UNAVAILABLE，不把屏幕事件当回退语音。
- 新增真实 Node 行为测试，用 spy 证明候选和拒绝状态零调用、READY 的调用序列、PREEMPT 的 stop/speak/enqueue 顺序以及坏 payload 拒绝；Python 静态合同保护脚本加载顺序和两个流式客户端委托。
- 验证：专项 Python `27/27`；第 20–25 项相关组合回归 `136/136`；Node 行为测试输出 `voice_delivery_client: OK`，三份 JS `node --check` 与 `git diff --check` 通过。
- 当前生产后端只发送 `authorization=CONTENT_ELIGIBLE`，所以真实页面仍不会由该事件发声；READY/PREEMPT 仅在测试中模拟，必须由第 26 项 Scheduler 接线后才是真实运行时授权。本项不标 REAL_OK。
- 当前唯一下一项：第 26 项 `VOICE-C5-D10-THREE-ENTRY-INTEGRATION`。

## 2026-08-23 本轮维护记录：VOICE-C5-D10 三入口统一调度

- 新增 `web/playback_runtime.py`：`WebPlaybackService` 把 `VoiceDeliveryItem` 转为带 20 秒 TTL 的 `PlaybackRequest`，统一调用同一个 `PlaybackScheduler`；`BrowserPlaybackExecutionPort` 表达服务器批准后经 HTTP/SSE 交给浏览器执行，不在服务器本地发声。
- `/record` 保存成功后只构建一次 `PresentationDeliveryPlan`：`messages` 负责显示，`voice_items` 经过共享 Scheduler 后附加为 `voice_delivery_events`。保存失败仍在计划和调度之前退出。
- chat 普通正文继续只有 `screen_delta`；chat tool 产生的类型化语音批次不再直接发送 `CONTENT_ELIGIBLE`，而是先调用同一 `web_playback_service.authorize()`，再发送 Scheduler 的 READY/DEFERRED/DROP 结果。
- 桌面 `voice_asr.js` 与手机 `mobile.js` 删除从 `messages.voice_text` 直接发声的路径，统一委托 `consumeVoiceDelivery()`；手机页按正确顺序加载共享授权客户端。
- 当前服务器尚未收到浏览器 VAD/TTS 实时事件，因此生产默认快照为空闲态；符合内容政策的项会得到 READY。若未来出现 PREEMPT，当前适配器在收到匹配 STOPPED 反馈前只发 DEFERRED，避免未确认停止就立即播新语音。真实延后恢复和抢占闭环留给 C3 真机项。
- 验证：纯调度/事件专项 `18/18`，相邻 Scheduler/agent/tool/前端静态回归 `31/31`，Node 行为测试输出 `voice_delivery_client: OK`，五份 JS 语法与四份 Python 编译检查通过。FastAPI `/record` 测试模块因现有 Python 3.14 与旧 `pydantic_core` ABI 不兼容而未加载，不计为业务断言通过；本项不标 REAL_OK。
- 当前唯一下一项：第 27 项 `VOICE-C5-E1-AUTO-ACCEPTANCE`。

## 2026-08-23 本轮维护记录：VOICE-C5-E1 自动验收与职责冻结

- 新增 `tests/test_c5_architecture_freeze.py` 七条可执行架构护栏：DeliveryPlan 禁止依赖运行状态/TTS；Gate 保持纯决定；`/record` 与 chat tool 必须共用 `web_playback_service`；记录客户端只能消费授权事件；流式客户端不得含正文或 done 发声旁路；后台任务完成通知作为显式独立例外保留。
- 审计发现活动版与遗留版流式客户端仍有不可达的 `speechBuffer` 收尾发声代码。虽然缓冲区已无写入、当前不会发声，但未来赋值即可复活，因此本轮删除 `autoSpeak/shouldSpeak/takeCompletedSentences/speechBuffer/done→enqueueSpeech` 残留；done 继续保存 conversation_id、收起思考状态、更新头像并刷新实验列表。
- C5 的冻结职责为：内容层表达含义；DeliveryPlan 只做语音资格；VoiceStateCoordinator 只写运行事实；ContextFactory 只复制快照；Gate 只做决定；Scheduler 唯一编排 Queue/ExecutionPort；浏览器授权客户端只执行 READY/PREEMPT。
- 自动验证：冻结与前端专项 `20/20`；C5 27 个模块组合回归 `190/190`；Node 行为测试输出 `voice_delivery_client: OK`，两份流式客户端 `node --check` 通过。
- 项目级 `unittest discover` 实际执行 `898` 项，结果 `FAILED (errors=17)`、无 assertion failure。17 个错误均发生在导入/加载阶段：当前 Python 3.12 无法加载 `.venv` 中 cp311 NumPy 扩展，Pydantic 同样缺少匹配的 `_pydantic_core`。因此本项只标 C5 `AUTO_OK`，不写项目全量通过、不产生 REAL_OK/UX_CONFIRMED。
- 当前唯一下一项：第 28 项 `VOICE-C4-1-SILERO-CONTRACT`。

## 2026-08-24 本轮维护记录：自由实验统一追问回归纳入正式路线

- 用户真实验收发现自由实验只显示“已记录”，与此前可主动追问的体验不一致。代码审计确认：统一理解合同仍能产生 `missing_fields / should_ask_follow_up / follow_up_question`，但 Web 桥和共享记录服务只保留实体，随后自由模式的空方案评估覆盖了语义追问。
- 计划遗漏原因：历史 `LLM-FOLLOWUP-STRICT-01` 只登记为模型提示词严格度争议，还曾写成“非迁移退化”；它没有进入唯一施工表、没有独立完成条件，也没有回归测试，所以后续逐项施工无人负责。
- 新增第 28 项 `VOICE-C5-E2-FREE-FOLLOWUP-PRESERVATION` 并设为唯一 `NEXT`；原第 28–39 项顺延为 29–40，相对顺序不变。两份正式计划均更新为 40 项。
- 独立验收边界：自由实验语义追问不被空方案评估覆盖；方案确定性追问保持不变；只有保存成功后才能产生 clarification/回执；保存失败不产生成功呈现；新增红灯回归测试转绿且共享记录服务原有测试继续通过。
- 修复：`web/llm_bridge.py` 透传事件 `missing_fields`、`should_ask_follow_up` 和 `follow_up_question`；`web/record_service.py` 仅在自由模式、正常 experiment 分支且追问合同完整时选用语义追问，方案模式继续使用确定性评估。有效 evaluation 随记录落盘，呈现仍严格发生在保存成功之后。
- 自动证据：桥接/共享服务专项 `17/17`；相邻 `/record`、tool、结果合同、降级生产者与呈现回归 `59/59`；项目正式 `.venv` 全量 `1012/1012` 通过。尚未做本轮真实模型和浏览器录音复验，因此第 28 项标 `AUTO_OK`，不标 `REAL_OK`。
- 当前唯一下一项：第 29 项 `VOICE-C4-1-SILERO-CONTRACT`。

## 2026-08-24 本轮维护记录：VOICE-C5-E3 记录流式首反馈

- 发现来源：用户真实体验指出“回复第一句速度慢”；最近三条记录的统一理解耗时为 3.42–4.73 秒，且旧 `/record` 必须等待完整 JSON、保存和最终响应后才有首次可见反馈。
- 新增 `POST /record/stream`，使用 `application/x-ndjson`：连接建立后先发送 `record_status/understanding`，共享记录事务成功后发送原合同不变的 `record_result`；保存失败发送 `record_error` 后结束，绝不发送结果、成功回执或播放授权。旧 `POST /record` 保留兼容。
- 桌面 `voice_asr.js` 与手机 `mobile.js` 使用 `ReadableStream.getReader()` 增量解析；状态事件只更新处理提示，只有最终结果才渲染 messages 并消费 Scheduler 授权事件。两处脚本增加 2026-08-24 cache-busting。
- 边界：这是“首次状态反馈流式”，不是统一理解 JSON 的内容 token 流式，也不是流式 TTS；真实追问仍要等模型完整结构化结果和保存成功，避免半截 JSON、假追问或假记录。
- 自动证据：流式/统一理解专项 `44/44`；C5 冻结、手机页、record 与前端合同复验 `40/40`；项目正式全量 `1017/1017` 通过；两份 JavaScript `node --check` 通过。真实浏览器分块到达与体感仍待用户裁决，因此为 `AUTO_OK`。
- 路线同步：新增第 29 项 `VOICE-C5-E3-RECORD-STREAMING-FEEDBACK`；原第 29–40 项顺延为 30–41，两份唯一施工表共 41 项且相对顺序不变。
- 当前唯一下一项：第 30 项 `VOICE-C4-1-SILERO-CONTRACT`。

## 2026-08-24 本轮维护记录：VOICE-C4-1 Silero VAD 适配合同

- 新增 `src/core/silero_vad_contract.py`，只定义运行库无关的适配边界：输入固定为 16 kHz 单声道、512 个归一化浮点采样的不可变帧，并携带递增序号与单调采集时间。
- 输出固定为 `SPEECH_STARTED / SPEECH_PAUSED / SPEECH_RESUMED / SEGMENT_FINALIZED` 四类事实；`to_voice_runtime_event()` 只映射到现有 Coordinator 事件，不直接写运行状态。
- 失败合同覆盖运行时不可用、模型加载失败、推理失败和非法输出，统一显式选择 `USE_RMS`；失败与语音边界事件互斥，避免失败时伪造讲话状态。
- 本项未加载或下载模型，未访问麦克风，未修改 `phone_call.js` RMS 主路径，未接真实设备，也未改变 C5 播放职责。
- 自动证据：合同与相邻 Coordinator/ContextFactory 回归 `30/30`；项目正式 `.venv` 全量 `1040/1040` 通过。只标 `AUTO_OK`，不标 `REAL_OK`。
- 当前唯一下一项：第 31 项 `VOICE-C4-2-SILERO-INTEGRATION`。

## 2026-08-24 本轮维护记录：VOICE-C4-2 通话模式接入 Silero

- 新增 `web/frontend/call_silero_vad.js`：按现有锁定版本动态加载 ONNX Runtime 1.19.2 与 `vad-web` 0.0.22，使用 Silero v5；适配器只转换开始、停顿、继续、断句事件和返回 16 kHz 音频段。
- `web/app.py` 保证适配器先于 `phone_call.js` 加载；`phone_call.js` 的正常入口改为 `startPreferredCapture()`，Silero 成功时不创建旧 `AudioContext/ScriptProcessor` RMS 麦克风链。
- 初始化失败时直接启动原 `startRmsCapture()`；运行期失败只处理一次，先停止/销毁 Silero，再启动 RMS。两条路径不并行持有麦克风，挂断时清理当前适配器及原有音频资源。
- 新增 Node 行为测试：固定低概率噪音序列不产出事件；固定人声概率序列产出开始→停顿→继续→停顿→断句；Silero 正常时 RMS `getUserMedia` 调用为 0，初始化失败时为 1 且通话保持活动。
- 证据边界：概率序列证明适配状态机和接线，不证明真实模型音频分类质量。仓库历史 WAV 未纳入 Git 固定语料；一次只读实模探查还触发现有后端 `VadSegmenter` 空段异常，留给第 32 项在可重复语料和明确边界下处理。
- 自动证据：Silero/状态/页面/C5 组合回归 `46/46`；`call_silero_vad`、`phone_call_silero_fallback`、既有 `voice_delivery_client` 三条 Node 行为测试通过；四份相关 JS `node --check` 通过；项目正式 `.venv` 全量 `1043/1043` 通过；`git diff --check` 通过。
- 当前只标 `AUTO_OK`，没有真实浏览器、真实麦克风、噪音分类或 barge-in 证据，不标 `REAL_OK`。
- 当前唯一下一项：第 32 项 `VOICE-C4-3-VAD-REGRESSION`。

## 2026-08-24 本轮维护记录：VOICE-C4-3 VAD 回归与真实模型固定样例

- 真实缺陷复现：本地 Silero 对历史语音加尾静音后确实产出队列段，但 `VadSegmenter` 先保存 `front` 视图、再 `pop()`、最后才读取 samples；sherpa 出队后使底层视图失效，因而抛出“VAD 返回了空语音段”。
- 先在 `tests/test_vad_segmenter.py` 增加 `InvalidatingFakeVad` 红灯测试，明确模拟 pop 后 samples 清空；修改前该测试稳定以相同空段错误失败。
- 最小修复仅调整 `src/audio/vad_segmenter.py` 出队顺序：先 `_assemble_one()` 复制并组装成项目自己的 `VoiceSegment`，成功后才 `pop()`；未修改模型、阈值、预滚、最短/最长语音或缓冲参数。修复后 VAD 单元测试 `20/20`。
- 新增 `tests/test_vad_real_model_regression.py`：使用 Git 已跟踪的单声道 24 kHz `web/voice/reference.wav`，确定性线性重采样至 16 kHz，追加固定 3 秒尾静音后，仓库本地 Silero ONNX 实际产出 1 个非空语音段；固定 2 秒静音与随机种子 `20260824`、标准差 `0.02` 的 3 秒低水平宽带噪音均产出 0 段，真实模型样例 `3/3` 通过。
- 扩展 `test_phone_call_silero_fallback.js`：Silero 正常主路径后主动触发运行期推理失败，验证先停 Silero、只启动一次 RMS；挂断后再次启动并模拟初始化失败，验证新 RMS 链可建立，覆盖运行失败和重启生命周期。
- 自动证据：浏览器适配器与回退 Node 行为测试通过；四份相关 JS `node --check` 通过；VAD/真实模型/状态/页面/C5 组合回归 `69/69`；最终项目 `.venv` 全量 `1047/1047` 通过；`git diff --check` 通过。
- 证据边界：已验证一个已跟踪真实语音、全静音和一种合成宽带噪音，不等于真实房间空调、键盘、远场、扬声器自激或不同浏览器麦克风通过；本项只标 `AUTO_OK`，不标 `REAL_OK`。
- 当前唯一下一项：第 33 项 `VOICE-C3-1-PLAYBACK-TIMING-REAL`。

## 2026-08-25 本轮维护记录：VOICE-C4-3B 短停顿进入同一会话状态

- 真实缺口是 `phone_call.js` 收到 Silero `speech_paused` 时只改页面提示，没有上报服务端；请求模型也只允许 `user_speech_started`。
- 浏览器现在使用同一个 `reportVoiceRuntimeEvent()`，在停顿时携带当前 `conversation_id` 发送 `user_speech_paused`。
- HTTP 路由将该类型显式映射为 `USER_SPEECH_PAUSED`，仍交给按会话隔离的 `VoiceRuntimeSessionRegistry` 和唯一写入者 `VoiceStateCoordinator`。
- 最终状态只是 `user_speaking: true -> false`，`segment_capturing` 仍为 `true`；重试同一停顿事实返回 `applied=false`。
- 自动证据：会话/路由 `6/6`，相关组合 `43/43`，两个 Node 行为测试通过，全量 `1053/1053` 通过；另有 Starlette/FastAPI 弃用警告，无失败。
- 项目 `.venv` 启动器指向已缺失的 Python 3.11；本轮为不改用户环境，用 Python 官方 3.11.9 一次性运行时加载现有 `.venv` 依赖完成验证。
- 证据不包括恢复、断句、ASR/TTS 事件、Scheduler 消费或真实设备体感；该记录当时曾误将第 33 项列为下一项，后续复核已增补 32c–32f 并纠正。

## 2026-08-25 本轮维护记录：VOICE-C4-3C 停顿后继续讲话进入同一会话

- 复核发现 Silero 已产生 `speech_resumed`，但 `phone_call.js` 只恢复页面聆听状态，未上报服务端。
- 浏览器现携带原 `conversation_id` 发送 `user_speech_resumed`；HTTP 路由显式映射到 `USER_SPEECH_RESUMED`。
- 最终状态仅为 `user_speaking: false -> true`，`segment_capturing` 保留 `true`，因此继续讲话仍属于同一音频片段。
- 重复恢复事件返回原状态且 `applied=false`，其他 conversation 不受影响。
- 验证：会话/HTTP 路由 `8/8`，纯合同 `24/24`，`call_silero_vad` 和 `phone_call_silero_fallback` Node 行为测试通过，JS 语法和 `git diff --check` 通过。
- 项目原 `.venv` 启动器仍指向已缺失的 Python 3.11；本轮用一次性官方 Python 3.11.9 加载现有依赖，专项后继续完成全量 `1055/1055`，然后删除临时运行时。
- 复核增补 32c–32f，第 33 项退回 `TODO`。当前唯一下一项是 32d：断句与 ASR 处理状态桥接。

## 2026-08-25 本轮维护记录：VOICE-C4-3D–3F 语音事实到播放重评生产闭环

- 纠正了“一小步”的粒度：本轮不再按单个事件分拆，而是一次完成浏览器事实、按会话状态、播放决策、TTS 反馈和延后重评的可独立验收能力。
- `phone_call.js` 使用串行事件链保证 `PAUSED -> FINALIZED -> ASR_STARTED -> ASR_FINISHED/FAILED` 顺序，并消费状态请求返回的重评播放事件。
- `VoiceRuntimeSessionRegistry` 暴露同一 conversation 的唯一 Coordinator；`ConversationPlaybackRegistry` 为每个 conversation 绑定共享该 Coordinator 的 Scheduler 和延后队列。
- chat 与 `/record` 的播放候选携带 conversation 进入共享服务；无 Web conversation 的记录使用 `record:<session_id>` 隔离。
- `local_tts.js` 的每个播放单元保留 runtime hooks；`voice_delivery_client.js` 将 `intent_id/priority` 随 STARTED/FINISHED/STOPPED/FAILED 回报服务端。
- Scheduler 新增显式 `reevaluate()`：只在 ASR 输入空闲或 TTS 结束事实后重评已延后队列；仍忙则保留，已过期则 DROP，可播则交回浏览器。
- 专项 `48/48`、全部 3 个 Node 行为测试、五份相关 JS 语法、`git diff --check` 和全量 `1060/1060` 通过。仅能证明自动环境下的软件闭环，不能证明真实麦克风、外放、耳机、浏览器时序或听感。
- 当前唯一下一项恢复为第 33 项真实播放时机验收。

## 2026-08-25 真实验收纠偏：VOICE-C6 单聊天时间线与显式模式前置批次

- 第 33 项首次真实浏览器验收发现：ASR 与普通 chat 文字回复正常，但普通正文没有生成 `voice_delivery`，因此在通话和喇叭均开启时仍无声音。服务端日志证明没有 `/tts` 或 TTS 生命周期请求；这不是用户操作问题。
- 当前试验改动为普通回复补了 `ASSISTANT_REPLY` 候选，并完成相关专项 `43/43`；但它暂时复用了实验语音首句/25 字预算，只用于证明缺口位置，不视为最终 chat 输出策略，也不把第 33 项标为通过。
- 复核确认第 26 项此前所谓“三入口统一”实际只覆盖 `/record` 与 chat tool 已有语音候选共用 PlaybackScheduler；普通 chat 仍是 `screen_delta`，前端也没有统一 Turn 状态。因此第 26 项名称和结论已收窄，保留原自动证据，不扩大为完整界面/输出统一。
- 产品交互改为单聊天时间线：用户/助手文字、方案、步骤、安全、记录、tool、确认和状态都成为同一 `turn_id` 下的消息块；原中间运行画布不再保存第二份实时 think/tool 状态，方案库、记录库、安全库等管理页可继续承担完整浏览与编辑。
- 模式显式分为：`chat`、`experiment/free`、`experiment/protocol`。文字、单次录音、连续通话只是 `input_source`，不得暗中决定业务模式；每个请求携带提交时的模式快照，避免异步处理期间切换模式导致串线。
- 自由实验记录仍必须保留第 28 项已修复的语义追问：先保存原始事实，保存成功后最多追问一个影响复现/判断/安全的关键缺口；方案实验按方案已知值、现场必测与偏差追问；自由 chat 不自动保存实验事实。
- 内容策略分开但输出机制统一：实验记录使用严格短回执/追问，chat 使用自然回答与按句语音，tool 只呈现真实执行结果；三者统一生成 Turn/Block/voice identity，并共用会话 PlaybackScheduler、TTS 反馈、延后、过期和失败边界。
- 新增 33a–33f 作为真实播放前置：合同 → 单一 Store → chat-first 界面 → 显式模式 → 分策略输出 → 三生产者交叉自动回归；原真实播放时机验收后移为 33g，第 34 项仍负责真实打断、自激和漏检。
- 35–39 的五分支理解保持在输出收口之后：`experiment/control/tool/chat/uncertain` 只决定输入去向；第 39 项再统一 tool 参数、风险、确认和执行权限，不允许理解层直接保存、执行或播放。
- 当前唯一下一项：33a `VOICE-C6-A1-TURN-BLOCK-CONTRACT`，先定义可追溯而无副作用的统一回合/消息块合同；本记录不宣称真实声音、单聊天界面或模式切换已经完成。

## 2026-08-25 VOICE-C6-A1-TURN-BLOCK-CONTRACT 自动闭环

- 新增纯数据合同 `ConversationTurn / ConversationBlock`，以及 interaction mode、experiment context、input source 和 block type 枚举；`request_id` 提供幂等身份，模式、上下文、`mode_version` 和输入来源在提交时形成不可变快照。
- 用户/助手文字以及方案、步骤、安全、记录、tool、确认和系统状态卡片均是可见 Block；VOICE Block 不复制正文，必须用 `source_block_id` 引用本 turn 非语音 Block，并携带唯一 `intent_id` 和 `MessagePriority`。
- 新增纯函数 `decide_turn_replay()`：不同 `(conversation_id, request_id)` 是新请求；完全相同合同是幂等重放；同一请求改变 `mode_version` 明确报模式版本冲突；其他内容变化报请求内容冲突。函数不读写 Store。
- 合同拒绝空/重复身份、跨 turn 或 voice-to-voice 引用、非法模式上下文组合和非 JSON payload；嵌套 payload 深层不可变，`to_wire()` 产出 JSON 可序列化字典。
- 专项 `14/14`、相邻呈现/播放合同 `39/39`、`py_compile`、`git diff --check` 与项目全量 `1076/1076` 通过，因此标 `AUTO_OK`。这是纯合同自动证据，不证明 Store、单 Composer/聊天页面、模式切换、Chat/实验保存策略、Tool 权限、TTS 或真实浏览器/设备。
- 当前唯一下一项：33b `VOICE-C6-A2-SINGLE-CONVERSATION-STORE`；把事件写入唯一 Store 并移除 chat/run 双份 think/tool 状态。本轮不提前实现。

## 2026-08-25 VOICE-C6-A2-SINGLE-CONVERSATION-STORE 自动闭环

- 新增浏览器 `ConversationTurnStore`：`beginTurn/upsertBlock/pushThink/pushTool/subscribe/clear/getSnapshot` 是当前 Turn 的唯一前端事实入口；快照深拷贝，外部不能反向篡改 Store。
- Chat 服务端正文统一 upsert 为 `assistant_text`，think 映射为 `system_status(kind=think)`，Tool 映射为 `tool_card`；聊天 DOM 只订阅渲染，不再直接接收这些服务端事实。
- `run_canvas.js` 删除实时 `stream/pendingIndex`、think/tool HTML 生产和 `runPushThink/runPushTool/runClearStream`；运行画布继续只显示现有方案与步骤，不再保存第二份实时事件。
- Tool pending/result 由服务端携带同一个 `tool_call_id`，Store 以稳定调用身份更新同一 Block，不再依赖标题作为首选身份。
- Store 对相同 `(conversation_id, request_id)` 的原始请求重放保持已有 Block；内容或 `mode_version` 改变则拒绝冲突。此为浏览器内存 Store 行为，不是数据库持久化或跨刷新幂等。
- 专项组合 `27/27`、`conversation_turn_store: OK`，其余 3 个既有 Node 行为测试通过，JS/Python 语法、`git diff --check` 与项目全量 `1083/1083` 通过。自动证据不证明真实浏览器布局、刷新恢复或用户体验。
- 当前唯一下一项：33c `VOICE-C6-A3-CHAT-FIRST-SURFACE`；将方案、步骤、安全、记录、确认和状态正式渲染为同一聊天时间线 Block。本轮不提前实现。

## 2026-08-25 VOICE-C6-A3-CHAT-FIRST-SURFACE 自动闭环

- 七类卡片 Block 共用一个 BlockView 适配器和聊天卡片骨架；类型差异只决定标题、正文、元信息、状态和色调，不复制七套 DOM。
- 方案/步骤/安全从既有只读会话事实投影进每个 Turn；单次录音建立 experiment Turn，保存结果进入 record/confirmation Block。
- 原“实验进行中”run 画布不再加载；方案、试剂安全、记录和设置继续作为管理页，不保存第二份实时状态。
- 专项 `30/30`、5 个 Node 行为测试、JS 语法、`git diff --check` 与全量 `1091/1091` 通过，仅标 `AUTO_OK`；真实布局、滚动和用户体验未验收。
- 当前唯一下一项：33d `VOICE-C6-A4-EXPLICIT-MODE-SWITCH`。

## 2026-08-25 VOICE-C6-A4-EXPLICIT-MODE-SWITCH 专项自动闭环

- 唯一 Composer 显式提供自由聊天、自由实验记录、方案实验记录三档；模式变化才递增 `mode_version`。
- 文字、单次录音和连续通话只贡献 `input_source`；提交时冻结 `interaction_mode / experiment_context / mode_version / input_source`，之后切换不改变旧快照。
- Chat 的 Store Turn 与 `/chat/stream` 请求复用同一快照；单次录音开始时冻结并同时交给 Store 与 `/record/stream`；连续通话明确标记 `continuous_call`。
- 服务端 Chat/Record 请求继承同一个模式快照校验器，拒绝 chat+实验上下文、experiment+none 和非正版本；本项不按模式改变保存、Tool、回复或 TTS 策略。
- 实际证据：33d/33c/33b 专项 `22/22`，项目目录既有 Python 3.11 运行时加载现有依赖完成全量 `1098/1098`；新旧 3 个 Node 合同测试、相关 JS `node --check`、Python `py_compile`、`git diff --check` 均通过。
- 证据限制：未做真实浏览器布局、模式切换和录音/连续通话走查，不标 `REAL_OK/UX_CONFIRMED`。
- 当前唯一下一项：33e `VOICE-C6-A5-MODE-OUTPUT-POLICIES`。

## 2026-08-25 VOICE-C6-A5-MODE-OUTPUT-POLICIES 自动闭环

- 新增纯策略选择 `select_output_policy()`：Chat 不保存、不允许记录 Tool；自由/方案实验保存原始事实，最多一个追问。
- 文字和连续通话在统一 Composer 提交后按冻结模式分流；单次录音在 Chat 模式回到 Chat，在实验模式才进入 `/record/stream`，因此 input_source 不再决定业务去向。
- Chat 服务端同时隐藏并硬阻断 `record_observation`，提示词不再把“提到实验事实”解释成自动保存；实验模式请求误入 Chat、Chat 请求误入 Record 均返回 409。
- 自由实验显式覆盖当前已加载方案，保留统一理解的关键语义追问；方案实验必须已有有效方案，否则在抽取和保存前失败；成功投影严格发生在保存之后。
- Tool 仍只把真实执行 outcome 交给既有 Tool Card/DeliveryPlan，不新增模型伪造结果或旁路播放。
- 验证：专项 `46/46`，项目全量 `1105/1105`，6 个相关 Node 行为测试、5 份 JS 语法与 `git diff --check` 通过，仅标 `AUTO_OK`。
- 未做真实浏览器模式切换、文字/单次录音/连续通话和卡片顺序验收，不标 `REAL_OK/UX_CONFIRMED`。
- 当前唯一下一项：33f `VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX`。

## 2026-08-25 VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX 自动闭环

- 矩阵盘点发现 33a 的 `source_block_id` 仍停留在纯合同，实际 `VoiceDeliveryItem/PlaybackRequest/voice_delivery` 未携带屏幕来源；本轮将该身份贯穿内容计划、调度和浏览器边界。
- Chat/Tool 语音绑定当前助手 Block；Record 追问绑定当前 confirmation Block；请求同时携带 `request_id/turn_id`，两者必须同时出现。
- 浏览器仅在 `source_block_id` 引用当前 Turn 已存在 Block 时接受 READY/PREEMPT，拒绝孤儿语音；调度的 DEFERRED、恢复 READY 和过期 DROP 均保持来源身份不变。
- 新增 Python 三生产者矩阵：Chat/Record/Tool × READY/DEFERRED/恢复/DROP × A/B 会话隔离；新增 Node 矩阵覆盖三种可见 Block、播放引用、完全相同重放和 `mode_version` 冲突。
- 第一次全量的 2 个失败来自旧架构护栏匹配 `authorize(output.items)` 精确字符串；更新为检查 `bind_voice_items(...)` 后仍进入同一 Scheduler，没有回退生产实现。
- 验证：专项组合 `54/54`、全量 `1110/1110`、7 个 Node 行为测试、JS/Python 语法及 `git diff --check` 通过，仅标 `AUTO_OK`。
- 未进行真实浏览器、麦克风、扬声器、耳机、TTS 听感或真实时序验收。
- 当前唯一下一项：33g `VOICE-C3-1-PLAYBACK-TIMING-REAL`。

## 2026-08-25 维护记录：33c-UX 单主视图纠偏

- 真实页面复核发现 `shell.js` 虽已取消 run 画布的实时 think/tool 状态，却仍默认把方案管理画布与聊天左右并排，造成用户看到两处主界面。
- 本轮把 Chat 设为默认且唯一可见主视图；方案、试剂安全、记录和设置改为导航触发的互斥管理页。
- `chat / experiment/free / experiment/protocol` 不再选择不同屏幕区域，只决定同一聊天时间线中产生哪些 Block。
- 针对性模式/Block/三生产者回归 `27/27`、JS 语法与 `git diff --check` 通过，仅标 `AUTO_OK / UX_PENDING`。
- 尚未做真实浏览器布局、滚动、管理页往返和状态保留走查。当前唯一下一项是完成单主视图真实浏览器 UX 复验，确认后再继续 33g。

## 2026-08-25 维护记录：33g 前置语音输入输出恢复

- ASR warmup 503 的根因是受限 Uvicorn 进程中 FunASR 调用 `ffmpeg -version` 被 Windows 拒绝；服务改为核验 PID 后以同项目 Python 3.11 非受限隐藏启动，ASR `loaded=true`，固定真实 WAV 转写成功。
- 普通 Chat 的 `ASSISTANT_REPLY` 错误使用永不播放的 `ROUTINE`，Scheduler 返回 `DROP/context_lost`；现改为低于安全/追问、可在空闲播放的 `REVIEW`，真实 SSE 返回 `READY/playback_window_open`。
- 火山 TTS 首探针出现一次代理 TLS EOF，随后连续 `3/3` 返回 200、每次 17,760 字节；不能据此宣称外部网络永远稳定。
- 专项 `38/38`、项目全量 `1111/1111` 通过。当前唯一下一项是用户用真实麦克风验证“说话→文字进入唯一聊天→模型回复→实际出声”。

### 2026-08-25 浏览器最后一公里补充

- 用户复验时日志显示真实 `/asr/transcribe 200` 与 `/chat/stream 200`，但没有 `/tts` 或 TTS 生命周期请求，证明故障在浏览器 READY 消费边界。
- 单主视图隐藏了头像及其 `tts-muted` 控件，历史静音值可能继续阻断播放且用户无法解除；现将“语音开启/关闭”移到唯一聊天头部，并让 PLAYED、PLAYBACK_DISABLED、REJECTED_PAYLOAD、TTS_UNAVAILABLE 成为可观察浏览器事件。
- Node 行为测试、JS 语法、差异检查及相关组合 `50/50` 通过；服务以同配置重启为 PID 29900，首页新缓存版本和按钮均已现场确认，ASR 已重新预热。
- 唯一下一项仍是用户刷新后确认按钮显示“语音开启”，再完成一次真实说话与人耳播放。

### 2026-08-25 自由实验重复呈现纠偏

- 用户截图证明同一第 71 段记录同时进入聊天 Blocks 与遗留 `lab_panel.js` 右侧面板；数据库 `/record/history` 显示该段仅 1 条，因此是重复投影而非重复保存。
- 桌面首页停止加载 `lab_panel.js`，`voice_asr.js` 删除第二个 `labRender()` 消费者；方案、安全、记录管理仍由 shell 管理页保留，实时结果只进入唯一 ConversationTurnStore。
- 相关回归 `43/43`、JS 语法和差异检查通过；服务 PID 25484 已确认首页不含旧面板、ASR `loaded=true`。唯一下一项是刷新后复验自由实验只出现一组 Blocks 且仍有语音。

### 2026-08-25 方案模式与活动方案同步纠偏

- 用户点“方案实验记录”后仍看到“自由实验”，根因是 Composer 只切换浏览器语义模式，没有建立服务端活动方案；两套状态发生分裂。
- 现在方案模式入口先读取 `/protocols/session`：没有活动方案时只打开方案选择页，不提前切换模式；点中具体方案且 POST 成功后，才把 `interactionModeState` 切为 `experiment/protocol` 并返回唯一聊天时间线。选择“自由记录模式”则同步切到 `experiment/free`。
- 专项相关组合 `29/29`、两份 JS 语法和差异检查通过，仅证明自动合同，不代表真实浏览器选择、返回和方案 Block 已由用户确认。
- 唯一下一项：真实浏览器刷新后点“方案实验记录”→选一个具体方案→自动回主聊天→录入一条事实，确认显示该方案/步骤而非自由实验。

### 2026-08-25 Chat 语音合同设计决定（未编码）

- 默认 Chat：可朗读正文单独成为可见 Block，屏幕正文与 `voice_text` 逐字一致；生成阶段以约 10 秒为目标，禁止下游首句/25 字机械截断。
- “继续说”：只为当前回合建立 continuation 详细 Block，不形成永久详细偏好；用户指定重读时按原可见 Block 重新合成，不重新生成答案。
- 打断：先暂停，不自动恢复。误触反馈前两次可见且朗读，第三次起只显示；有效 `user_text` 建立后清零，连续监听始终保持开启。
- 状态为 `DESIGN_DECIDED / NOT_CODED`；现有 `MAX_ITEM_CHARS = 25` 尚未移除，Free/Protocol 语音矩阵尚未决定，不能标为自动或真实验收通过。

### 2026-08-25 Free / Protocol Experiment 语音合同设计决定（未编码）

- 共同规则：一个 Experiment Turn 可以有多个业务 Block，但最多只产生一个独立、可见的语音汇总 Block；实际 `voice_text` 与该来源 Block 正文逐字一致，估算最长约 15 秒。用户原话不回读，保存成功 `record_card` 只显示不朗读，保存失败不得产生成功反馈，现有通用 `safety_alert` 只显示不读。
- Free：先保存原始事实，成功后最多一个关键语义追问；追问和本轮必要解释显示并朗读，没有追问时允许静默保存，不受后台残留方案约束。
- Protocol：必须先有活动方案；`protocol_card` 只在进入/切换/版本变化时出现，`step_card` 只在进入/切换/版本变化时出现；本轮新偏差、必测缺口或确认 Block 分别维护业务状态，但需说内容统一进入至多一个约 15 秒的可见语音汇总 Block，既有上下文不重复显示或朗读。
- 当前 `publishProtocolContextBlocks(turnId)` 仍按每个 Turn 重建方案/步骤卡，首句/25 字限制仍存在；明确危险动作判断和 `danger_intervention` 均不存在。本项为 `DESIGN_DECIDED / NOT_CODED`，不能标为自动或真实验收通过。

### 2026-08-25 统一可见语音 Block 纯合同（AUTO_OK，未接生产）

- 新增纯 `spoken_output` 合同：Chat 默认 50 字估算约 10 秒，单回合 continuation 不套默认预算，Free/Protocol 整 Turn 唯一自动语音 75 字估算约 15 秒。
- 一次构造只产生一个可见 `assistant_text(role=spoken)` 与一个引用它的 VOICE；语音文字直接从可见 Block正文派生，不保存第二份副本，超预算在发布前失败而不是截断。
- 新增专项 `6/6`、相关组合 `30/30`、全量 `1119/1119`、编译与差异检查通过，标 `AUTO_OK`。
- 尚未接生产 Chat/Record、前端、Scheduler 或 TTS；页面仍使用旧首句/25 字策略。唯一下一步只接普通 Chat 生产链。

### 2026-08-25 普通 Chat 可见语音 Block 生产接入

- `CHAT_POLICY`生成最多50字的纯文本完整短答；`chat_stream`缓冲并验证后，屏幕一次发布`${turnId}:spoken`的`assistant_text(role=spoken)`，唯一voice item逐字读取同一正文并进入共享Scheduler。
- 新增预算贯穿`VoiceDeliveryItem → PlaybackRequest → WebPlaybackService`；普通Chat可使用50字预算，既有Record/Tool仍默认25字，没有全局放宽旧内容策略。
- 前端只改Chat Block ID、role和发布时间；没有新增/隐藏界面区域，Experiment路径未改。最终全量`1123/1123`、编译、JS语法和差异检查通过。
- PID 14492真实官方DeepSeek探针得到screen/voice逐字相同、`:spoken`来源、READY；真实TTS返回200、118560字节MP3，ASR`loaded=true`。状态为软件与真实服务探针通过、真实浏览器/人耳`PENDING`。
- 唯一下一步：用户`Ctrl+F5`后用普通Chat验证一段完整短答在屏幕和语音中逐字一致且不中途截断。

### 2026-08-25 可搬家的一键启动与转交

- `start.bat`、`build_exe.bat`、`package.bat`、`upload.bat` 删除个人绝对路径，统一用 `%~dp0` 从批处理自身位置定位仓库；带空格路径也使用引号保护。
- `scripts/start_best.py --doctor` 可只报告仓库、Python、虚拟环境、Web 入口、ASR 模型和本地配置状态，不下载、不启动服务。
- 新增 `docs/ONE_CLICK_START_GUIDE.md`，面向新手说明首次启动、密钥边界、常见失败、源码/EXE 两种交付和证据边界；README 快速开始改为双击 `start.bat`。
- 自动证据：启动器专项 `2/2`、项目原 `.venv` 全量 `1144/1144`、`git diff --check` 通过；另一台电脑的首次下载、浏览器、麦克风、API 和防火墙仍需目标机真实验收，因此只标 `AUTO_OK`。
- 本项只解决可搬家启动与交付说明，不改变 Chat/Record/TTS 业务逻辑；语音主线唯一下一项保持不变。

### 2026-08-26 根目录按使用者职责归类

- 根目录只保留普通用户唯一入口 `start.bat`；有效开发批处理进入 `scripts/windows/`，10 个已弃用批处理进入 `scripts/legacy_launchers/`。
- EXE 入口移动为 `scripts/launcher.py`，同步修正仓库根计算和 `scripts/build_exe.py` 的 PyInstaller 入口；VAD 诊断进入 `scripts/diagnostics/`。
- 两份旧交接文档、页面 dump 和终端抓取记录进入 `docs/history/`；文件均保留，没有删除历史证据。
- README 新增根目录文件职责表；专项测试锁定“根目录只能有 start.bat”及新打包入口。专项 `4/4`、移动入口 `py_compile`、项目原 `.venv` 全量 `1148/1148`（9.902 秒）和 `git diff --check` 均通过，仅标 `AUTO_OK`。
- 本轮不移动 `.runtime-python311*`：它们是未跟踪的本机备用运行时，当前是否仍被外部命令使用缺少证据，贸然移动可能破坏当前开发环境。

### 2026-08-26 移动后源码打包真实测试

- 非受限环境真实运行 `scripts/windows/package_source.bat` 成功，证明批处理能从新目录返回仓库根并调用项目 `.venv`；生成 `dist/ai107-source-20260826-004317.zip`，601 个条目、60,656,779 字节。
- 内容验收失败：必需入口均存在，`.env/.venv/web/settings.json/web/lab_agent.db/web/certs` 已排除；但错误包含 `.runtime-python311*` 37 项、`audio/recordings/` 26 项和 `results/` 4 项。
- 当前 ZIP 仅在本机、未上传，但含真实录音和运行结果，明确标记为 `NOT_SAFE_TO_SHARE`。根因修复应补齐 `scripts/package.py` 排除合同，并让批处理在 Python 失败时传播非零退出码；本次仅按用户要求测试，尚未修复。

### 2026-08-26 源码包隐私排除修复与复验

- `scripts/package.py` 新增目录剪枝和文件过滤：排除 `.runtime-python*`、`audio/raw`、`audio/recordings`、`results` 和运行日志；`package_source.bat` 保存并传播 Python 退出码。
- 合同与入口专项 `7/7` 通过后真实生成 `dist/ai107-source-20260826-004548.zip`：507 项、35,967,522 字节。
- 开箱验收：`start.bat/README/.env.example/package_source.bat/scripts/launcher.py/ONE_CLICK_START_GUIDE` 全部存在；`.env/.venv/.runtime-python*/settings/数据库/证书/录音/results/log` 全部 0 项，结果 `PASS / SAFE_CONTENT_CONTRACT`。
- 旧 `004317.zip` 仍留在本机且标记 `NOT_SAFE_TO_SHARE`，未上传；本轮未获删除授权，因此不删除。

### 2026-08-26 VOICE-D0 来源可信输入合同

- 新增纯数据合同 `ExperimentTurnInput`，冻结 `conversation_id / request_id / turn_id`、实验模式快照、输入来源、原文和可选 ASR 证据；不调用 LLM、不保存、不分派、不更新问题状态。
- 文字输入只能携带原文；单次录音和连续通话必须携带与原文完全一致的最终 `ASRResult`。
- 当前 `Documents\107` 是唯一实现基线；`Desktop\asr_demo` 只用于核对设计初衷，禁止复制或覆盖当前核心文件。
- 红灯先证明模块不存在；实现后专项 `9/9`、相邻回归 `35/35`、项目正式 `.venv` 全量 `1162/1162` 通过，仅标 `AUTO_OK`。
- 尚未接 `/asr`、`/record`、`UnifiedObserver`、`ReplyCoordinator` 或真实 LLM，不能证明统一链已接入或识别能力。
- 当前唯一下一项：第 35 项 `VOICE-D1-SESSION-OWNERSHIP`，建立按 `(conversation_id, lab_session_id)` 隔离的会话状态和有序处理边界。

### 2026-08-26 VOICE-D1 会话所有权与有序处理

- 新增 `web/experiment_runtime_sessions.py`；每个 `(conversation_id, lab_session_id)` 独立持有 `ReplyCoordinator`、`SessionContext` 和单工作线程队列，不与其他实验会话共享问题状态。
- 同一会话按提交顺序串行修改状态，不同会话可以并行；相同 `request_id` 的完全一致重试复用原序号和 `Future`，内容冲突拒绝，队列达到上限时对新请求施加背压。
- 专项 `11/11`、相邻回归 `43/43`、项目正式 `.venv` 全量 `1175/1175`（8.485 秒）通过，仅标 `AUTO_OK`。
- 本轮没有从 `Desktop\asr_demo` 复制或覆盖任何实现；当前 `Documents\107` 仍是唯一施工基线。
- 尚未把注册表接到 `/record`，也未调用 `UnifiedObserver` 或真实 LLM；因此当前不能声称生产统一链已接入，也不能评价识别能力。
- 遗留留白（2026-08-26 审查发现）：`ExperimentRuntimeSession._submissions` 只在 `submit` 写入、从不清理已完成记录，幂等去重会保留会话生命周期内的全部历史。该行为对幂等必要，但对背压"防内存增长"动机是过度保留；清理策略（去重窗口期）取决于未来 `/record` 路由的重试策略，待接路由时按真实重试行为确定，当前不阻塞。
- 当前唯一下一项：第 36 项先让统一观察器在该会话边界内处理 `ExperimentTurnInput`，以受控测试验证真实观察结果；生产 `/record` 切换留到观察器合同稳定后。

### 2026-08-26 VOICE-D2 会话边界内接入统一观察器（受控验证）

- 新增 `src/core/experiment_observer_bridge.py::observe_experiment_turn`：把语音 `ExperimentTurnInput` + 会话状态映射到 `UnifiedObserver.observe()`，只观察不落盘不执行；文字输入（`asr_result=None`）显式抛 `ValueError`，落实"文字不伪装成 ASR"。
- `session_id` / `segment_id` 走显式参数：`ExperimentTurnInput` 合同没有这两个字段，段号由调用方分配。
- 受控测试 `tests/test_experiment_observer_bridge.py`：复用 `FixedAcceptanceProcessor` 模式（Fake 不触网、构造 source 匹配有效事件），验证语音映射、文字拒绝、明确命令 0 次 LLM、普通输入 1 次 LLM、降级 `degraded_evidence_note` 且 `asr_transcript` 保留、接线器在 `ExperimentRuntimeSession` 单 worker FIFO 边界内运行。
- 专项 `6/6`、项目正式 `.venv` 全量 `1186/1186`（8.016 秒）通过，仅标 `AUTO_OK`。
- 未接真实 LLM、未接 `/record` 路由、未落盘或执行澄清动作；真实观察结果验收需真实 LLM + 固定 WAV 授权后另行安排。
- 当前唯一下一项：第 37 项 `VOICE-D3-DROP-IN-SWAP` 降级生产者切换为真实观察器（依赖 `UnifiedSegmentProcessor` 六步流水线接入 web 存储）。

### 2026-08-26 方案实验闭环缺口统计（真实验收发现 + 代码审查）

- **缺口 1（核心）· 无累计已记录字段状态**：`ProtocolSessionState` 只存 `selection`+`cursor`（当前步骤游标），不存"这一步已记录哪些字段"；用户分句补字段（先"3.58"后"克"）时系统不记得上一句、重复追问。方向：加"当前步骤累计字段"状态，`compute_missing_fields` 改用累计判断。
- **缺口 2 · 追问是"死"的**：降级 producer 只产 `partial_question` 文本，无 `pending_action`、不更新 `ReplyCoordinator`，回答关联不上。方向：方案实验接入六步流水线。
- **缺口 3 · deviations 被丢弃**：`detect_protocol_deviations` 能检测偏差（含 `action` 不匹配），但 `record_service.py` 的 `presentation_evaluation` 只取 3 字段丢弃 deviations，不提示"操作和方案不一致"。方向：deviations 接进呈现层。
- **缺口 4 · 无法识别完全无关输入**：提取不到实体的无关话，系统只机械追问缺字段、不提示"请围绕当前步骤"。方向：加"未提供有效实体"判断。
- **缺口 5（暂缓）· 文本字段无确定性识别**：`observation` 等文本字段 `answer_fallback` 正则覆盖不了；用户 2026-08-26 定"暂时不考虑"，靠 LLM 识别。
- **缺口 6（共同地基）· 字段 schema 散落**：字段名+属性散落 10+ 处，加字段改 6-7 处、数量对不齐。方向：集中到 `entity_field_schema.py`。
- 后续顺序：缺口 6（字段地基）→ 缺口 1+2（闭环地基：累计状态 + 六步流水线）→ 缺口 3+4（纠错能力：deviations + 无关输入）→ 缺口 5 暂缓。
- **两类缺口的本质区分**（2026-08-26 澄清"终端通畅、Web 为何有缺口"）：① **Web 环境适配**（终端路径早已接好，Web 还没搬）——缺口 2（追问死 = 没接六步）、缺口 6（字段散落，两端都散）；② **真·新能力**（终端路径也没有，主要是方案实验特有）——缺口 1（累计状态）、缺口 3（deviations 呈现）、缺口 4（无关输入识别）。含义：统一链本身没坏，缺的是"Web 转接头 + 方案实验新能力"两块，可分别补。

### 2026-08-26 自由实验六步流水线受控验证（第 37 项第一段）

- 新增 `src/core/experiment_observer_bridge.py::process_experiment_turn`：把语音 `ExperimentTurnInput` 映射到 `SegmentJob`，交给 `UnifiedSegmentProcessor` 六步流水线完整处理（观察→落盘→执行澄清动作），文字输入拒绝；`processor` 由调用方装配并跨 turn 复用，保持协调器/上下文状态。
- 集成测试 `tests/test_experiment_pipeline.py`：真实观察链（`UnifiedObserver` + Fake processor）+ 真实 `ClarificationExecutor` + 真实 `ReplyCoordinator` + Fake 三个存储，验证六步跑通、追问-回答闭环、文字拒绝、降级 ASR 不丢。
- 专项 `4/4`、项目正式 `.venv` 全量 `1190/1190`（8.385 秒）通过，仅标 `AUTO_OK`。
- 填补的空隙：现有 `test_unified_segment_processor.py` 用 FakeObserver，未证明"真实观察链 + 六步 + 真实执行器 + 真实协调器"能串联闭环；本项补上。
- 未做：生产 `/record` 切换（存储适配 + 输出层适配 + 会话状态接入，留第 37 项第二段）。
- 当前唯一下一项：第 37 项第二段生产切换（`/record` 自由实验分支用六步流水线替换降级 producer）。

### 2026-08-27 Web 统一 Turn“结束实验记录”完整真实验收

- 用户在真实桌面浏览器、麦克风和扬声器环境完成连续通话验收，确认精确口述“结束实验记录”后：`business.session_ended=true`、结束命令不新增实验记录、下一条实验轮换到新 `lab_session_id`、按钮回到未通话、麦克风停止且服务无 `ValueError/500`。
- 真实验收继续暴露“只显示单句结束语”的缺口：`ExperimentProcessor` 的结束分支没有读取 SQLite 恢复的 `ReplyCoordinator`。现已把本次实验步骤数、全部未解决问题、稳定编号和“待回答/已暂缓”状态合成一个最终 `ConversationTurn` 屏幕摘要；已解决问题不重复出现。
- 随后真实验收又暴露“完整文字已上屏，但不朗读且连续通话不退出”：完整屏幕摘要超过 SSE 每轮 50 字语音预算，`turn_result` 发出后 `voice_delivery` 序列化异常，同时吞掉 `done`。修复后屏幕保留完整明细，语音使用 50 字以内的 `SESSION_CLOSING_SUMMARY / SUMMARY` 短摘要；`web/api/turn.py` 隔离提交后的语音授权异常并保证最终 `done` 必达。
- 关键真实请求证据：`web-audio-daf62c42-f6be-4ea0-bf4c-531da8a10c82`；SQLite 最终 Turn 包含完整问题汇总和 `session_ended=true`。用户最终确认完整上屏、短收尾朗读、连续通话退出和麦克风停止均通过。
- 自动证据分两轮：问题汇总接入相关 Python `48/48`；语音预算与 `done` 兜底相关 Python `37/37`、`test_phone_call_silero_fallback.js`、JavaScript 语法及 `git diff --check` 通过。自动结果不代替真实证据；本项因已有用户真实复验标记 `REAL_OK`。
- 当前唯一下一能力：方案实验完整接入，按“free/protocol 状态隔离 → 当前步确定性评价 → 最终 protocol/step/safety Blocks → SQLite → 前端显示 → 真实验收”完成一个闭环；暂不开始提速，不删除旧公开接口。

### 2026-08-27 修复：语速设置不起作用（tts_speed 未接入真实播放链路）

- 根因：设置面板语速 `tts_speed` 只在 `/tts/test` 非流式链路被读取；真实语音播放走流式 `/tts/stream`，其语速取自 `VoiceDeliveryItem.speech_rate` 合同字段，而所有进入播放授权（`web_playback_service.authorize`）的构造点都没传 `speech_rate`（默认 1.0），真实播放语速被固定为 1.0，拖滑块无效。
- 修复：6 处构造点统一注入 `speech_rate=settings_store.current().tts_speed` —— `web/turn_processors.py`（`_voice_item` 与 `_prepare_chat_spoken_delivery`）、`web/api/voice_runtime.py`（欢迎语，原硬编码 1.0）、`web/lab_tools.py`、`web/tool_presentation.py`、`web/api/chat.py`。
- 测试修复：`tests/test_web_voice_runtime_event.py` 欢迎语测试 mock `settings_store.current` 并断言语速透传 1.2；`tests/test_settings_store.py` 补 `setUp` 复位进程内 `_cache`，消除其他测试读真实 settings.json 造成的测试间污染。
- 测试基线：专项 `38/38` 通过；项目正式 `.venv` 全量 `1252` 中 `1251` 通过、`1` 个 error 为 `test_explicit_mode_switch`（`composer.js` 的 `interactionModeState.select('protocol')` 已改为带第二参数，属统一 Turn 前端既有未提交改动，与本修复无关），仅标 `AUTO_OK`。
- 真实验收（2026-08-27）：用户拖滑块后真实播放确认语速跟随设置生效（原话"语速可以了"）；第一句（欢迎语）也跟随语速设置，用户选定方案 A（不再固定 1.0），仅标 `REAL_OK`。

### 2026-08-27 「正在理解」提速探索 + 前端耗时观测接入

- 摸清"正在理解"延迟构成：本质是一次 LLM 调用（非流式、等完整 JSON），延迟 = 首 token 时间 + 输出时长；三条 LLM 链路（`WebSettingsLLMClient`/`src/llm/client.py`/聊天 `run_agent`）均已禁用 thinking，精确命令走本地正则 0 次 LLM，聊天模式已流式。
- 发现：服务端 `TurnTimingRecorder` 已记录完整阶段耗时（`llm_started→llm_completed` 等 `elapsed_ms`）并随 `turn_result` 的 `timing` 字段下发，但前端 `turn_client.js` 未读取、用户看不到。
- 改动：`web/frontend/turn_client.js` 新增 `summarizeServerTiming`，读取 `event.timing` 并计算"理解 LLM / 理解总 / 落盘 / 总"耗时，输出到 `[turn-timing]` console。`node --check` 语法通过，相邻 JS 测试 `voice_delivery_client`、`turn_reply_surface` 通过。
- 尚未真实验收：需用户跑一次真实语音，F12 Console 看 `[turn-timing]` 各阶段秒数，据此判断瓶颈是理解 LLM 还是生成回答，再决定是否上「首句流式语音」。
