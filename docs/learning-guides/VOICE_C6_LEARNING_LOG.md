# VOICE-C6 学习日志：从双界面补丁到统一对话工作区

> 面向对象：希望从白话理解逐步进入专业开发，而不是只看结论型总结的项目参与者。  
> 当前阶段：第 33 项 `VOICE-C6-UNIFIED-CONVERSATION-SURFACE`。  
> 当前唯一下一项：33d `VOICE-C6-A4-EXPLICIT-MODE-SWITCH`。  
> 维护原则：每完成一个完整、可独立验证的能力，追加一节；自动测试、生产接线和真实体验必须分开记录。

## 1. 这份日志怎样维护

每个新条目固定回答八个问题：

1. 用户实际遇到了什么；
2. 修改前的真实缺口是什么；
3. 用白话怎样理解；
4. 对应的专业概念是什么；
5. 当前项目的数据怎样流动；
6. 哪些文件、函数和字段可以亲自复核；
7. 证据能证明与不能证明什么；
8. 唯一下一步是什么。

状态只使用以下证据等级：

```text
DESIGN：合同或方案已明确，尚未完成代码
CODED：实现已存在，尚未完成足够自动验证
AUTO_OK：相关自动测试通过
REAL_OK：真实浏览器、麦克风或设备按记录场景通过
UX_CONFIRMED：用户确认实际交互可以接受
```

## 2. 2026-08-25：真实验收为什么推翻了“已经统一”的表面结论

### 2.1 用户实际遇到什么

在真实浏览器中开启连续通话和语音播报后：

```text
用户讲话成功
→ ASR 成功
→ Chat 文字回复成功
→ 页面没有声音
```

服务端日志里有 `/asr/transcribe` 和 `/chat/stream`，但没有 `/tts`，也没有
`tts_started/finished/stopped/failed`。因此问题不在喇叭开关，也没有证据表明 TTS 已经生成后播放失败；
真正断点是普通 Chat 回复没有形成语音候选。

### 2.2 白话理解

此前系统修好了“拿到一张广播稿以后，什么时候允许广播”，却没有保证普通聊天一定会产生广播稿。

```text
播放调度正确
≠ 每类回复都已经进入播放调度
```

### 2.3 专业概念

- 候选生产者（candidate producer）：决定有没有可交付语音；
- 内容政策（content policy）：决定哪些内容适合出声；
- 播放政策（playback policy）：决定现在能不能播；
- 生产接线（production wiring）：真实入口是否真的把候选送到调度器；
- 证据边界（evidence boundary）：测试覆盖哪一跳，结论就只能写到哪一跳。

### 2.4 当前项目怎样体现

- 普通 Chat 正文通过 `screen_delta` 显示；
- 只有带 `ToolVoiceDeliveryBatch` 的工具结果原本会调用 `web_playback_service.authorize()`；
- 试验性 `ASSISTANT_REPLY` 证明普通 Chat 可以在完整回答后进入 Scheduler；
- 但它暂时复用了实验语音“首句、最多 25 字”的政策，不是最终 Chat 策略。

复核路线：

```text
web/frontend/composer.js::send
→ web/frontend/streaming_chat_v2.js::form.onsubmit
→ POST /chat/stream
→ web/api/chat.py::chat_stream
→ web/playback_runtime.py::ConversationPlaybackRegistry.authorize
→ voice_delivery
→ web/frontend/voice_delivery_client.js::consumeVoiceDelivery
```

### 2.5 自动证据与真实证据

相关专项曾得到 `43/43`，证明试验性普通回复候选没有破坏所覆盖的流事件与播放合同。

它不能证明：

- Chat 最终语音长度和分句策略合理；
- 普通 Chat、自由实验、方案实验和 Tool 都已经统一；
- 真实扬声器一定播放；
- 用户讲话时一定不抢播；
- 页面交互已经容易理解。

### 2.6 本次学到什么

看到“Scheduler 已接入”时，必须继续问：

> 谁产生候选？哪些内容没有候选？真实入口是否调用了它？

## 3. 2026-08-25：输入方式、工作模式和业务分支不是一回事

### 3.1 白话理解

用户用键盘还是麦克风，只说明“话是怎样送进来的”；用户是在聊天还是记录实验，才决定“系统应该怎样理解”。

```text
输入方式：text / recording / call
工作模式：chat / experiment
实验上下文：free / protocol
业务分支：experiment / control / tool / chat / uncertain
```

不能再用“点了哪个按钮”暗中猜测业务模式。

### 3.2 当前缺口

当前 Composer 会把文字复制到隐藏的旧 `#message`，再触发旧 `#form`；
`streaming_chat_v2.js` 只发送 `message/conversation_id`。请求没有：

```text
turn_id
input_source
interaction_mode
experiment_context
mode_version
```

因此当前所有文字先进入 Chat Agent，模型可能根据句子自行调用记录 Tool。看起来是 Chat 输入框，
却可能产生实验写入副作用。

### 3.3 目标设计

界面显式提供：

```text
[自由聊天] [实验记录]

实验记录：
- 自由实验
- 当前方案实验
```

每个请求冻结提交时的模式快照。即使请求处理中用户切换模式，旧请求也按提交时语义完成。

专业概念：正交维度（orthogonal dimensions）、请求级快照（request-scoped snapshot）、
乐观版本（mode version）、竞态条件（race condition）。

## 4. 2026-08-25：自由实验没有方案，但仍然可以追问

### 4.1 白话理解

“没有方案”只表示没有预先规定的字段，不表示用户说得不完整时系统必须沉默。

用户说：

> 加入了盐酸。

自由实验可以先保存原始事实，再判断影响复现、判断或安全的关键缺口，并只问最关键的一项：

> 已记录。加入了多少？

### 4.2 自由实验与方案实验的区别

| 类型 | 追问依据 | 共同边界 |
|---|---|---|
| 自由实验 | 口述本身的语义缺口 | 先保存，成功后追问 |
| 方案实验 | 方案已知值、现场必测、实际偏差 | 每轮最多一个关键问题 |

自由 Chat 不自动保存同一句实验事实；需要写入时应经过明确意图和后续 Tool 权限层。

专业概念：语义缺口（semantic gap）、方案约束（protocol constraint）、提交后投影
（post-commit projection）、最小必要追问（minimal necessary clarification）。

## 5. 2026-08-25：为什么方案、安全、记录和 Tool 要进入同一聊天时间线

### 5.1 修改前的真实缺口

同一个思考或 Tool 事件会同时进入两套前端内存：

```text
chatPushThink + runPushThink
chatPushTool + runPushTool
```

右侧聊天区和中间运行画布各保存一份状态。这不是一份事实的两个视图，而是双写；容易出现一边更新、
另一边没有更新，刷新后恢复程度不同，也无法明确验收对象。

### 5.2 目标设计

实时交互只保留一条聊天时间线：

```text
ConversationTurnStore
→ user_text
→ assistant_text
→ protocol_card
→ step_card
→ safety_alert
→ record_card
→ tool_card
→ confirmation_card
→ system_status
```

方案库、记录库、安全库等独立页面可以继续用于完整浏览和编辑，但不能再保存第二份实时运行状态。

专业概念：单一事实源（single source of truth）、事件双写（dual write）、消息块（content block）、
聊天优先工作区（chat-first workspace）。

## 6. 2026-08-25：策略分开，输出机制统一

三类结果不应使用同一说话政策：

| 生产者 | 内容策略 | 共同机制 |
|---|---|---|
| Chat | 自然交流、按句语音、不自动保存实验事实 | Turn/Block、Scheduler、TTS反馈 |
| 实验记录 | 保存后短回执、必要追问、失败不伪造成功 | Turn/Block、Scheduler、TTS反馈 |
| Tool | 只呈现真实结果，写入型操作受权限控制 | Turn/Block、Scheduler、TTS反馈 |

白话类比：实验记录员、聊天伙伴和工具操作员可以使用不同台词规则，但都必须使用同一个广播系统。

专业概念：机制与策略分离（mechanism-policy separation）、统一外壳（common envelope）、
多生产者（multiple producers）、单一副作用出口（single side-effect boundary）。

## 7. 第 33 项后续学习路线

| 任务 | 完整能力 | 本轮学习重点 |
|---|---|---|
| 33a | Turn/Block 纯合同 | 不变量、身份、引用完整性、无副作用合同 |
| 33b | 唯一 ConversationTurnStore | 单一事实源、幂等归并、事件顺序 |
| 33c | 单聊天时间线 | 消息块渲染、管理页与运行态边界 |
| 33d | 显式模式切换 | 请求快照、版本冲突、异步竞态 |
| 33e | 三种输出策略 | 策略模式、语音分句、保存后反馈 |
| 33f | 三生产者交叉回归 | 测试矩阵、失败隔离、组合影响 |
| 33g | 真实播放验收 | AUTO_OK、REAL_OK、UX_CONFIRMED 的区别 |

## 8. 后续每项追加模板

```text
## 日期与任务编号

### 用户实际遇到什么

### 修改前真实缺口

### 白话理解

### 专业概念

### 数据流（不超过五个主节点）

### 代码复核路线
- 入口文件/函数：
- 消息字段：
- 经过的函数：
- 状态写入位置：
- 最终副作用：

### 验证
- 命令：
- 实际输出：
- 能证明：
- 不能证明：

### 唯一下一步
```

## 9. 当前停点

- 正式计划已经把第 33 项拆为 33a–33g；
- 第 33 项真实验收已开始但未通过；
- 试验性普通 Chat 语音候选不是最终策略；
- 当前只推进 33a 纯合同，不提前实现 Store、界面、模式、保存、Tool 或 TTS；
- 下一次维护日志的触发点：33a 完成自动验证并形成可复核的字段与不变量。

## 10. 2026-08-25：33a `VOICE-C6-A1-TURN-BLOCK-CONTRACT` 自动闭环

状态：`AUTO_OK`。

### 10.1 用户实际遇到什么

第 33 项真实浏览器验收先暴露了普通 Chat 有 ASR 和文字回复、但没有语音候选的问题；继续复核后又发现，
页面同时保存聊天区和运行画布两份 think/tool 状态，而且输入入口还在隐式决定业务模式。

因此真正需要先解决的不是“再补一条 Chat TTS 分支”，而是给后续单 Composer、单聊天时间线建立共同身份：

```text
这是哪个请求、哪个回合、哪一块可见内容？
提交时是什么模式和版本？
语音究竟对应屏幕上的哪一块？
同一请求重试时是幂等重放还是冲突？
```

### 10.2 修改前真实缺口

已有 `PresentationIntent` 能表达“业务想呈现什么”，`VoiceDeliveryItem / PlaybackRequest` 能表达
“内容是否有语音资格以及何时播放”，但它们没有统一表达：

- `conversation_id → request_id → turn_id → block_id` 可追溯身份；
- 提交时冻结的 `interaction_mode / experiment_context / mode_version / input_source`；
- 用户/助手文字、方案、步骤、安全、记录、Tool、确认和系统状态的统一 Block 外壳；
- VOICE 与可见内容之间可验证的 `source_block_id` 引用；
- 同一请求的完全相同重放、模式版本变化和其他内容变化应怎样区分。

试验性 `ASSISTANT_REPLY` 只定位了普通 Chat 候选缺口，仍复用实验首句/25 字政策；它没有补齐上述合同，
也没有被本项删除或当成最终 Chat 策略。

### 10.3 白话理解

把一次用户输入想成一个有编号的文件袋：

- `request_id` 是前台受理号，用来识别是不是同一次提交重试；
- `turn_id` 是这次完整对话回合号；
- 每张文字或卡片都有自己的 `block_id`；
- 模式、实验上下文、版本和输入来源在交件时盖章，之后切换界面不能改掉旧文件袋的语义；
- 语音不再抄写另一份正文，只写“朗读 block-X”，所以屏幕和声音可以追溯到同一内容。

合同只规定文件袋长什么样、哪些组合非法；它不会替用户保存实验、运行 Tool 或播放声音。

### 10.4 专业概念

- 聚合根（aggregate root）：`ConversationTurn` 负责检查同一回合所有 Block 的整体不变量；
- 值对象（value object）：Turn、Block 和重放判断均不可变，只表达事实和值；
- 请求级快照（request-scoped snapshot）：提交时冻结模式、上下文、版本和输入来源；
- 幂等键（idempotency key）：本合同使用 `(conversation_id, request_id)`；
- 乐观版本冲突（optimistic version conflict）：同一请求键携带不同 `mode_version` 时明确报冲突；
- 引用完整性（referential integrity）：VOICE 只能引用本 Turn 已有的非语音 Block；
- 机制与策略分离：Chat、实验记录、Tool 的内容策略以后分别实现，但都使用 Turn/Block 和统一 Scheduler；
- 纯合同（pure contract）：构造、校验、序列化和比较不产生业务副作用。

### 10.5 数据流（不超过五个主节点）

```text
一次用户提交
→ 冻结 request/turn/模式/版本/输入来源
→ 生成可见内容 Blocks
→ VOICE 通过 source_block_id 关联可见 Block
→ to_wire 输出，供未来 Store/界面/Scheduler 消费
```

本项只完成前四步的数据合同和第五步的纯序列化出口；尚无真实 Store 或生产消费者。

### 10.6 代码复核路线

- 入口文件/函数：
  - `src/core/conversation_turn.py::ConversationBlock`
  - `src/core/conversation_turn.py::ConversationTurn`
  - `src/core/conversation_turn.py::decide_turn_replay`
  - `ConversationBlock.to_wire()` / `ConversationTurn.to_wire()`
- 消息字段：
  - Turn：`conversation_id`、`request_id`、`turn_id`、`interaction_mode`、
    `experiment_context`、`mode_version`、`input_source`、`blocks`；
  - 普通 Block：`block_id`、`type`、`payload`；
  - VOICE Block：另带 `source_block_id`、`intent_id`、`priority`，且 `payload` 必须为空；
  - 可见类型：`user_text`、`assistant_text`、`protocol_card`、`step_card`、`safety_alert`、
    `record_card`、`tool_card`、`confirmation_card`、`system_status`。
- 经过的函数：
  - Block 构造 → `ConversationBlock.__post_init__()` → `_freeze_payload()`；
  - Turn 构造 → `ConversationTurn.__post_init__()` → 身份、模式组合、Block 唯一性与 VOICE 引用校验；
  - 重放比较 → `decide_turn_replay(existing, candidate)`；
  - 线格式 → `ConversationTurn.to_wire()` → `ConversationBlock.to_wire()` → `_to_wire_value()`。
- 状态写入位置：无。合同没有数据库、文件、前端 Store 或会话状态写入者。
- 最终副作用：无。没有保存实验、执行 Tool、调用 PlaybackScheduler 或播放 TTS。

主要不变量：

- Chat 只能配 `experiment_context=none`；Experiment 必须选择 `free` 或 `protocol`；
- `mode_version` 必须是正整数；
- 同一 Turn 的 `block_id` 唯一，同一 Turn 的 VOICE `intent_id` 唯一；
- VOICE 不能跨 Turn、不能引用 VOICE、不能复制可见正文；
- 非 VOICE Block 禁止夹带语音身份字段；
- payload 只接受 JSON 可表示的数据，并在构造时深层复制和冻结；
- 不同幂等键是新请求；相同键且合同完全一致是幂等重放；相同键改变模式版本或内容是冲突。

### 10.7 验证

专项命令：

```powershell
.\.runtime-python311\python.exe -B -m unittest tests.test_conversation_turn -v
```

实际输出：

```text
Ran 14 tests in 0.003s
OK
```

相邻合同命令：

```powershell
.\.runtime-python311\python.exe -B -m unittest `
  tests.test_conversation_turn `
  tests.test_presentation_intent `
  tests.test_presentation_delivery `
  tests.test_playback_request `
  tests.test_c5_architecture_freeze `
  -v
```

实际输出：

```text
Ran 39 tests in 0.011s
OK
```

项目全量命令：

```powershell
.\.runtime-python311\python.exe -B -m unittest discover -s tests -v
```

实际输出：

```text
Ran 1076 tests in 7.795s
OK
```

静态检查：

```powershell
.\.runtime-python311\python.exe -m py_compile `
  src\core\conversation_turn.py `
  tests\test_conversation_turn.py

git diff --check -- `
  src/core/conversation_turn.py `
  tests/test_conversation_turn.py `
  docs/PROJECT_TASK_CHECKLIST.md `
  docs/VOICE_WEB_MIGRATION_PLAN_2026-08-20.md
```

实际结果：`py_compile` 通过；`git diff --check` 通过，只有既存 LF→CRLF 提示，没有空白错误。

### 10.8 能证明

- Turn/Block 能表达三个显式模式组合和三种输入来源，而不把输入来源当成业务模式；
- 九类可见内容和 VOICE 可以放入同一不可变 Turn；
- VOICE 的 `source_block_id` 引用完整性、身份唯一性和 JSON 线格式已由自动测试覆盖；
- 模式版本已冻结在 Turn 中，纯函数能区分完全相同的幂等重放、模式版本冲突和内容冲突；
- 合同模块没有保存、Tool、Store、Scheduler 或 TTS 执行方法；
- 所覆盖的既有呈现和播放合同没有因本项回归失败。

### 10.9 不能证明

- 页面已经只有一个 Composer 或一条聊天时间线；
- 生产请求已经发送 `request_id / mode_version`，或切换模式时真的不会串线；
- Store 已按幂等键去重、拒绝冲突或保证事件顺序；
- Chat 遇到实验事实时不会自动保存；写入型 Tool 已有明确意图和权限控制；
- 自由实验已经执行“先保存原始事实、成功后最多一个关键追问”；
- 方案实验已经按方案已知值、现场必测、偏差和安全追问；
- Chat、实验记录和 Tool 的不同内容策略已经接入共同外壳；
- PlaybackScheduler、TTS、真实浏览器、麦克风、扬声器、耳机或实际 UX 已通过。

这些都属于后续生产接线或真实验收，不能由 `AUTO_OK` 扩大推断。

### 10.10 唯一下一步

33b `VOICE-C6-A2-SINGLE-CONVERSATION-STORE`：实现唯一 `ConversationTurnStore`，让生产事件只写入一份
Turn 状态，并在 Store 边界实际消费 33a 的幂等重放/冲突判断；移除 chat/run 两份 think/tool 双写。

本条目不提前实现单 Composer、界面渲染、模式按钮、Chat/实验内容策略、保存、Tool 权限或 TTS。

## 11. 2026-08-25：33b `VOICE-C6-A2-SINGLE-CONVERSATION-STORE` 自动闭环

状态：`AUTO_OK`。

### 11.1 用户实际遇到什么

同一个 think 或 Tool 事件会同时出现在聊天区和中间运行画布。两边看似展示同一件事，实际上各自保存
一份内存状态；一边更新失败或刷新行为不同，就会出现两个互相矛盾的“现场”。

### 11.2 修改前真实缺口

```text
streaming_chat_v2.js：activeThinkRow / toolRows
run_canvas.js：stream / pendingIndex

同一 think：chatPushThink + runPushThink
同一 Tool：chatPushTool + labToolCard → runPushTool
```

普通助手正文还直接修改 `reply.textContent`，没有先成为 33a 定义的 `assistant_text` Block；Tool 卡片主要
按标题配对，连续两个同名调用可能被错误视为同一调用。

### 11.3 白话理解

以前是两名记录员各抄一本现场账。本项改成只有一本总账：服务端事件先记进
`ConversationTurnStore`，聊天区只负责把总账画出来；运行画布不再抄 think 和 Tool。

“DOM 上已经显示”不等于“事实已经存好”。DOM 节点只是显示结果，Store 中的 Block 才是当前前端事实。

### 11.4 专业概念

- 单一事实源（single source of truth）；
- 事件归约（event reduction）：pending/result 更新同一 Tool Block；
- 发布订阅（publish-subscribe）：Store 发布快照，聊天渲染器订阅；
- 稳定身份（stable identity）：Tool 使用服务端 `tool_call_id`，不优先依赖标题；
- 防御性复制（defensive copy）：对外快照是深拷贝，消费者不能反向修改 Store；
- 内存幂等（in-memory idempotency）：同一请求重放不清空已归约的 Block。

### 11.5 数据流（不超过五个主节点）

```text
Chat 流事件
→ ConversationTurnStore upsert Block
→ Store 发布不可外改的 Turn 快照
→ 聊天时间线订阅并渲染 DOM
→ 运行画布只保留方案/步骤展示
```

### 11.6 代码复核路线

- 入口文件/函数：
  - `web/frontend/conversation_turn_store.js::createConversationTurnStore`
  - `beginTurn / upsertBlock / pushThink / pushTool / subscribe / clear / getSnapshot`
  - `web/frontend/streaming_chat_v2.js::form.onsubmit`
- 消息字段：沿用 33a Turn 身份；用户为 `user_text`，助手正文为 `assistant_text`，think 为
  `system_status` 且 `payload.kind=think`，Tool 为 `tool_card`；服务端 Tool view 新增 `tool_call_id`。
- 经过的函数：
  - 用户提交 → `beginTurn()`；
  - `screen_delta/delta/task_queued` → `publishAnswer()` → `upsertBlock()`；
  - `LABTHINK` → `pushThink()`；`LABCARD` → `pushTool()`；
  - `publish()` → `streaming_chat_v2.js` 的 Store 订阅者 → DOM 渲染。
- 状态写入位置：唯一写入 `conversation_turn_store.js` 内部的 `turn.blocks`。
- 最终副作用：只改变浏览器内存和聊天 DOM；不保存数据库、不执行 Tool、不播放 TTS。

删除路线：

- `run_canvas.js` 不再拥有 `stream/pendingIndex`；
- 删除 `runPushThink/runPushTool/runClearStream`；
- `tool_cards.js` 不再由页面加载；
- `streaming_chat_v2.js` 不再调用 `chatPushThink/runPushThink/chatPushTool/runPushTool/labToolCard`。

### 11.7 验证

专项组合：

```powershell
.\.runtime-python311\python.exe -B -m unittest `
  tests.test_conversation_turn_store_frontend `
  tests.test_frontend_screen_delta `
  tests.test_agent_tool_presentation -v
```

实际输出：

```text
Ran 27 tests in 0.151s
OK
```

Store 行为与相邻 Node 回归：

```powershell
node tests\js\test_conversation_turn_store.js
node tests\js\test_voice_delivery_client.js
node tests\js\test_call_silero_vad.js
node tests\js\test_phone_call_silero_fallback.js
```

实际输出：

```text
conversation_turn_store: OK
voice_delivery_client: OK
call_silero_vad: OK
phone_call_silero_fallback: OK
```

项目全量：

```powershell
.\.runtime-python311\python.exe -B -m unittest discover -s tests -v
```

实际输出：

```text
Ran 1083 tests in 7.947s
OK
```

修改的 3 个 JS 文件 `node --check` 通过，Python `py_compile` 和相关文件 `git diff --check` 通过。

### 11.8 能证明

- 当前活动 Chat 的用户文字、助手正文、think 和 Tool 只写一个前端 Store；
- 聊天 DOM 从 Store 快照读取服务端正文、think 和 Tool；
- 运行画布已无第二份实时 think/tool 数组、索引和推送 API；
- Tool pending/result 携带同一服务端 `tool_call_id` 并更新同一 Block；
- 完全相同请求重放保留 Store 已有 Block，模式版本或请求内容变化被拒绝；
- 所覆盖的屏幕/TTS 边界、Tool 呈现和既有 VAD/播放 Node 行为没有自动回归失败。

### 11.9 不能证明

- 真实浏览器中聊天布局和顺序已经符合用户预期；
- 历史消息、录音记录、方案、安全、确认等全部生产者已经进入 Store；
- 页面刷新后 Store 可以恢复，或多标签页之间能共享幂等状态；
- 服务端已经接收 33a 的完整请求级模式快照；当前文字入口仍临时标记为 chat/text/version 1；
- 页面已经只有一个 Composer；
- Chat/实验/Tool 内容策略、保存权限、PlaybackScheduler 或真实 TTS 已完成。

因此本项是自动软件闭环 `AUTO_OK`，不是 `REAL_OK` 或 `UX_CONFIRMED`。

### 11.10 唯一下一步

33c `VOICE-C6-A3-CHAT-FIRST-SURFACE`：让方案、步骤、安全、记录、确认和系统状态也成为同一聊天时间线的
可见 Block；管理页保留完整浏览/编辑职责，但不恢复第二份实时状态。

## 12. 2026-08-25：33c `VOICE-C6-A3-CHAT-FIRST-SURFACE` 自动闭环

状态：`AUTO_OK`。

### 12.1 用户实际遇到什么

Block 类型很多：方案、步骤、安全、记录、Tool、确认、状态。如果每类都单独写一套 HTML，代码会迅速变成
七套相似组件，改圆角、间距或状态文案时必须改七处；同时旧 run 画布还会继续与聊天区竞争“主界面”。

### 12.2 修改前真实缺口

33b 只有 user/assistant/think/tool 进入聊天 Store；方案、步骤和安全仍由 run 画布绘制，录音结果仍主要进入
`lab_panel`。Store 虽然允许其他 Block 类型，但没有共同渲染规则，也没有生产适配器。

### 12.3 白话理解

不是为每种内容造一种完全不同的盒子，而是先规定一个共同卡片：左上角是什么类别，中间是什么标题，下面有
几行正文和元信息，右边可有状态。不同 Block 只负责把自己的数据填进这些格子；安全卡再把色调改成红色。

### 12.4 专业概念

- 视图模型（View Model）：把业务 payload 翻译成适合显示的结构；
- 适配器（Adapter）：七种 Block 进入同一个卡片接口；
- 开闭原则：新增类型时扩展映射，不复制整个渲染器；
- 机制与策略分离：卡片骨架是机制，标题、色调和正文选择是类型策略；
- Chat-first：实时交互以聊天时间线为主，管理页只负责完整浏览和编辑。

### 12.5 数据流（不超过五个节点）

```text
现有方案/记录事实
→ conversation_context_blocks 转为 Block
→ ConversationTurnStore
→ conversationBlockView 生成统一视图模型
→ 聊天卡片骨架渲染
```

### 12.6 代码复核路线

- 入口：`conversation_block_view.js::conversationBlockView()`；
- 生产适配：`conversation_context_blocks.js::publishProtocolContextBlocks/beginRecordSurface/publishRecordSurface`；
- 渲染：`streaming_chat_v2.js::ensureCardRow()`；
- 字段：共同视图为 `label/title/tone/status/lines/meta`；原 Block payload 不被卡片组件反向修改；
- 状态位置：仍只写 `ConversationTurnStore.turn.blocks`；
- 副作用：只读方案上下文并更新浏览器 Store/DOM，不保存实验、不执行 Tool、不播放 TTS。

### 12.7 验证

```text
专项：Ran 30 tests，OK
Node：conversation_block_view / conversation_turn_store / voice_delivery_client /
      call_silero_vad / phone_call_silero_fallback 均 OK
全量：Ran 1091 tests in 7.934s，OK
JS node --check：通过
```

### 12.8 能证明

- 七类卡片由一个 View Model 适配入口和一个聊天卡片骨架表示；
- 方案、步骤、安全、记录和确认已有生产投影进入 Store；
- run 实时画布不再加载，管理页仍在；
- 所覆盖的 Store、屏幕、语音许可和 VAD 自动回归未失败。

### 12.9 不能证明

- 真实浏览器中的宽度、顺序、折叠、滚动和手机体验合格；
- 显式模式已经上线；当前录音模式仍根据既有方案会话读取，`mode_version=1` 仍是过渡值；
- 所有历史内容刷新后都能恢复；
- Chat/实验/Tool 内容政策、权限和真实 TTS 已完成。

### 12.10 唯一下一步

33d `VOICE-C6-A4-EXPLICIT-MODE-SWITCH`：在唯一 Composer 上显式选择 chat、experiment/free、
experiment/protocol，并把提交时模式与 `mode_version` 快照发送到服务端，避免异步切换串线。

## 13. 2026-08-25：33d `VOICE-C6-A4-EXPLICIT-MODE-SWITCH` 专项自动闭环

状态：`AUTO_OK`（专项与全量自动证据；未做真实浏览器验收）。

### 13.1 用户实际遇到什么

页面虽然只有一个输入框，但文字 Chat、单次录音和连续通话在背后各自猜模式：文字被写死成 Chat，录音又根据是否
加载方案暗中决定实验上下文。用户发送后再切模式时，没有一张“当时选了什么”的提交凭证。

### 13.2 修改前真实缺口

`streaming_chat_v2.js` 写死 `chat/none/version 1/text`；`conversation_context_blocks.js` 请求当前方案会话后推断
free/protocol；`phone_call.js` 调用 Composer 时没有声明连续通话来源；Chat/Record 请求模型也不接收模式快照。

### 13.3 白话理解

把模式想成相机档位。按快门前可以切换，但按下快门的一刻，要把“什么档位、档位第几版、用文字还是录音”抄到这张
照片的票据上。之后再转动旋钮，只影响下一张照片，不能修改已经拍下的那张。

### 13.4 专业概念

- 单一事实源：`interactionModeState` 是页面唯一当前模式；
- 不可变快照：提交对象冻结，异步切换不能反向修改；
- 乐观版本：模式实际变化时 `mode_version + 1`，重复点击同档不增版；
- 正交维度：业务模式与输入来源分开组合；
- 边界校验：服务端拒绝 chat+free/protocol、experiment+none 和非正版本。

### 13.5 数据流（不超过五个节点）

```text
Composer 选择三种模式
→ interactionModeState 更新版本
→ 提交时加入 input_source 并冻结快照
→ 同一快照写 Turn Store 和 HTTP 请求
→ 服务端 ModeSnapshotFields 校验
```

### 13.6 代码复核路线

- 入口：`interaction_mode_state.js::createInteractionModeState/select/capture`；
- UI/提交：`composer.js::send()`；连续通话入口为 `phone_call.js::composerSend(...continuous_call)`；
- 字段：`interaction_mode / experiment_context / mode_version / input_source`；
- 服务端：`mode_snapshot.py::ModeSnapshotFields.validate_mode_context()`，由 `ChatRequest/RecordPayload` 继承；
- 最终状态：当前选择只在 `interactionModeState`；提交快照分别进入当前 `ConversationTurnStore.turn` 和请求 JSON；
- 本项没有保存实验、执行 Tool、改变内容策略、生成/播放 TTS。

### 13.7 实际测试输出

```text
Python 专项组合：Ran 22 tests，OK
项目全量：Ran 1098 tests in 7.662s，OK
Node：interaction_mode_state / conversation_turn_store / conversation_block_view 均 OK
相关 JS node --check：通过
Python py_compile：通过
git diff --check：通过
```

### 13.8 能证明

- 三种模式有唯一显式选择和单调版本；
- 三种输入来源不会自行决定模式；
- 提交后切换不会修改旧快照；
- Store 与对应 HTTP 请求使用同一份冻结语义；
- 服务端能拒绝非法模式组合。

### 13.9 不能证明

- 真实浏览器按钮布局、窄屏换行、键盘与录音交互体验合格；
- Chat 模式录音已经不保存，或实验模式文字已经默认保存；这些属于 33e 路由/内容策略；
- Tool 权限、确认、输出策略、PlaybackScheduler 或真实 TTS 已完成；
- 全量自动通过不代表真实浏览器中三个入口的操作与异步时序通过。

### 13.10 唯一下一步

33e `VOICE-C6-A5-MODE-OUTPUT-POLICIES`：让自由 Chat 不自动保存；自由实验先保存原始事实、成功后最多追问一个关键
语义缺口；方案实验按方案已知值、现场必测、偏差和安全追问；Tool 只呈现真实结果。

## 14. 2026-08-25：33e `VOICE-C6-A5-MODE-OUTPUT-POLICIES` 自动闭环

状态：`AUTO_OK`，未做真实浏览器验收。

### 14.1 用户现象与修改前缺口

33d 已能给请求贴上正确模式标签，但系统还没照标签办事：Chat 录音仍直达 `/record`；实验文字仍进入 Chat；旧 Agent
提示词看到实验事实就强制调用记录 Tool。也就是说，“标签正确”不等于“行为正确”。

### 14.2 白话理解

模式像快递面单，策略像分拣传送带。33d 只把“普通包裹、冷链、危险品”写对；33e 才让普通包裹走普通线、自由实验走
原始事实保存线、方案实验走带方案核对的保存线。录音只是包裹从哪个窗口交进来，不能决定传送带。

### 14.3 专业概念

- Strategy Pattern：共同输出机制下选择不同业务策略；
- Defense in Depth：Chat 同时从模型工具列表隐藏记录 Tool，并在执行入口硬拒绝；
- Post-commit Projection：保存成功后才生成“已记录”或追问；
- Mode Conflict：方案模式没有有效方案时在副作用前失败；
- Orthogonality：`input_source` 与业务模式正交。

### 14.4 数据流（不超过五个节点）

```text
冻结的模式快照
→ select_output_policy
→ Chat Agent 或 SharedRecordService
→ 保存成功/真实 Tool outcome
→ 同一 Turn/Block 时间线
```

### 14.5 入口、字段、函数和状态位置

- 纯入口：`output_policy.py::select_output_policy()`；
- 前端分流：`streaming_chat_v2.js` 与 `voice_asr.js::streamExperimentRecord()`；
- Chat：`api/chat.py::_require_chat_policy()` → `agent/core.py::_tools_for_mode/_run_tool_with_presentation`；
- Record：`api/record.py::record/record_stream` → `SharedRecordService.record()`；
- 字段：沿用 `interaction_mode / experiment_context / mode_version / input_source`；
- 最终业务状态：实验原始事实仍只由 `save_record()` 写入；Chat 不写实验记录；显示状态仍进入当前 Turn 的 Blocks。

### 14.6 三种策略

```text
Chat：自然回答；不套记录短回执；不自动保存；记录 Tool 隐藏+硬阻断
experiment/free：忽略已加载方案；保存原始事实；保存后最多一个关键语义追问
experiment/protocol：要求有效方案；按方案已知值、现场必测、偏差和安全判断；保存后呈现
Tool：只把真实执行 outcome 转成 Tool Card/DeliveryPlan
```

### 14.7 实际测试输出

```text
专项：Ran 46 tests，OK
全量：Ran 1105 tests in 7.883s，OK
Node：interaction_mode_state / conversation_turn_store / conversation_block_view /
      voice_delivery_client / call_silero_vad / phone_call_silero_fallback 均 OK
JS node --check：通过
git diff --check：通过
```

### 14.8 能证明

- Chat 文字、单次录音、连续通话不会仅因实验事实自动进入记录服务；
- 显式 Chat 直接请求 `/record` 也在服务构造前被拒绝；
- 自由实验和方案实验使用不同评估权威；
- 方案上下文冲突在抽取与保存前失败；
- 保存成功后才生成成功回执/至多一个追问；
- 所覆盖的旧 Tool、播放和 VAD 自动回归未失败。

### 14.9 不能证明

- 真实浏览器三个模式按钮、文字、单次录音和连续通话操作体验合格；
- 真实数据库在人工切换模式时绝无错写；
- Chat 最终按句语音策略已经替换试验性 25 字语音候选；
- 写入型 Tool 的明确意图、权限确认和执行授权已经完成；该层仍属于后续第 39 项；
- 真实 TTS、外放、耳机或设备时序通过。

### 14.10 唯一下一步

33f `VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX`：把 Chat、Record、Tool 放进同一交叉矩阵，覆盖屏幕、语音开关、
讲话延后、过期、失败、幂等、模式切换和会话隔离，确认三种生产者共用外壳但不互相串策略。

## 15. 2026-08-25：33f `VOICE-C6-A6-THREE-PRODUCER-AUTO-MATRIX` 自动闭环

状态：`AUTO_OK`，未做真实浏览器或设备验收。

### 15.1 先总结前一项

33e 已让模式决定业务策略：Chat 不保存，自由实验保存后最多一个语义追问，方案实验按有效方案评估。33f 不再新增
第四种策略，而是检查 Chat、Record、Tool 共用 Turn/Block 和 PlaybackScheduler 后，会不会在组合状态下串线。

### 15.2 用户现象与修改前缺口

已有测试分别证明 Store、记录、Tool 和 Scheduler，但没有证明一条语音究竟对应屏幕哪张 Block。33a 虽规定 Voice 用
`source_block_id` 引用可见内容，生产 `voice_delivery` 仍没有该字段。因此“屏幕有字”和“调度有声音”可能只是两件碰巧
同时发生的事。

### 15.3 白话理解

Chat、Record、Tool 像三家餐厅，共用一个外卖平台。订单号 `intent_id` 说明是哪一单；`source_block_id` 说明这一单对应
页面上的哪张小票。骑手延迟、恢复或取消时，两张身份标签都不能丢；否则可能把 A 桌的播报送到 B 桌。

### 15.4 专业概念

- Cross-product Matrix：跨生产者与运行状态做笛卡尔组合验证；
- Referential Integrity：语音的 `source_block_id` 必须引用当前 Turn 的真实 Block；
- Causal Trace：屏幕事实、语音候选和调度结果可沿同一身份追踪；
- Session Isolation：每个 conversation 拥有独立 Coordinator、Scheduler 和延后队列；
- Contract Preservation：DEFERRED、重新评估和 DROP 不改变内容身份。

### 15.5 数据流（不超过五个节点）

```text
Chat / Record / Tool 可见 Block
→ VoiceDeliveryItem(source_block_id)
→ PlaybackRequest
→ ConversationPlaybackRegistry / Scheduler
→ 浏览器校验 Block 后播放或拒绝
```

### 15.6 入口、字段、函数和状态位置

- 内容合同：`presentation_delivery.py::VoiceDeliveryItem/build_delivery_plan/bind_voice_items`；
- 调度合同：`playback_request.py::PlaybackRequest.from_delivery_item()`；
- Chat/Tool 绑定：`api/chat.py::chat_stream()`，绑定 `${turn_id}:assistant`；
- Record 绑定：`api/record.py::_record_response()`，追问绑定 `${turn_id}:confirmation:${intent_id}`；
- 浏览器闸门：`voice_delivery_client.js::validItems()`；
- 字段：新增实际生产接线 `request_id / turn_id / source_block_id`，保留 `intent_id / priority`；
- 状态：Block 仍只在 `ConversationTurnStore`；延后项仍只在 conversation 专属 Scheduler 队列。

### 15.7 矩阵覆盖

```text
生产者：Chat / Record / Tool
调度：READY / user speaking DEFERRED / idle reevaluate READY / expired DROP
隔离：conversation A busy 不影响 conversation B
前端：三种 source Block 存在才播放；孤儿 source 拒绝
幂等：相同 request 重放保留 Blocks；mode_version 改变报冲突
```

### 15.8 实际测试输出

```text
专项组合：Ran 54 tests，OK
全量：Ran 1110 tests in 7.818s，OK
Node：three_producer_matrix / interaction_mode_state / conversation_turn_store /
      conversation_block_view / voice_delivery_client / call_silero_vad /
      phone_call_silero_fallback 均 OK
JS/Python 语法：通过
git diff --check：通过
```

### 15.9 能证明与不能证明

能证明：三生产者的语音身份经过调度不丢；同会话忙时均延后，B 会话不受 A 影响；过期不补播；浏览器拒绝不存在
的 Block；自动环境中的幂等和模式冲突成立。

不能证明：真实浏览器事件时序、页面滚动、真实扬声器/耳机播放、用户讲话时是否真的不抢话、恢复后的听感、真实 TTS
耗时与失败；Chat 试验性 25 字语音内容策略仍不是最终按句策略。

### 15.10 下一步如何设计

33g `VOICE-C3-1-PLAYBACK-TIMING-REAL` 不再继续堆自动测试，而要设计真实验收表。分别用 Chat、自由/方案 Record、Tool
制造语音候选；每类在外放和耳机下验证：用户讲话时不播放、停说后仍有效才恢复、超过 TTL 不补播，并同时留浏览器
事件、服务端日志和人耳结果。只有三类都取得真实证据，才标 `REAL_OK`。

## 16. 2026-08-25：33c-UX 单主视图纠偏

状态：`AUTO_OK / UX_PENDING`，尚未做真实浏览器体验确认。

### 16.1 先总结前一项

33a–33f 已经把 Chat、Record、Tool 收敛到统一 Turn/Block 与播放身份，但“数据只有一份”不等于“页面只显示一处”。本轮补齐视觉外壳：不让旧管理画布与新聊天时间线永久并排。

### 16.2 用户现象与修改前缺口

用户看到主聊天旁边仍有实验方案和安全内容，直觉上仍是两套工作区。现场确认 `shell.js` 固定创建 `sh-center` 与 `sh-chat` 两列，默认 `show('protocols')`；33c 仅移除了 run 画布实时状态，没有改变这个默认双栏路由。

### 16.3 白话理解

以前像桌面上同时摊着“聊天本”和“实验管理本”，用户不知道该看哪本。现在桌面一次只摊开一本：默认是聊天本；点方案库或安全库时临时换成管理本，点“主对话”再回来。实验信息仍能作为卡片写进聊天本，但不再另开一块实时屏幕。

### 16.4 专业概念

- Single Primary Surface：任一时刻只有一个主要内容区域；
- Mutually Exclusive View Routing：聊天与管理页通过路由互斥显示；
- State/View Separation：模式和 Turn Store 决定内容，外壳只决定当前看哪个视图；
- Progressive Disclosure：完整方案与安全库按需打开，关键上下文以 Block 进入时间线。

### 16.5 数据流（不超过五个节点）

```text
用户选择 chat / experiment 模式
→ 冻结模式快照
→ 业务策略生成对应 Blocks
→ 唯一 ConversationTurnStore
→ 唯一聊天时间线渲染
```

### 16.6 入口、字段、函数和状态位置

- 页面入口：`web/frontend/shell.js::init()`；
- 视图入口：`shell.js::show(view)`，默认 `show('chat')`；
- 显示状态：`#shell.chat-view` 互斥控制 `#sh-chat / #sh-center`；
- 内容状态：仍只在 `window.conversationTurnStore`，本轮没有新增第二 Store；
- 字段：本轮不新增消息字段，继续使用 `interaction_mode / experiment_context / mode_version` 与 Block `type`；
- 管理页：`protocols / reagents / records / settings` 保留，只在主动导航时整页显示。

### 16.7 实际测试输出

```text
针对性组合：Ran 27 tests，OK
Node --check web/frontend/shell.js：通过
git diff --check（本轮两份代码/测试文件）：通过
```

### 16.8 能证明与不能证明

能证明：源码默认进入 Chat；聊天与管理画布在 CSS/路由合同上互斥；管理入口仍存在；模式、输出策略和三生产者身份的 27 项覆盖未回归。

不能证明：真实浏览器缓存已刷新；桌面窗口实际只出现一个主区域；聊天滚动、管理页往返和 Store 状态保留体验合格；真实声音、外放、耳机或播放时序通过。

### 16.9 唯一下一步

真实浏览器按 `Ctrl+F5` 后复验：默认只见主聊天；分别进入实验方案和试剂安全库时聊天被整页替换；点击主对话后原聊天仍在且没有第二份方案/安全实时区域。通过后再进入 33g，不在本轮提前验 TTS 时序。

## 17. 2026-08-25：33g 前置语音输入输出恢复

状态：软件与真实服务探针通过，真实麦克风/浏览器播放仍为 `REAL_PENDING`。

### 17.1 先总结与用户现象

单主视图已经建立，但用户实际操作发现 ASR 加载失败、语音内容不进入聊天、普通回复没有合成。打字仍有回复，说明模型聊天段正常，故障位于语音输入和播放授权两端。

### 17.2 修改前缺口与白话理解

第一处像录音员上班前必须确认 ffmpeg 工具，但当前启动环境不准他打开工具，所以一句话也抄不出来；没有文字就不可能送进聊天。第二处像播音稿已经写好，却被贴成“低价值静默通知”，调度员按规则直接销毁。TTS 工厂本身并未持续损坏。

### 17.3 专业概念

- Process Capability：运行进程是否有创建依赖子进程的能力；
- Pipeline Failure Isolation：按 ASR、提交、LLM、授权、TTS 分段定位；
- Priority Classification：内容类别必须映射到正确调度优先级；
- Real Service Probe：真实调用 ASR/TTS，但仍区别于浏览器与人耳端到端验收。

### 17.4 数据流（不超过五节点）

```text
麦克风音频 → SenseVoice 文本 → 唯一 Composer/Chat Turn
→ ASSISTANT_REPLY(REVIEW) / PlaybackScheduler READY
→ 火山 TTS 与浏览器播放
```

### 17.5 入口、字段、函数与状态

- ASR：`web/api/asr.py::warmup/transcribe` → `SenseVoiceBackend.__init__/recognize`；
- Chat：`web/api/chat.py::chat_stream` 创建 `ASSISTANT_REPLY`；
- 字段：`priority` 从错误的 `ROUTINE` 改为 `REVIEW`，`source_block_id` 仍绑定助手 Block；
- 调度：`ConversationPlaybackRegistry.authorize()` → `PlaybackScheduler.schedule()`；
- 最终状态：ASR 后端保存在 `web.api.asr._backend`；聊天 Block 仍只在 ConversationTurnStore；TTS 音频不落业务库。

### 17.6 实际测试输出

```text
ASR warmup：loaded=true，error=null
固定真实 WAV：你好，我是你的实验助手，我们可以开始工作了吗？
真实 Chat SSE：READY / REVIEW / playback_window_open
火山 TTS：首次一次 SSL EOF；随后 3/3 为 HTTP 200、17,760 bytes
专项：Ran 38 tests，OK
全量：Ran 1111 tests in 7.934s，OK
```

### 17.7 能证明与不能证明

能证明：当前服务能加载 SenseVoice 并转写固定真实音频；普通 Chat 的语音候选可以通过 Scheduler；火山服务当前能返回 MP3；自动回归未发现相关软件退化。

不能证明：用户真实麦克风权限、录音质量与分段正确；识别文字一定进入当前可见聊天；浏览器一定成功解码并从扬声器播放；代理不会再次 TLS 抖动；外放/耳机不抢话和打断时序合格。

### 17.8 唯一下一步

用户在刷新后的真实页面做一次完整测试：点单次录音，说“请用一句话解释为什么实验要设置对照组”，确认识别文字进入唯一聊天、出现模型回复并实际听到声音。只观察这一条链，通过后再扩展到外放/耳机时序矩阵。

## 18. 2026-08-25：隐藏静音状态的最后一公里修复

用户再次报告无声。现场日志显示 `/asr/transcribe 200` 和 `/chat/stream 200`，却完全没有 `/tts`，因此 ASR、聊天和服务端 READY 之外的浏览器消费层才是缺口。单主视图 CSS 隐藏了头像，而头像原本是 `tts-muted` 的唯一控制入口；历史静音值仍生效，用户却看不到也无法切换。

白话说，音响和音频文件都正常，但遥控器被收进柜子，且上次的“静音”还被记住。专业上这是 Persisted UI State 与 Control Visibility 不一致。修复后聊天头部直接显示“语音开启/关闭”，写回同一个 `tts-muted`，并把 PLAYED、PLAYBACK_DISABLED、REJECTED_PAYLOAD、TTS_UNAVAILABLE 作为可观察事件反馈，不删除来源 Block 完整性闸门。

数据流：`voice_delivery READY → source Block 校验 → 可见语音开关 → enqueueSpeech → /tts`。入口为 `voice_delivery_client.js::consumeVoiceDelivery/outcome` 与 `shell.js::syncTtsButton`；最终静音状态仍是 `window.ttsMuted + localStorage['tts-muted']`，没有新增平行状态。

实际验证：首次旧断言因“拒绝不再静默”出现 1 个预期失败，更新为不得调用 TTS但必须报告原因；随后 Node `voice_delivery_client: OK`，相关组合 `50/50`、JS 语法与 `git diff --check` 通过。服务重启 PID 29900，首页确认新缓存脚本、聊天头部按钮存在，ASR `loaded=true`。

能证明：浏览器现在有唯一可见静音控制，且各拒绝原因可观察。不能证明：当前真实页面已经刷新、用户系统音量正常、浏览器 Audio 解码和扬声器实际出声。唯一下一步：用户 `Ctrl+F5`，确认头部为“语音开启”，再发一条语音；若仍无声，根据按钮反馈和新日志继续定位浏览器播放本身。

## 19. 2026-08-25：自由实验双投影移除

用户截图显示“加入缓冲液”同时出现在聊天 Block 和右侧实验方案面板。白话上是一张记录被两个显示器播放；专业上是同一 `record_result` 被 `publishRecordSurface()` 与遗留 `labRender()` 两个 Projection Consumer 消费。`/record/history` 证明 `segment_id=71` 只有一条，未发生双写。

本轮停止在桌面首页加载 `lab_panel.js`，并从 `voice_asr.js` 删除 `labRender()`；唯一数据流变为 `record_result → publishRecordSurface → ConversationTurnStore → 聊天时间线`。完整方案、安全和记录管理仍通过 shell 的 `protocols/reagents/records` 页面访问，不删除业务数据和服务端评估。

实际验证：相关回归 `43/43`、JS 语法与 `git diff --check` 通过；服务重启为 PID 25484，首页现场检查 `loads_legacy_lab_panel=false`、`loads_record_surface=true`，ASR `loaded=true/error=null`。能证明旧双投影入口已从当前首页删除；不能证明用户浏览器已刷新或下一次真实自由实验的卡片顺序和语音体验合格。唯一下一步是 `Ctrl+F5` 后再录一条自由实验，确认只出现左侧一组 Block 且语音仍播放。

## 20. 2026-08-25：方案模式与具体方案建立一致性

### 20.1 用户现象与修改前缺口

用户点击“方案实验记录”，时间线却显示“自由实验”。现场 `/protocols/session` 返回 `mode=free, protocol=null`。原 Composer 只把浏览器 `interactionModeState` 切成 protocol，并没有选择服务端的具体方案，所以“想用方案”和“实际用哪个方案”互相矛盾。

### 20.2 白话理解

“方案实验记录”像告诉助手“我要按菜谱做菜”，但还没有选是哪一本菜谱。旧界面先亮起“按菜谱”按钮，真正做记录时后台只能说“没有菜谱，按自由记录处理”。正确流程是先让用户选具体方案，选择成功后才正式进入方案模式。

### 20.3 专业概念

- State Consistency：浏览器交互模式与服务端活动方案必须表达同一个事实；
- Guard Condition：进入方案模式前必须满足“存在有效活动方案”；
- Commit-after-success：只有服务端 POST 方案成功后，前端才提交模式切换；
- Explicit Selection：不能擅自替用户选择第一个方案。

### 20.4 数据流（不超过五节点）

```text
点击方案实验记录 → 查询活动方案 → 无方案则打开选择页
→ 用户选择具体方案并保存成功 → 切为 protocol 并回到唯一聊天时间线
```

### 20.5 入口、字段、函数和状态位置

- 模式入口：`web/frontend/composer.js::selectComposerMode(mode)`；
- 方案入口：`web/frontend/views.js` 中 `.p-card.onclick`；
- 消息字段：POST `/protocols/session` 的 `protocol_id`；模式仍为 `interaction_mode=experiment / experiment_context=protocol / mode_version`；
- 服务端经过：`GET/POST /protocols/session`，本轮不改变服务端记录、Tool 或 TTS；
- 最终状态：活动方案保存在既有服务端 session；浏览器模式保存在唯一 `window.interactionModeState`；选择成功后 `shellShow('chat')` 返回主时间线。

### 20.6 实际测试输出

```text
node --check composer.js / views.js：通过
针对性与相邻回归：Ran 29 tests，OK
git diff --check（本轮代码与测试）：通过
```

### 20.7 能证明与不能证明

能证明：没有活动方案时源码不会提前切成 protocol；选择具体方案成功后会同步模式并回聊天；自由卡会同步 free；相邻模式、单主视图和三生产者测试未回归。

不能证明：真实浏览器缓存已刷新；用户点击方案卡后实际自动返回；下一条真实录音一定显示所选方案、步骤和安全 Block；ASR、TTS 与 VAD 本轮没有重新验收。

### 20.8 唯一下一步

真实浏览器按 `Ctrl+F5`，点击“方案实验记录”，选择一个具体方案，确认自动回主聊天且按钮保持“方案实验记录”；再录一句实验事实，确认出现所选方案/步骤而不是“自由实验记录”。

## 21. 2026-08-25：Chat 语音输出合同讨论定稿（尚未实现）

状态：`DESIGN_DECIDED / NOT_CODED`。本节只固化用户已决定的 Chat 行为，不代表当前 25 字实现已经修改，也不提前决定 Free 或 Protocol 的语音策略。

### 21.1 默认 Chat 回复

- 屏幕文字与语音必须严格一致；具有 voice 资格的文字必须单独成为可见 Block。
- `voice_text` 必须逐字等于其 `source_block_id` 所指可见 Block 的正文；TTS 层不得另行摘要、截断、清洗或添加“小科”等称呼。
- 默认 Chat 回答在生成阶段按中文语速估算最长约 10 秒；这是生成目标，不允许显示完整长文后只朗读开头，也不允许播放到 10 秒时硬切。
- 可继续使用 `assistant_text`，以 payload role 区分可朗读正文和不自动朗读的补充内容；具体字段名进入代码前再冻结。

### 21.2 单回合“继续说”

- 用户明确说“继续说”时，建立新的用户 Turn 和新的详细回答 Block。
- 该次回复使用单回合 continuation 状态，并以 `continuation_of_turn_id` 追溯上一回合；不把它变成后续所有回答的永久详细偏好。
- continuation 不受默认 10 秒目标强制限制，但每个实际朗读片段仍必须对应独立可见 Block，保持逐字一致。

### 21.3 打断与指定重读

- 用户开口时先暂停当前语音，本阶段不自动恢复旧音频。
- 用户明确指定“重读上一段/某一段”时，从目标可见 Block 读取原文字并重新合成音频；不重新调用模型改写答案。
- 当前 33a 合同限制 voice 引用同 Turn Block；实施重读时需在“允许同 conversation 跨 Turn 引用历史 Block”与“当前 Turn 建立带 `copied_from_block_id` 的重读 Block”之间再冻结一种，不在本次讨论中偷偷决定。

### 21.4 VAD/ASR 误触反馈保护

- 误触不等于有效用户输入，也不能被实验模式保存成事实。
- 连续第 1、2 次误触：创建可见反馈 Block，并完整朗读同一正文。
- 连续第 3 次及以后：继续更新可见状态，但不再生成 voice item；麦克风、VAD、ASR 和连续监听保持开启。
- 有效输入定义为通过基础检查并正式建立 `user_text` Block；有效输入后计数清零并解除语音反馈抑制。`uncertain` 路由只要文字有效也算有效输入。
- 音频过短、ASR 空白/失败、上传失败和 VAD misfire 不算有效输入。
- 误触暂停的旧回答不自动恢复；用户之后仍可通过指定重读，从屏幕 Block 重新合成。

### 21.5 当前明确未决定

- Free 与 Protocol 模式中 `record_card / confirmation_card / protocol_card / step_card / safety_alert / tool_card / system_status` 的逐项语音资格与时长规则；
- 10 秒估算对应的最终中文字数；
- 重读采用跨 Turn 历史引用还是当前 Turn 复制 Block；
- “以后详细点”是否成为持久用户偏好；
- 前端具体样式、展开按钮和播放高亮。

### 21.6 证据边界与下一步

本节只能证明设计决定已写入项目，不能证明代码、自动测试或真实浏览器已经满足。当前生产代码仍存在 `MAX_ITEM_CHARS = 25` 和只取第一句的旧限制。唯一下一步由用户后续指定；在此之前不实施 Chat 合同，也不讨论结果冒充完成。

## 22. 2026-08-25：Free / Protocol Experiment 语音输出合同定稿（尚未实现）

状态：`DESIGN_DECIDED / NOT_CODED`。本节固化两种 Experiment 的目标合同；不代表当前前端 Block 生命周期、15 秒预算、危险动作判断或语音策略已经实现。

### 22.1 两种 Experiment 的共同合同

- 一次有效用户输入只建立一个可追溯 Turn；`user_text` 显示用户原话，但不自动回读。
- 任何实际进入 TTS 的正文必须单独成为可见 Block；`voice_text` 必须逐字等于 `source_block_id` 所指 Block 的可见正文。TTS 层不得另行摘要、清洗、加称呼或截断。
- 一个完整 Experiment Turn 的全部自动语音合计，以中文语速估算最长约 15 秒。预算发生在 Block 形成前，不在播放中硬切。
- 同一 Turn 可以有多个业务 Block，但最多只产生一个独立、可见的语音汇总 Block；TTS 只朗读该 Block，逐字一致。若预计超预算，必须在该 Block 形成前把正文压缩为语义完整的短文本，而不是显示后少读。
- `record_card` 只在事实保存成功后显示，默认不朗读；保存失败不得产生成功 Block 或成功语音，只能产生与真实失败一致的可见状态。
- 现有通用 `safety_alert` 是方案/试剂安全资料，显示但不自动朗读。当前没有“明确危险动作判断”或 `danger_intervention` 能力；未来若实现，必须另立有证据的判断合同，不能仅凭试剂名称推断危险。
- 连续语音误触沿用已决定规则：连续第 1、2 次显示并朗读输入失败反馈，第 3 次起只更新屏幕状态；有效 `user_text` Block 建立后清零并解除抑制。误触不得保存事实、推进步骤或触发偏差判断。

### 22.2 `experiment/free` 合同

- 用户口述默认作为实验记录事实，而不是普通 Chat 自动讨论；必须先保留原始事实并完成保存。
- 保存成功后生成 `record_card`，只显示、不朗读。
- 保存成功后若存在关键语义缺口，最多生成一个必要追问 `confirmation_card`；该 Block 显示并完整朗读同一正文。
- 没有必要追问时，本轮允许只有静默的保存结果，不强行为了“有声音”生成多余回复。
- Free 不加载方案约束，不生成 `protocol_card / step_card`，也不因后台残留活动方案而改用 Protocol 规则。
- 本轮若有关键追问或必要解释，业务结果仍分别显示；同时把本轮确需说出的内容组织成至多一个可见语音汇总 Block，合计约 15 秒。没有需朗读内容时不强行创建该 Block。

### 22.3 `experiment/protocol` 合同

- 进入 Protocol 前必须存在用户明确选择且服务端确认的活动方案；无活动方案不得假装进入，应先回到方案选择。
- `protocol_card` 只在首次进入方案、切换方案或方案版本实际变化时显示一次；不得因每条口述建立新 Turn 而重复投影。
- `step_card` 只在首次进入当前步骤、切换步骤或步骤版本实际变化时显示一次；不得在同一步的连续记录中重复出现。
- 方案/步骤边界若有需要播报的新信息，与同一 Turn 的偏差、必测缺口和确认要求一起组织进唯一可见语音汇总 Block；完整管理详情仍留在各业务 Block、非 voice 元数据或管理页。
- 用户现场事实保存成功后生成静默 `record_card`。
- 方案已知值、现场必测项、偏差或安全条件造成的真实缺口，用一个或多个本轮新 `confirmation_card` 分别表达和维护状态；它们本身不分别进入 TTS，需说出的内容由本轮唯一语音汇总 Block统一表达。
- 未变化的 `protocol_card / step_card`、既有安全资料和历史追问不重复朗读；只有本轮新产生或状态真正变化的 Block 才进入本轮语音候选。
- 本轮确有额外解释时可作为业务 `assistant_text` 显示；需要朗读的部分也必须并入唯一语音汇总 Block，不能再创建第二条自动语音。

### 22.4 Block 生命周期不变量

```text
相同 conversation_id + protocol_id + protocol_version
→ 只产生一次进入方案的 protocol_card

相同 conversation_id + protocol_id + step_number + step_version
→ 只在进入该步骤边界时产生一次 step_card

每次有效实验输入
→ 新 user_text
→ 保存成功后新 record_card（静默）
→ 仅为本轮新缺口/变化产生 confirmation 或 assistant Block
```

### 22.5 当前实现缺口与证据边界

- 当前 `conversation_context_blocks.js::publishProtocolContextBlocks(turnId)` 仍以当前 `turnId` 创建 protocol/step Block，因此会随每个记录 Turn 重复；目标生命周期尚未编码。
- 当前语音层仍有首句/25 字限制，尚未实现 Experiment Turn 总计约 15 秒与逐字一致。
- 当前合同尚未冻结唯一语音汇总 Block 的最终类型名；可复用 `assistant_text` 并使用明确 role，也可在实现纯合同时再冻结专用类型，但不得因此改变“一 Turn 最多一个”的产品规则。
- 当前只有通用 `safety_alert` 资料投影，没有明确危险操作识别、即时干预或相应特殊优先级。
- 本节只能证明设计已记录，不能证明静态检查、自动测试、浏览器、真实麦克风、ASR、TTS或实验保存已经符合。

### 22.6 唯一下一步

等待用户决定何时实施。实施时应先做纯 `interaction_mode + block_type + block lifecycle → VoicePolicy` 合同及测试，不先接真实 TTS，并把当前 protocol/step 每 Turn 重复投影作为同一完整能力的生命周期缺口修正。

## 23. 2026-08-25：统一可见语音 Block 纯合同（AUTO_OK，未接生产）

### 23.1 本轮范围与修改前缺口

本轮只把已决定的 Chat/Experiment 语音正文、估算时长和唯一来源写成纯软件合同。修改前生产语音仍通过 `voice_delivery.py` 取第一句并最多保留 25 字，无法表达 Chat 约 10 秒、Experiment 整 Turn 约 15 秒、continuation 不受默认 Chat 预算，以及“一 Turn 最多一个可见语音汇总 Block”。

### 23.2 白话理解与专业概念

白话上，屏幕和喇叭不再各拿一份稿子：先建立一张用户看得见的朗读稿，喇叭只能照着这张稿子读。专业上这是 Single Source of Truth、Reference Integrity、Deterministic Policy 与 Fail-before-publication；超长时拒绝建立 Block，让上游重写，而不是发布后截断。

### 23.3 数据流（不超过五节点）

```text
冻结的 mode/context/reply_scope
→ select_spoken_output_policy
→ 上游提供完整可朗读正文
→ build_spoken_block_plan
→ 可见 assistant_text(role=spoken) + 引用它的 VOICE
```

### 23.4 入口、字段、函数和状态位置

- 新入口：`src/core/spoken_output.py::select_spoken_output_policy()`；
- 构造入口：`build_spoken_block_plan()`；
- Chat 默认：`estimated_max_chars=50`，按 5 字/秒估算约 10 秒；
- Chat continuation：`estimated_max_chars=None`，只表示不受默认 10 秒合同，不代表无限 TTS 已接通；
- Free/Protocol：`estimated_max_chars=75`，表示整个 Experiment Turn 唯一自动语音约 15 秒；
- 可见来源：`assistant_text` payload `role=spoken / text`；
- 语音身份：既有 `VOICE.source_block_id / intent_id / priority`，VOICE payload 仍为空；
- 唯一正文：`SpokenBlockPlan.voice_text` 直接读取来源 Block 的 `payload.text`，不保存第二份副本；
- 最终状态：本轮无 Store、数据库、Scheduler、TTS、前端或运行时状态改变。

### 23.5 实际测试输出

```text
新增专项：6/6 OK
专项与相邻合同：Ran 30 tests，OK
项目全量：Ran 1119 tests in 7.873s，OK
Python compile：通过
git diff --check：通过
```

### 23.6 能证明与不能证明

能证明：三种模式组合选择正确预算；Chat continuation 不套默认上限；Experiment policy 明确最多一个 voice Block；可见正文是唯一语音文字源；超预算明确失败且不截断；构造结果满足既有同 Turn VOICE 引用合同；全量自动回归通过。

不能证明：模型会按预算生成自然回答；生产 Chat/Record 已调用新合同；浏览器会显示 `role=spoken`；现有首句/25 字限制已删除；真实 TTS 时长接近估算；Protocol/Step 生命周期已修；真实麦克风、VAD、播放、打断或重读通过。

### 23.7 前端影响说明

本轮没有修改任何前端文件，因此当前页面布局、按钮、Block样式和播放行为均不变。未来接前端时，必须明确展示唯一 `assistant_text(role=spoken)`，说明它对应哪项功能，并由用户亲自确认屏幕文字与实际朗读逐字一致。

### 23.8 唯一下一步

把生产 Chat 的普通回复接入该纯合同：先建立可见 spoken Block，再从同一 Block派生唯一 voice item，并删除 Chat 路径对首句/25 字策略的依赖；本步仍不同时接 Experiment 或重读，避免一次跨越两个生产策略。

## 24. 2026-08-25：普通 Chat 可见语音 Block 生产接入

状态：软件自动闭环与真实 DeepSeek/TTS 探针通过，真实浏览器扬声器体验为 `REAL_PENDING / UX_PENDING`。

### 24.1 先总结与用户现象

此前普通 Chat 屏幕显示完整回答，但语音层只取第一句并最多 25 字，用户听到不到 5 秒就回到聆听。本轮只把普通 Chat 接入统一可见语音 Block；Free/Protocol、continuation、重读、VAD误触保护均未接。

### 24.2 白话理解与专业概念

白话上，模型先交一份约 10 秒、可以独立理解的短答；后端完整检查后才把同一份稿子交给屏幕和喇叭。专业上是 Buffer-before-publication、Single Source of Truth、Budget Propagation 和 Fail-before-visible：模型超 50 字时不会先显示长文再偷偷少读。

### 24.3 数据流（不超过五节点）

```text
DeepSeek按Chat短答策略生成
→ chat_stream缓冲并验证完整正文
→ screen_delta建立 assistant_text(role=spoken)
→ 同文 VoiceDeliveryItem 进入 PlaybackScheduler
→ 浏览器按 source_block_id 校验后调用 /tts
```

### 24.4 入口、字段、函数和状态位置

- 模型入口：`web/agent/core.py::CHAT_POLICY`，要求纯文本、最多50个中文字符、不加“小科”或Markdown；
- HTTP入口：`web/api/chat.py::chat_stream()`；普通正文不再逐token发布，而是在完整验证后发一个 `screen_delta`；
- 合同桥接：`chat.py::_build_chat_spoken_delivery()` → `select_spoken_output_policy()` → `build_spoken_block_plan()`；
- 可见Block：前端 `streaming_chat_v2.js` 使用 `${turnId}:spoken` 与 payload `{role:'spoken', text}`；
- 语音字段：`intent_id / kind=assistant_reply / priority=REVIEW / voice_text / source_block_id / max_chars=50`；
- 预算传递：`VoiceDeliveryItem.max_chars → PlaybackRequest.max_chars → web playback runtime`，解决Scheduler重建时退回旧25字的问题；
- 最终屏幕状态仍只写 `ConversationTurnStore`，音频不写业务库。

### 24.5 前端具体改动与对应功能

- 修改文件：`web/frontend/streaming_chat_v2.js`；
- 修改前：助手Block ID为 `:assistant`，payload只有 `text`，屏幕逐token增长；
- 修改后：仅Chat使用 `:spoken`，payload为 `role=spoken + text`，完整验证后一次显示；Experiment仍保留原 `:assistant` 行为，本轮没有偷偷改实验页面；
- 对应功能：让用户看到的助手气泡就是实际完整朗读稿，voice `source_block_id` 可在同一Turn找到它；
- 没有新增第二聊天区、按钮、管理面板、隐藏节点或新样式；页面视觉仍是原助手气泡，只改变数据身份与发布时间；
- 缓存版本：`streaming_chat_v2.js?v=20260825-spoken-chat`。

### 24.6 实际测试与现场探针

```text
首轮专项：46项中2个NameError + 2个旧护栏失败；修正枚举导入并更新旧25字断言。
第二轮相关：53项中1个旧三生产者Block ID护栏失败；更新为 :spoken 身份。
播放预算专项：29/29 OK。
最终全量：Ran 1123 tests in 7.833s，OK。
Python compile、Node --check、git diff --check：通过。
```

运行现场先发现旧 PID 15000 未实际退出，新探针仍返回逐token/25字；核验其确为项目 Uvicorn 后重启为 PID 16220。第一次新代码探针屏幕已整段发布，但 PlaybackRequest 重建丢失 `max_chars=50`，返回“不能超过25字”；补齐预算贯穿并重启为 PID 14492 后，真实官方 DeepSeek 返回：

```text
screen_delta：人工智能是让机器模拟人类智能来完成学习、推理、识别与决策等任务的技术。
voice_text：与上面逐字一致
source_block_id：turn-probe-spoken-chat-3:spoken
authorization：READY / playback_window_open
```

真实 `/tts` 对同文返回 HTTP 200、audio/mpeg、118560 bytes；ASR重新预热为 `loaded=true / SenseVoiceSmall`。

### 24.7 能证明与不能证明

能证明：当前 PID 14492 已加载新缓存；真实DeepSeek产生符合50字预算的完整短答；屏幕事件与voice_text逐字相同；来源Block使用`:spoken`；50字预算完整穿过Scheduler；真实TTS能合成整段MP3；全量自动测试通过。

不能证明：用户浏览器已刷新；ConversationTurnStore在真实页面成功建立`:spoken` Block；浏览器Audio完整播放118560字节；人耳实际时长约10秒；用户打断、continuation、指定重读、VAD误触保护或Experiment合同已接通。

### 24.8 唯一下一步

用户在真实浏览器 `Ctrl+F5` 后用Chat问“请用一句话解释什么是人工智能”，确认屏幕只出现一段完整短答、语音逐字完整读完且没有中途截断。完成这一步真实UX证据后，再决定接Experiment生产链，不在本轮继续扩大。

## 25. 2026-08-25：暂停后再次 started 的会话事件归一化

### 25.1 先总结与用户现象

用户真实连续通话中打断一次后，后续助手不再发声。修改前日志出现明确 HTTP 500：浏览器 Silero VAD 在短暂停顿后再次上报 `user_speech_started`，而服务端仍保留打开的采集片段，只允许 `user_speech_resumed`，异常为“片段已在采集；请使用 USER_SPEECH_RESUMED”。

### 25.2 白话理解与专业概念

白话上，浏览器说“又开始说话了”，服务端却认为“这句话还没结束，只是接着说”，两个名字描述的是同一个实际动作，因此不该让请求崩溃。专业上，这是边界事件归一化：入口吸收不同 VAD 的事件命名差异，核心状态机仍保持严格状态转换；恢复讲话也作为 barge-in 清除旧 TTS 占用。

### 25.3 数据流（不超过五节点）

```text
Silero再次发 speech_started
→ /voice/runtime/event
→ VoiceRuntimeSessionRegistry 按当前会话状态归一化为 resumed
→ VoiceStateCoordinator 清除旧TTS占用并恢复 user_speaking
→ 后续片段固化、ASR与新回复继续
```

### 25.4 入口、字段、函数和状态位置

- HTTP入口：`web/api/voice_runtime.py::consume_voice_runtime_event()`；
- 消息字段：`conversation_id / type`，本次真实失败的 `type=user_speech_started`；
- 边界归一化：`web/voice_runtime_sessions.py::VoiceRuntimeSessionRegistry.consume()`；仅当 `segment_capturing=true` 且 `user_speaking=false` 时，把重复 started 解释为 resumed；
- 核心转换：`src/core/voice_runtime_state.py::VoiceStateCoordinator._reduce()`；`USER_SPEECH_RESUMED` 设 `user_speaking=true`，同时清空 `tts_playing / active_tts_priority`；
- 最终状态只改变该 `conversation_id` 的内存语音运行状态，不写实验记录、不执行 Tool、不生成 TTS。

### 25.5 实际测试输出

```text
真实失败顺序专项与相邻模块：Ran 34 tests in 0.125s，OK
项目全量：Ran 1132 tests in 7.910s，OK
新服务：PID 33360，GET / 返回 HTTP 200
ASR预热：loaded=true，engine=SenseVoiceSmall
```

### 25.6 能证明与不能证明

能证明：`started → paused → started` 不再返回500；第三个事件在同一采集片段中恢复讲话；started/resumed 两种 barge-in 都清除服务端旧TTS占用；全量自动回归通过；当前8000服务已加载代码且ASR已预热。

不能证明：真实浏览器的下一轮音频一定播放；真实 VAD 是否还会产生其他乱序；扬声器、Audio对象、TTS请求和用户实际听感尚未由本轮自动测试证明。

### 25.7 前端影响说明

本轮没有修改前端文件、按钮、布局或Block展示。变化只在后端如何理解浏览器已有的事件，因此页面刷新不是为了加载新JS，而是为了开始一段干净的真实通话会话。

### 25.8 唯一下一步

在当前真实浏览器开启连续通话，让助手开始朗读后说一句完整的新问题打断，等待新问题识别并观察下一条助手回复是否重新朗读；若仍失败，只采集这一次的新服务日志继续定位，不再同时改VAD阈值或界面。
