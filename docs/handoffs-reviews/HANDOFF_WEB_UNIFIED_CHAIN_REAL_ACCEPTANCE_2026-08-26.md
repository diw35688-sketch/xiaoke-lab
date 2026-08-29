# 交接：Web 统一 Turn 链真实验收进展与未决问题（更新至 2026-08-27）

> 本文档是当日收工时的新交接点，不覆盖 `HANDOFF_WEB_UNIFIED_CHAIN_2026-08-26.md`。
>
> 总体结论：统一 Turn、SQLite 主账、文字/单录/连续通话输入和 SSE 基础链已实现；真实验收已证明 Chat、自由实验、单次语音以及“结束实验记录”的完整收尾链可用。方案实验仍为 `REAL_FAIL`，旧公开接口不得删除，提速任务不得开始。

## 一、今天已经证实的结果

### 1. 文字 Chat：核心链路 `REAL_OK`

- request_id：`web-1787755673861-7`
- `/turn/text` 正常产生 `turn_accepted -> status -> turn_result -> voice_delivery -> done`。
- DeepSeek 结果、Chat Blocks 和 SQLite 提交成功。
- 总耗时约 2478 ms；主要耗时为 LLM 约 2465 ms，SQLite 约 8 ms。
- 屏幕与返回数据已验收；不将其外推为所有语音播放场景均通过。

### 2. 文字自由实验：核心链路 `REAL_OK`

- request_id：`web-1787755997265-10`
- 生成第 18 段实验记录。
- SQLite 中有一条 `lab_records`、一组 `experiment_events`，无 ASR 证据，也没有误写 Chat `messages`。
- 总耗时约 3671 ms；理解约 3653 ms，SQLite 约 12 ms。

### 3. 桌面单次录音：核心链路 `REAL_OK`

- request_id：`web-audio-496356e9-d0b7-408c-a04d-052aa5901c3a`
- 生成第 19 段实验记录。
- ASR 约 1.35 s，理解约 3.71 s，SQLite 约 7 ms，总耗时约 5.07 s。
- WAV 存在，数据库字节数与 SHA-256 可对应；完整最终 `ASRResult` 已入库。

### 4. 网络、启动与前端幂等修复

- `.venv` 在用户真实启动环境中是可用的。Codex 侧出现 `Unable to create process` 时，不得再归因为用户 Python 环境损坏。
- `scripts/start_best.py` 已补项目根路径，修复从 `web` 目录启动时 `ModuleNotFoundError: src`。
- HTTPS 使用本地证书，浏览器会显示不受信任警告；HTTP/HTTPS 必须和实际启动方式一致。
- 前端的 request fingerprint 与最终 Blocks 已分开，修复了服务器最终 Turn 回填时被误判为“同一 request_id 内容冲突”。

### 5. 结束实验/结束连续通话：`REAL_OK`（2026-08-27）

用户已在真实浏览器、麦克风和扬声器环境完成复验，确认以下项目同时通过：

- 精确口述“结束实验记录”走零次 LLM 快速路径，最终业务结果包含 `business.session_ended=true`。
- 结束命令不新增 `lab_record` 或实验事件；下一条实验轮换到新的 `lab_session_id` 并能正常保存。
- 屏幕显示本次实验步骤数和全部未解决待确认问题，保留稳定编号，并区分“待回答”与“已暂缓”；已解决问题不重复显示。
- 收尾语音在现有每轮 50 字预算内朗读精简摘要：说明实验已结束、未解决问题数量并提示查看屏幕；完整问题明细仍由屏幕承担。
- 收尾语音保留播放，连续通话按钮恢复为未通话，麦克风停止且不再提交新分段。
- 服务窗口无 `ValueError` 或 500 错误。

本轮真实请求证据之一：

- request_id：`web-audio-daf62c42-f6be-4ea0-bf4c-531da8a10c82`
- SQLite 中的最终 Turn 已包含完整结束摘要和 `session_ended=true`。

真实验收期间连续暴露并修复了三个缺口：

1. `UnifiedAcceptanceBypass` 原先漏掉 `END_SESSION_EXECUTION`，精确结束命令会抛 `ValueError`。
2. `ExperimentProcessor` 原先把结束回复硬编码为单句，没有读取 SQLite 恢复的 `ReplyCoordinator.active_clarifications()`；现已生成“步骤数 + 未解决问题数量 + 编号/状态/正文”的单一屏幕摘要。
3. 完整屏幕摘要直接作为语音时超过 SSE 每轮 50 字预算：`turn_result` 已上屏，但 `voice_delivery` 生成异常并吞掉后续 `done`，造成既不朗读也不退出。现已把屏幕全文和短语音分开，并保证语音授权失败时已提交 Turn 仍必定发送 `done`。

关键实现位置：

- `web/turn_processors.py`：完整结束摘要、短收尾语音、`SESSION_CLOSING_SUMMARY / SUMMARY` 语义。
- `web/api/turn.py`：提交后语音授权隔离；异常记录 `voice_authorization_failed_after_commit`，但不得阻断 `done`。
- `web/frontend/phone_call.js`：收到结束 Turn 后等待 `voice_delivery` 或 `done`，使用 `stopCall({preservePlayback: true})` 关闭麦克风但保留收尾播放。
- `web/database/turn_store.py`：恢复问题状态并提供准确实验步骤数量。

## 二、今天暴露且尚未完成真实验收的问题

### 1. 方案实验：`REAL_FAIL`

用户真实观察：

- 界面已显示 `experiment/protocol`，但模型仍在追问自由实验留下的问题。
- 对话区看不到方案当前步骤和该做什么。

已核实的根因：

1. `experiment_session_state` 只按 `(conversation_id, lab_session_id)` 保存 `ReplyCoordinator` 和 `SessionContext`。free/protocol 切换时会恢复同一份待确认状态，导致跨模式追问污染。
2. 前端请求前的 `publishProtocolContextBlocks()` 会临时加入 `protocol_card/step_card`，但 `acceptCommittedTurn()` 后会用服务器最终 Turn 替换临时 Turn。服务器 Turn 并不包含这两类 Block，因此步骤卡消失。
3. 新 `ExperimentProcessor` 目前只检查已选方案并取 `step_view`，没有把旧 `RecordService` 中的完整方案确定性评价接回统一 Turn。`evaluation.deviations` 目前仍是空列表。

下次不要只修界面，应完成一个完整能力边界：

- free 与 protocol 的待确认状态隔离，protocol 状态绑定 `protocol_id`。
- `ExperimentProcessor` 执行方案当前步的确定性评价。
- 方案已知值不当作缺失项；只有现场必记缺失或真实偏差才触发方案追问/提示。
- 最终 `ConversationTurn` 直接包含 `protocol_card`、`step_card`、必要的 `safety_alert`，不依赖提交前临时 UI Block。
- 增加 free -> protocol -> free 的状态隔离和恢复测试。

### 2. ASR 证据路径小偏差

- `asr_evidence.audio_rel_path` 已是正确相对路径。
- 但 `payload_json` 中完整 `ASRResult.audio_path` 仍可能是绝对路径。
- 这与“SQLite 只保存相对路径”的最终合同有偏差，应在全部真实验收收口前统一。

## 三、最近自动验证

- 统一链大改完成时的全量 Python 记录：`1211 tests OK`。
- 结束指令修复后的针对性回归：`58 tests OK`。
- 最后增加连续通话关闭后：Python 针对性 `20 tests OK`，`test_phone_call_silero_fallback.js: OK`。
- 结束问题汇总接入后：相关 Python `48 tests OK`。
- 收尾语音预算和 SSE `done` 兜底修复后：相关 Python `37 tests OK`，`test_phone_call_silero_fallback.js: OK`，JavaScript 语法通过。
- `node --check web/frontend/phone_call.js` 通过。
- `git diff --check` 通过；输出只有 Windows LF/CRLF 警告，无空白错误。

自动证据本身仍只是 `AUTO_OK`；结束收尾项另有用户完成的真实浏览器、麦克风和扬声器证据，因此该项可独立标记 `REAL_OK`，不得外推到方案实验、手机或异常注入。

## 四、下次的第一步（不要跳步）

### A. 单独修复方案实验

用一个可独立验证的完整步骤完成：状态隔离 -> 方案评价 -> 最终 Blocks -> SQLite -> 前端显示 -> 真实验收。

## 五、工作区与安全边界

- 当前工作树很脏，包含用户原有改动、本轮改动、未跟踪代码与真实验收产生的 `web/data/`。
- 本轮没有 commit、push或部署。
- 不得使用 `git add -A`，不得删除/覆盖无关改动。
- 真实验收前不得删除 `/asr/transcribe`、`/record`、`/record/stream`、`/chat`、`/chat/stream`。
- 不要因 Codex 沙盒中 `.venv` 启动器被拒绝，就重建或覆盖用户的 Python 环境。用户真实启动证据优先级更高。

## 六、当前标记

```text
统一 Turn / SQLite / SSE 基础链：AUTO_OK
文字 Chat 核心链：REAL_OK
文字自由实验核心链：REAL_OK
桌面单次录音核心链：REAL_OK
结束实验/连续通话：REAL_OK（完整问题上屏、短收尾朗读、麦克风停止、会话轮换均已真实通过）
方案实验：REAL_FAIL
手机、VAD 全流程、断网/失败注入、重启恢复：REAL_PENDING
旧公开接口删除：BLOCKED BY REAL ACCEPTANCE
文字/语音提速：NOT STARTED
```
