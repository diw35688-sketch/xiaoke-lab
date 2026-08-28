# 交接：Web 统一 Turn 生产链（2026-08-26）

> 当前状态：核心替换、SQLite 主账、四类前端入口迁移和自动回归已完成，标记为 `AUTO_OK`。
> 真实浏览器、麦克风、SenseVoice、DeepSeek、SQLite 故障、手机、扬声器和打断尚未由用户验收，不能标记 `REAL_OK`，因此旧公开接口暂未删除。

## 一、已经锁定的结构

三个维度相互独立：

- 输入方式：`text`、`single_recording`、`continuous_call`。
- 业务模式：`chat`、`experiment/free`、`experiment/protocol`。
- 输出方式：屏幕 Block、`voice_delivery`。语音输入不自动决定是否播报。

正式生产链：

```text
文字 ------------------┐
单次录音 -> ASR --------+-> TurnInput
连续通话 -> VAD -> ASR -┘
                           |
                   TurnApplicationService
                    /                \
            ChatProcessor       ExperimentProcessor
                                      |
                         experiment/control/uncertain
                                      |
                         泛化理解、校验、动作规划
                    \                /
                     ConversationTurn / Blocks
                              |
                   SQLite COMMIT -> SSE -> voice_delivery
```

Web 以 SQLite 为唯一提交主账，不双写 JSONL。完整 `ASRResult` 以版本化 JSON 存在 SQLite；原始 WAV 按 conversation/session 保存。终端原有 JSONL 不迁移。JSON/JSONL 文件只在显式导出时产生，当前没有实现导出功能。

## 二、本轮已经实现

### 1. 通用输入和流合同

- `src/core/turn_input.py`：通用 `TurnInput`；文字禁止携带 ASR，语音必须携带最终、原文一致的 `ASRResult`。
- `src/core/turn_request_envelope.py`：语音尚未完成 ASR 前可登记的身份和模式快照。
- `src/core/turn_timing.py`：单调耗时和 UTC 时间点。
- `web/turn_stream_contract.py`：固定 SSE 事件：`turn_accepted`、`turn_status`、`turn_result`、`voice_delivery`、`turn_error`、`done`；预留但不发送 `block_delta`。

### 2. SQLite 主账和事务

`web/database/db.py` 增量创建或扩展：

- `turn_requests`：请求/Turn 身份、模式快照、请求哈希、状态、attempt、最终结果和计时。
- `asr_evidence`：完整 ASRResult JSON、WAV 相对路径、SHA-256、字节数。
- `experiment_events`：每个采用事件独立行，`request_id + event_index` 唯一。
- `experiment_session_state`：ReplyCoordinator 和 SessionContext 快照及 revision。
- `lab_records` 增加 request/conversation/turn 身份。
- `messages` 增加 request/turn/block 身份。
- 所有连接启用 `PRAGMA foreign_keys=ON`，迁移不重写历史业务 JSON。

`web/database/turn_store.py` 已实现：

- 相同 `request_id` + 相同请求重放；不同内容 409 冲突。
- `processing`、`committed`、`failed` 和失败重试 attempt。
- 服务重启将遗留 `processing` 转成 `INTERRUPTED_BY_RESTART` 可重试失败。
- ASR 证据、事件/消息、lab_record、会话状态、最终 Turn 和 committed 状态在一个业务事务内提交。
- 业务写入任一点失败会整体回滚。
- 已提交结果重放不再次处理，也不自动重播语音。
- 删除实验会话或对话时返回关联音频路径，由 API 同步删除 WAV。

注意：业务 COMMIT 后补记的 `persistence_committed` 诊断更新若失败，只记录日志，不能推翻已提交业务或删除已提交 WAV。

### 3. ASR 服务层

`web/asr_application_service.py` 负责：

- backend 创建、单例复用、预热和加载错误隔离。
- 只接受 16 kHz、单声道、16-bit PCM WAV。
- 上传先写 `.pending`，计算 SHA-256；ASR 成功后移到 conversation/session 稳定目录。
- 返回完整最终 `ASRResult`，不判断 Chat/实验、不调用实验 LLM、不写业务记录、不生成 TTS。
- 失败清理 pending/未提交音频；启动清理超过 24 小时且无数据库引用的 pending 文件。

旧 `/asr/status`、`/asr/warmup`、`/asr/transcribe` 已复用该服务。`/asr/transcribe` 只作为迁移兼容入口，不是正式 Turn 权威入口。

### 4. 业务处理和六步泛化

- 统一理解、分派、实验采用和澄清动作现在读取可信 `raw_text`，ASR 证据为可选；文字实验不再伪造 ASRResult。
- `ChatProcessor` 只生成 Chat 消息和 Turn/Block，不写 `lab_records`。
- `ExperimentProcessor` 处理 `experiment/control/uncertain`：明确 control 走规则快速路径、零次 LLM；uncertain 不产生实验记录或状态副作用；experiment 才产生事件和 lab_record。
- 实验处理从 SQLite 快照恢复 ReplyCoordinator/SessionContext，在隔离副本上理解和规划；只有最终事务 COMMIT 后新状态才成为主账。
- 同一 `(conversation_id, lab_session_id)` 使用单线程 FIFO；不同实验会话可以并行。
- 运行时 `_submissions` 只保存进行中的 Future，完成/失败即移除，跨重启幂等以 SQLite 为准。

### 5. 新接口和前端迁移

- `POST /turn/text`：JSON，服务端强制文字来源、无 ASR。
- `POST /turn/audio`：multipart 的 `audio + metadata`，只接受单次录音或连续通话；客户端不能上传 ASRResult。
- `GET /turn/requests/{request_id}`：只返回状态、attempt、错误和阶段计时诊断。
- 删除接口：按 conversation 或 experiment session 删除统一 Turn 数据及关联 WAV。

四个生产入口已经直接使用新接口：

- 桌面文字：`web/frontend/streaming_chat_v2.js -> /turn/text`。
- 桌面单次录音：`voice_asr.js -> /turn/audio`。
- 手机单次录音：`mobile.js -> /turn/audio`。
- 连续通话/VAD：`phone_call.js -> /turn/audio`，不再先 `/asr/transcribe` 再伪装成文字提交。

`web/frontend/turn_client.js` 统一解析 SSE、保存服务端 conversation_id，并把浏览器侧接受/屏幕/语音事件时间输出到诊断控制台。主界面只显示阶段文案，不显示毫秒。

迁移期旧 `/chat`、`/chat/stream`、`/record`、`/record/stream` 仍保留原 HTTP 响应外形，但内部只构造 `TurnInput` 并调用同一个 `TurnApplicationService`；旧路由文件中的第二套 Chat/Record producer 已清除。

## 三、自动验证证据

当前最近验证：

- Python 全量：`1211 tests OK`（旧 producer 绑定测试已替换为统一兼容适配器测试）。
- Node：9 个 `tests/js/*.js` 套件全部通过。
- 新增专项覆盖：Turn 合同、SSE、计时、SQLite 迁移/事务/幂等/重放/冲突/失败重试/重启恢复、状态快照、文字 control 零 LLM、experiment/control/uncertain 互斥、ASR pending/哈希/稳定路径/清理、音频证据入库、API SSE 顺序、前端入口。
- 所有改动 JS 通过 `node --check`。
- `git diff --check` 通过。

这些证据只允许标记 `AUTO_OK`，不证明真实 SenseVoice、DeepSeek、浏览器、手机、麦克风、扬声器或用户体验。

## 四、仍然没有完成的事项

### 1. 必须由用户完成的真实验收

按顺序验证并记录 request_id：

1. 文字 Chat、文字自由实验、文字方案实验。
2. 桌面单录、手机单录、连续通话、Silero VAD 和 RMS 回退。
3. 实验事实记录、查看、暂缓、回答、确认、结束。
4. 页面刷新、服务重启、同 request 重提、内容冲突。
5. 网络中断、ASR 失败、LLM 降级、保存失败。
6. 同一 request/turn/session 能追溯屏幕 Block、SQLite、WAV、ASRResult、事件和澄清状态。
7. `voice_delivery` 只在 COMMIT 后出现；真实扬声器播放与用户打断正常。

只有上述通过才能标记 `REAL_OK`。

### 2. 真实验收后才能做

- 删除公开 `/asr/transcribe`、`/record`、`/record/stream`、`/chat`、`/chat/stream`。
- 删除前端兼容 fallback 和扫描仓库确认生产代码无旧入口残留。
- 独立开展提速任务：依据本轮计时处理文字 token 真流式、首句 TTS、连接复用和快速路径。

### 3. 本阶段明确没有实现

- 不发送 `block_delta`，普通正文仍在完整结果确定后发布。
- 不提前播放语音，不改变 TTS 长度策略。
- 不实现 JSON/JSONL 导出。
- 不实施任务 38/39 的五分支和新工具权限模型。

## 五、下一次直接从哪里开始

先启动真实 Web，完成“文字 Chat → 文字自由实验 → 桌面单录”三个最小验收并查看：

- 浏览器 SSE 是否按 `turn_accepted -> status -> turn_result -> voice_delivery? -> done`。
- `GET /turn/requests/{request_id}` 的状态/计时。
- SQLite 的 `turn_requests`、`messages` 或 `lab_records`、`asr_evidence`、`experiment_events`、`experiment_session_state`。
- `web/data/turn_audio` 中 WAV 与数据库相对路径/哈希是否对应。

这三个通过后再验手机和连续通话。不要在真实验收前删除旧接口，也不要开始文字/语音提速。
