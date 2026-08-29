# Web 统一 Turn 生产链：零基础学习与当前验收说明

> 版本：2026-08-26 学习版
> 项目：`C:\Users\dahli\Documents\107`
> 说明：这是目前实现的阶段性教材，不是“全部验收完成”的最终版。

## 先看结论

这次改造的核心，是不再让文字、单次录音和连续通话各走一套生产流程。它们先汇合为同一种 `TurnInput`，再由 `TurnApplicationService` 统一分派、统一提交 SQLite，最后通过 SSE 返回屏幕 Blocks 和语音播放许可。

```text
用户提交文字/录音
→ TurnInput
→ ASRApplicationService（只有语音需要）
→ TurnApplicationService
→ ChatProcessor / ExperimentProcessor
→ SQLite 事务提交
→ ConversationTurn / Blocks
→ SSE
→ 屏幕显示与 voice_delivery
```

### 当前证据等级

| 能力 | 当前结果 |
|---|---|
| 文字 Chat 核心链 | `REAL_OK` |
| 文字自由实验核心链 | `REAL_OK` |
| 桌面单次录音核心链 | `REAL_OK` |
| 统一 Turn、SQLite、SSE 主体 | `AUTO_OK` |
| 结束连续通话 | 代码修复后 `AUTO_OK / REAL_PENDING` |
| 方案实验 | `REAL_FAIL`，已发现状态串扰和步骤卡消失 |
| 手机、完整 VAD、断网和故障注入 | `REAL_PENDING` |
| 删除旧接口 | 禁止，必须等全部真实验收 |
| 文字/语音提速 | 尚未开始 |

- `AUTO_OK`：代码合同和自动测试通过。
- `REAL_OK`：用户在真实浏览器、服务和数据上看到正确结果。
- `REAL_FAIL`：真实使用已证明它不符合目标。
- `REAL_PENDING`：不能根据代码推测真实体验，还要人工验收。

---

## 一、统一 Turn 到底是什么

### 1. 一句话总结

Turn 是用户的一次完整交互：从提交文字或语音开始，到系统完成理解、保存、屏幕显示和语音授权为止。

### 2. 用户实际操作

用户可以在输入框发文字、点击单次录音，或开启连续通话由 VAD 自动切段。三种操作的前半段不同，但进入业务前都会形成 `TurnInput`。

### 3. 白话数据流

```text
用户说话/打字
→ 前端收集输入和本轮身份
→ 语音先由 ASR 变成可信文字
→ 所有输入形成 TurnInput
→ 按业务模式选择 Chat 或实验处理器
→ 生成最终 ConversationTurn / Blocks
→ SQLite 整笔提交
→ SSE 返回屏幕内容和语音许可
```

### 4. 专业设计思想

这是“输入汇合—业务分支—输出再汇合”的沙漏结构。它把三个维度分开：

- 输入方式：`text`、`single_recording`、`continuous_call`。
- 业务模式：`chat`、`experiment/free`、`experiment/protocol`。
- 输出方式：屏幕 Blocks 和 `voice_delivery`。

语音输入不代表必须播报，文字输入也可以触发语音回复。

### 5. 具体代码

- `src/core/turn_input.py`
  - `TurnInput`：本轮可信输入合同。
  - `__post_init__()`：检查模式、来源、原文和 ASR 是否一致。
  - `to_wire()`：转成可序列化数据。
- `src/core/turn_request_envelope.py`：语音尚未得到转写前，先固定 request/turn/模式身份。
- `src/core/conversation_turn.py`：定义最终 Turn 和用户文字、助手文字、记录卡、语音等 Block。

### 6. 失败场景

- 文字 Turn 上传 ASRResult：拒绝。
- 语音 Turn 没有最终 ASRResult：不进入业务处理。
- ASR 文字与 `raw_text` 不一致：拒绝，防止客户端覆盖转写。
- Chat 带实验上下文，或实验未选 free/protocol：拒绝。

### 7. 验证证据

`tests/test_turn_input_and_stream_contract.py`、`tests/test_turn_application_service.py`、`tests/test_turn_api.py` 覆盖合同、接口、SSE 顺序和错误，属于 `AUTO_OK`。

### 8. 得失与取舍

好处是统一、可追溯、好测试。代价是合同更严格，过去“随手传一个字典”的方式会被拒绝，而且所有前端都必须迁移。

### 9. 自己怎么阅读

先打开 `src/core/turn_input.py`，看它要求哪些字段。再搜索 `TurnInput(` 看哪些接口创建它，最后搜索 `.raw_text` 看业务如何读取它。

### 10. 自己怎么写

1. 先写不依赖 Web 的数据类。
2. 写清楚它的不变条件。
3. 写非法组合测试。
4. 再让 HTTP 接口将用户输入翻译成该数据类。
5. 业务服务只接收通过验证的对象。

---

## 二、ASRApplicationService 是做什么的

### 1. 一句话总结

ASR 服务层只负责把合法 WAV 变成完整、最终、可追溯的 `ASRResult`，不决定这句话是 Chat 还是实验。

### 2. 用户实际操作

用户点击录音或进入连续通话后，浏览器把音频编码为 16 kHz、单声道、16-bit PCM WAV，通过 `/turn/audio` 上传。

### 3. 白话数据流

```text
WAV 上传
→ 验证格式
→ 写入 .pending
→ 计算 SHA-256
→ SenseVoice 识别
→ 得到 ASRResult
→ 移到稳定目录
→ 返回转写、模型原文、时长、耗时、模型名和语言
```

### 4. 专业设计思想

ASR 是输入适配，不是业务决策。单录、连续通话和旧兼容接口可复用同一 backend，不用每条路都加载一次模型。

### 5. 具体代码

- `web/asr_application_service.py`
  - `_get_backend()`：延迟创建并复用 ASR backend。
  - `validate_wav()`：检查 WAV 格式。
  - `recognize_upload()`：完成 pending、哈希、识别和稳定存储。
  - `cleanup_pending()`：清理崩溃留下的孤儿临时文件。
  - `delete_audio()`：删除会话时删除归属音频。
- `web/api/asr.py`
  - `/asr/status`、`/asr/warmup` 仍保留。
  - `/asr/transcribe` 是迁移兼容口，不是正式 Turn 生产入口。

### 6. 失败场景

- WAV 格式不对：业务处理不开始。
- ASR 失败：请求标记失败，不生成假文字。
- ASR 成功但后续 SQLite 失败：不能说“已记录”，未提交音频需清理。
- 进程崩溃：超过 24 小时且没有数据库引用的 pending 文件由启动清理器删除。

### 7. 验证证据

真实单录 request `web-audio-496356e9-d0b7-408c-a04d-052aa5901c3a` 已验证 SenseVoice、WAV、SHA-256、SQLite 和实验记录的关联。

尚未收口的偏差：`asr_evidence.audio_rel_path` 是相对路径，但 `payload_json` 中的 `ASRResult.audio_path` 仍可能是绝对路径。

### 8. 得失与取舍

保存完整 ASRResult 占用更多空间，但能追溯当时的模型、识别耗时和原始输出，比只存一句转写更可靠。

### 9. 自己怎么阅读

从 `recognize_upload()` 开始，顺着 `pending_path -> backend.recognize -> stable_path -> RecognizedAudio` 阅读。遇到 `ASRResult` 时再打开 `src/asr/schemas.py`。

### 10. 自己怎么写

先定义“什么音频才合法”，再定义“识别成功必须返回哪些证据”，最后写 pending、成功、失败和崩溃四类测试。

---

## 三、TurnApplicationService 如何统一调度

### 1. 一句话总结

`TurnApplicationService` 是生产链的总调度：它管幂等、并发、分派、进度和最终提交，但不亲自理解 Chat 或实验语义。

### 2. 用户实际操作

发送后，页面会陆续显示“正在识别语音”、“正在理解”、“正在保存”。这些是同一 Turn 的进度，不是多次独立业务请求。

### 3. 白话数据流

```text
先登记 request_id 已开始处理
→ 如果是语音，先保存和 ASR
→ 按 interaction_mode 选处理器
→ 在数据库事务外等待 ASR/LLM
→ 得到 PreparedTurn
→ 开短 SQLite 事务整笔写入
→ COMMIT 后才发布 turn_result 和 voice_delivery
```

### 4. 专业设计思想

#### 幂等

幂等的白话意思是：同一件事重试多次，不能重复保存多份。

- 同一 `request_id` + 同一内容：重试或重放。
- 同一 `request_id` + 不同内容：409 冲突，不允许覆盖。
- 已提交请求：返回 SQLite 中的最终结果，不再调 LLM/ASR，不自动重播语音。

#### 不长时间锁住 SQLite

LLM 或 ASR 可能等几秒。如果一直持有 SQLite 写事务，其他请求容易遇到 `database is locked`。因此等模型时不持有最终业务写事务。

### 5. 具体代码

- `web/turn_application_service.py`
  - `submit()`：文字 Turn 入口。
  - `submit_audio()`：语音 envelope + WAV 入口。
  - `_active_or_conflict()`：检查内存中正在执行的同名请求。
  - `_executor_for()`：同一实验会话 FIFO，不同会话可并行。
  - `_execute_audio()`：先 ASR，再构造完整 TurnInput。
  - `_execute_prepared()`：调处理器、验证结果并提交 SQLite。
  - `_forget()`：完成后从内存 `_submissions` 移除，避免无限增长。

### 6. 失败场景

- 重启留下 `processing`：改为 `INTERRUPTED_BY_RESTART`，允许重试，不假装已完成。
- 理解成功但 SQLite 失败：整个业务事务回滚，不发布成功 Block，不授权语音。
- 重连正在执行的 request_id：共用同一 Future，不重复运行。

### 7. 验证证据

自动测试已覆盖同内容重试、内容冲突、进行中连接、已提交重放、失败 attempt 增加和重启恢复。真实浏览器已证明正常请求可提交和查询计时。

### 8. 得失与取舍

这增加了 request_id、hash、status、attempt 等复杂度，换来的是断网或用户重点时，不会把同一实验操作保存两次。

### 9. 自己怎么阅读

从 `submit()` 开始，沿 `reserve -> _register -> _execute -> _execute_prepared -> store.commit` 顺序读，不要一开始就深入 LLM 细节。

### 10. 自己怎么写

先画状态机：`processing -> committed` 或 `processing -> failed`。再写每个状态的重试规则，最后接业务处理器。

---

## 四、ChatProcessor 和 ExperimentProcessor 为什么分开

### 1. 一句话总结

Chat 要生成对话回答，实验要生成事件、记录卡和待确认状态；它们可共用 Turn 基础，但不能共用业务写入。

### 2. 用户实际操作

- 自由聊天：用户问问题，页面显示助手回答。
- 自由实验：说“加入5毫升缓冲液”，页面显示实验记录卡，SQLite 保存结构化事件。
- 控制命令：“查看待确认问题”或“结束实验记录”应走零次 LLM 快速路径。

### 3. 白话数据流

```text
interaction_mode == chat
→ ChatProcessor
→ 读历史消息
→ DeepSeek
→ user_text + assistant_text + voice block

interaction_mode == experiment
→ ExperimentProcessor
→ 从 SQLite 恢复 ReplyCoordinator / SessionContext
→ 区分 experiment / control / uncertain
→ 必要时产生事件、record_card 和新状态快照
```

### 4. 专业设计思想

这是策略分派和业务边界。输入方式不等于业务模式：语音可用来 Chat，文字也可记录实验。

实验六步可白话理解为：

1. 观察这句话是实验、控制还是不确定。
2. 关联可信输入证据。
3. 采用可信实验事件。
4. 规划追问、回答或控制动作。
5. 把业务事实和状态一起提交。
6. 从确定结果生成最终 Turn/Blocks。

### 5. 具体代码

- `web/turn_processors.py`
  - `PreparedTurn`：处理器产出的待提交包。
  - `ChatProcessor.prepare()`：生成 Chat 回答、消息和语音计划。
  - `ExperimentProcessor.prepare()`：恢复实验状态，调统一观察链，规划记录/追问/控制结果。
  - `_reply_text()`：把业务结果变成用户回复。
- `src/core/unified_acceptance_bypass.py`：连接理解、分派、采用和澄清动作。
- `src/core/reply_coordinator.py`：保存待确认问题和当前活跃问题。
- `src/core/session_context.py`：保存最近实验事件的短上下文。

### 6. 失败场景

- Chat 错写 `lab_records`：测试应拦截。
- experiment 错进 ChatProcessor：分派合同应拦截。
- uncertain：不产生实验事实和状态副作用。
- 明确 control 却调 LLM：快速路径测试应失败。

### 7. 验证证据

文字 Chat、文字自由实验和单录自由实验已有真实请求、屏幕和 SQLite 证据。结束命令修复有自动测试，但尚未在完整重启后真实复验。

### 8. 得失与取舍

处理器分开后业务边界清楚，但 free/protocol 的内部状态边界仍未完成。不能因 Turn 上显示 `experiment/protocol` 就认为方案业务已接通。

### 9. 自己怎么阅读

对比 `ChatProcessor.prepare()` 和 `ExperimentProcessor.prepare()` 的返回值，再顺着 `PreparedTurn` 看数据在 `TurnStore.commit()` 中写到哪里。

### 10. 自己怎么写

处理器只做理解和规划，不在中间随手 commit。先返回 PreparedTurn，由应用服务统一提交。

---

## 五、SQLite 主账和事务

### 1. 一句话总结

SQLite 主账表示：只有 SQLite 中已 COMMIT 的数据，才能作为“这件事真的发生了”的依据。

### 2. 用户实际操作

用户说完实验后，只有 SQLite 成功保存输入证据、事件、记录、状态和最终 Turn，页面才能显示“已记录”，扬声器才能播放。

### 3. 白话数据流

```text
短事务登记 turn_requests=processing
→ 在事务外做 ASR/LLM
→ 得到完整待提交结果
→ 开最终 SQLite 事务
→ 写证据、事件/消息、记录、会话状态、Turn、计时
→ turn_requests=committed
→ COMMIT
→ 发布成功结果和语音许可
```

### 4. 专业设计思想

事务像“整单结账”：要么整单成功，要么整单作废。不能实验记录写入了，但待确认状态没写；也不能页面说已保存，数据库却失败。

### 5. 具体代码和表

- `web/database/db.py`：增量建表和加列，开启外键。
- `web/database/turn_store.py`
  - `reserve()` / `reserve_envelope()`：登记请求并判断重试/冲突/重放。
  - `commit()`：最终业务事务。
  - `fail()`：记录失败代码和计时。
  - `diagnostics()`：返回状态和阶段耗时。
  - `load_experiment_state()`：从 SQLite 恢复实验协调状态。

| 表 | 保存内容 |
|---|---|
| `turn_requests` | 请求身份、模式、状态、attempt、最终 Turn 和计时 |
| `asr_evidence` | 完整 ASRResult、WAV 相对路径、SHA-256、字节数 |
| `experiment_events` | 已采用的版本化实验事件 |
| `experiment_session_state` | ReplyCoordinator 和 SessionContext 快照 |
| `lab_records` | 用户可查看的实验记录 |
| `messages` | Chat 用户/助手消息 |

### 6. 失败场景

最终事务任一步失败，其他本轮业务写入一起回滚。失败 Turn 保留错误码和 attempt，但不伪造成功记录。

### 7. 验证证据

真实 request_id 已能查到 `turn_requests`、`lab_records`、`experiment_events`、`asr_evidence` 和 WAV。自动测试覆盖 SQLite 失败时不留部分业务数据。

### 8. 得失与取舍

JSONL 方便人直接打开，但难以同时保证多表一起成功、幂等和并发查询。Web 因此以 SQLite 为主账。JSON/JSONL 只用于显式导出，当前尚未实现导出功能。

### 9. 自己怎么阅读

先看 `db.py` 的表结构，再看 `TurnStore.commit()` 每个 `INSERT/UPDATE`。问自己：这是证据、业务事实、状态，还是输出快照？

### 10. 自己怎么写

先画“本轮必须一起成功的数据”，再把它们放进同一事务函数，然后写每个中间点故意抛错的测试。

---

## 六、SSE、Blocks 和 voice_delivery

### 1. 一句话总结

SSE 让同一 HTTP 请求持续发送阶段事件；Blocks 说明页面显示什么，`voice_delivery` 单独说明是否允许播放。

### 2. 用户实际操作

发送后先看到“正在理解”，最后看到记录卡或助手回复。如果播放策略允许，提交后收到 `voice_delivery`。

### 3. 白话数据流

```text
turn_accepted   服务器已接收并确定身份
turn_status     正在保存音频/ASR/分派/理解/校验/保存
turn_result     SQLite 已提交的最终 Turn
voice_delivery  本轮可播放的语音意图
done            SSE 流结束
```

### 4. 专业设计思想

屏幕上有文字不等于扬声器可以说。播放是显式授权，因为语音可能打断用户，也可能在保存失败后误报“已记录”。

### 5. 具体代码

- `web/turn_stream_contract.py`：生成稳定 SSE 事件。
- `web/api/turn.py`
  - `/turn/text`、`/turn/audio`是新生产入口。
  - `_stream()` 发布进度、结果、语音和 done。
- `web/frontend/turn_client.js`
  - `submitText()` / `submitAudio()` 提交 Turn。
  - `consume()` 解析 SSE 并记浏览器时间点。
- `web/frontend/conversation_turn_store.js`
  - 保存当前 Turn 快照。
  - request 的不变指纹与会变化的最终 Blocks 分开，避免误报 request_id 冲突。

### 6. 失败场景

- HTTP 连不上：先查服务、端口、HTTP/HTTPS、base_url 和代理。
- SSE 收到 `turn_error`：服务已收到请求，但业务处理失败。
- 有 `turn_result` 却没声音：查 `voice_delivery`、静音、队列、浏览器权限，不要回头猜 ASR。

### 7. 验证证据

真实 Chat、文字实验和单录请求都看到正确 SSE 顺序，`voice_delivery` 出现在 `persistence_committed` 之后。

### 8. 得失与取舍

目前 SSE 是阶段流，不是每个 token 的文字流。这让生产链和提交边界先稳定，代价是用户仍要等完整正文。

### 9. 自己怎么阅读

打开浏览器 Network，选中 `/turn/text` 或 `/turn/audio`，对照事件顺序，再看 `web/api/turn.py::_stream()`。

### 10. 自己怎么写

先写事件合同和顺序测试，再写生成器。不要让前端根据文案猜事件类型。

---

## 七、计时点如何定位慢在哪里

### 1. 一句话总结

计时不会让系统自动变快，它先把“慢”分成 ASR、LLM、校验、SQLite、屏幕和 TTS 几段。

### 2. 用户实际操作

在 Network 的 `turn_result.timing` 或 `GET /turn/requests/{request_id}` 查阶段耗时。主界面只显示阶段文案，不用毫秒数据干扰使用。

### 3. 白话数据流

`request_received` 是起点，每到关键边界就打时间戳。最后不只看“总共5秒”，而是看“ASR 1.35秒、理解3.71秒、SQLite 7毫秒”。

### 4. 专业设计思想

耗时用单调时钟计算，避免系统时间校准造成负耗时；同时记 UTC 时间戳，便于和日志、SQLite 对齐。

### 5. 具体代码

- `src/core/turn_timing.py`：`TurnTimingRecorder`。
- 服务端：`audio_saved`、`asr_started/completed`、`understanding_started/completed`、`persistence_started/committed`。
- Chat：`llm_started`、`first_chunk`、`llm_completed`。当前 `first_chunk` 不代表前端已看到 token，因为正文真流式未实现。
- 浏览器：`turn_client.js` 记 accepted、screen_published、voice_delivery_received。

### 6. 失败场景

请求中途失败时，已记录时间点仍写入失败 Turn，用来判断失败在 ASR、理解还是保存阶段。

### 7. 验证证据

- 文字 Chat request `web-1787755673861-7`：总耗时约 2478 ms，LLM 约 2465 ms，SQLite 约 8 ms。
- 文字自由实验 request `web-1787755997265-10`：总耗时约 3671 ms，理解约 3653 ms，SQLite 约 12 ms。
- 单录 request `web-audio-496356e9-d0b7-408c-a04d-052aa5901c3a`：ASR 约 1.35 s，理解约 3.71 s，SQLite 约 7 ms，总计约 5.07 s。

这些数据证明当前主要瓶颈是模型理解和 ASR，不是 SQLite。

### 8. 得失与取舍

计时字段让数据更多，但避免了“感觉是 SQLite 慢”这类无证据优化。

### 9. 自己怎么阅读

拿一个 request_id，同时对照 Network `timing`、SQLite `turn_requests.timing_json` 和终端日志。

### 10. 自己怎么写

计时点放在服务边界，每个点要回答“哪个阶段刚开始或刚完成”。

---

## 八、当前已发现但未解决的问题

### 1. 方案实验不是只差一张界面卡片

真实验收已证明：切到 `experiment/protocol` 后还在追问 free 模式的问题，而且用户看不到当前步骤。

原因有三层：

1. SQLite 实验状态只按 `(conversation_id, lab_session_id)` 恢复，free/protocol 共用 ReplyCoordinator。
2. 前端提交前临时加的 protocol/step Blocks，被服务器最终 Turn 覆盖。
3. 新 `ExperimentProcessor` 还没完整接回方案当前步的确定性评价，`deviations` 仍可能是占位空数据。

正确修复必须包含：状态隔离、protocol_id 绑定、方案评价、最终 protocol/step Blocks、SQLite 和真实验收。

### 2. 结束连续通话已修代码，但未真实复验

已完成：

- 精确“结束实验记录”走 `END_SESSION_EXECUTION`。
- 返回 `session_ended=true`。
- 提交后轮换新 lab_session_id。
- 连续通话停麦克风和队列，保留结束播报。

但最后一次真实运行仍是修复前的旧 Python 进程。下次必须完整停服务、只启动一个新进程、`Ctrl+F5`，再说“结束实验记录”。

“到这里吧”是模糊表达，真实数据显示它被判为 `abstention`，不能当成精确结束测试。

### 3. 旧公开接口还不能删

`/asr/transcribe`、`/record`、`/record/stream`、`/chat`、`/chat/stream` 仍在迁移兼容期。手机、连续通话、VAD、重启恢复和故障流程全部 `REAL_OK` 后才能删除。

### 4. 提速尚不能开始

计时基础已有，但先要保证数据流、模式边界、保存和播放正确。文字 token 流式、首句 TTS、连接复用和快速路径应在验收后成为独立任务。

---

## 九、新手如何顺着代码阅读

不要一次打开几十个文件。每轮只回答一个问题。

### 第一轮：用户提交了什么

1. `web/frontend/turn_client.js`
2. `web/api/turn.py`
3. `src/core/turn_input.py`

问：前端发送哪些身份？服务端为什么不信客户端上传的 ASRResult？

### 第二轮：谁在调度

1. `web/turn_application_service.py::submit()`
2. `web/turn_application_service.py::submit_audio()`
3. `web/turn_application_service.py::_execute_prepared()`

问：什么时候 processing？什么时候选处理器？什么时候 commit？

### 第三轮：业务如何分开

1. `web/turn_processors.py::ChatProcessor`
2. `web/turn_processors.py::ExperimentProcessor`
3. `src/core/unified_acceptance_bypass.py`

问：哪些数据只有 Chat 写？哪些只有实验写？control 为什么不一定调 LLM？

### 第四轮：数据最后到哪里

1. `web/database/db.py`
2. `web/database/turn_store.py::commit()`
3. `web/database/turn_store.py::load_experiment_state()`

问：证据、业务事实、会话状态和最终输出分别存在哪里？

### 第五轮：页面为什么显示和说话

1. `web/api/turn.py::_stream()`
2. `web/turn_stream_contract.py`
3. `web/frontend/conversation_turn_store.js`
4. `web/frontend/voice_delivery_client.js`

问：屏幕 Block 和播放授权为什么要分开？

---

## 十、新手如何从零写出类似功能

假设新增“图片输入”，可按下面顺序：

1. **合同**：定义图片来源、身份和不信任的客户端字段，先写非法组合测试。
2. **输入服务**：校验、存储证据、调图像 backend，产生可信结果，不决定 Chat/实验。
3. **应用服务**：复用原有幂等、调度和最终事务。
4. **仓储**：先回答证据存哪里、SQLite 存哪些元数据、删除时如何清理，再写 SQL。
5. **Blocks**：定义稳定 `image_card` payload，再写前端渲染，不让前端理解数据库行。
6. **失败测试**：覆盖格式错误、backend 失败、重试、request_id 冲突、SQLite 回滚、删除级联和重启。
7. **真实验收**：假 backend 通过只能标 `AUTO_OK`；真浏览器、真图片、真 backend 和真 SQLite 通过才标 `REAL_OK`。

---

## 十一、下次继续工作的顺序

1. 完整停掉 8000 端口的旧 Python 服务。
2. 只启动一个新服务，浏览器 `Ctrl+F5`。
3. 复验连续通话中精确说“结束实验记录”。
4. 确认 `session_ended=true`、结束播报、麦克风关闭和新 lab_session_id。
5. 该项 `REAL_OK` 后，单独实现方案实验完整接入。
6. 继续手机、VAD、重启、断网和失败注入验收。
7. 全部真实验收后才删旧接口。
8. 然后建独立提速任务，根据 timing 数据优化。

---

## 十二、学习时记住的五句话

1. 前端发出事件，不代表服务端已完成业务。
2. 模式标签正确，不代表该模式的处理、状态和输出已全部接通。
3. 屏幕出现“已记录”，必须能反向追溯到 SQLite COMMIT。
4. 自动测试证明代码合同，真实验收才能证明浏览器、设备、模型和体验。
5. 优化前先计时，扩展前先把主账和失败边界写清楚。

## 参考交接文档

- `docs/HANDOFF_WEB_UNIFIED_CHAIN_2026-08-26.md`：统一 Turn 实现交接。
- `docs/HANDOFF_WEB_UNIFIED_CHAIN_REAL_ACCEPTANCE_2026-08-26.md`：真实验收结果、失败和下次起点。
