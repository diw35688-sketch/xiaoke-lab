# 语音 Web 迁移：本次对话做了什么

> 范围：只整理本次对话中已经讨论、实现或纠正的内容。任务状态以
> `VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 当前清单为准。
>
> 读法：每项固定回答五个问题——结果是什么、用户操作时发生什么、代码在哪里、为什么重要、当时只推进哪一步。

## 一、先梳理我们对协作方式做出的四次纠正

### 0.1 一轮应该“小而完整”，不是每执行一个命令就停

**一句话结果：** 我们把“一次推进一小步”明确成“一次完成一个可独立验证的能力”，而不是只读一个文件或只改一行就结束。

**用户操作发生了什么：** 你说“下一项” → 我检查一个明确任务 → 完成该任务所需的最小实现和验证 → 讲清因果与证据 → 停在下一个任务之前。

**约定位置：** `C:\Users\dahli\Desktop\AGENTS.md`、`CLAUDE.md`。

**为什么重要：** 这叫**增量交付（incremental delivery）**。任务太大时失败难定位；任务小到只剩一个命令时又没有用户价值。合适粒度是“有输入、有输出、有成功标准”。

**当时唯一下一步：** 按正式任务表，一次完整完成一项。

### 0.2 不再把受限环境启动失败说成 `.venv` 已失效

**一句话结果：** 之前对 Python 启动失败的诊断不严谨，现已明确：先区分沙箱阻止和项目环境故障，不能再无证据地说启动器失效。

**用户操作发生了什么：** 我运行项目 `.venv` → 受限环境可能拒绝创建进程 → 这只说明当前执行方式受阻 → 应在获准环境用同一命令重试 → 只有再次出现明确解释器或依赖错误，才可判断环境问题。

**约定位置：** `CLAUDE.md` 的“项目 `.venv` 与沙箱误判禁止规则”。

**为什么重要：** 这是**故障归因（fault attribution）**。现象相同不代表根因相同；把权限问题误报成环境损坏，会诱导重装或混用解释器，反而制造新故障。

**当时唯一下一步：** 后续测试优先使用项目原 `.venv` 命令，并按真实错误分类报告。

### 0.3 测试按风险选择，不机械地每项都跑全量

**一句话结果：** 局部纯逻辑改动跑专项和相邻回归，共享合同、Web 接线、存储、主流程或阶段收口再跑全量。

**用户操作发生了什么：** 改一个局部合同 → 先跑该合同测试 → 再跑直接依赖它的测试 → 若改动跨入口或触及共享状态，再跑全量 → 报告实际跑了什么，不把专项说成全量。

**约定位置：** `CLAUDE.md` 的“测试要求”和 `.venv` 规则。

**为什么重要：** 这是**风险分层测试（risk-based testing）**。测试范围由改动可能波及的范围决定，既避免每个小改动都付出全量成本，也避免跨模块改动只测一小块。

**当时唯一下一步：** 每项开始前先说明为何选专项、相邻回归或全量。

### 0.4 把播放架构正式加入计划

**一句话结果：** 我们不再只修页面上的“抢话”现象，而是把麦克风、VAD、ASR、状态、门控、队列、调度和 TTS 的职责边界写进正式计划。

**用户操作发生了什么：** 麦克风产帧 → VAD 判定开始/停顿/继续/断句 → ASR 转写固化音频段 → Coordinator 更新运行状态 → Factory 复制快照 → Gate 决定 → Queue 保存延后项 → Scheduler 编排 → TTS 只执行并报告事件。

**计划位置：** `docs/VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 的“语音运行与播放执行架构”。

**为什么重要：** 这是**单一职责（Single Responsibility）**和**状态机（state machine）**设计。每个事实只能有一个权威生产者，才能避免浏览器以为“用户在说话”、服务器却以为“空闲”。

**当时唯一下一步：** 先逐个建立播放请求、上下文和决定合同。

## 二、第 1～16 项：先建立“不抢话”的播放决策与执行架构

### 1. 播放请求合同

**一句话结果：** 每条待播放语音现在都带有重要性、创建时间、有效期和替代键，不再只是一段裸文本。

**用户操作发生了什么：** 系统产生一句提示 → 包装成 `PlaybackRequest` → 标记紧急程度和有效时间 → 交给后续门控判断。

**代码位置：** `src/core/playback_request.py`，测试 `tests/test_playback_request.py`。

**为什么重要：** 这是**领域对象（domain object）**。把规则需要的数据放进明确对象，后面才能回答“能否延后、何时过期、哪条可替代哪条”。

**当时唯一下一步：** 定义判断播放时所需的运行上下文。

### 2. 播放上下文合同

**一句话结果：** 用户是否讲话、ASR 是否处理中、TTS 是否播放、会话处于什么阶段，被统一描述成一个上下文。

**用户操作发生了什么：** 用户讲话或系统状态变化 → 当前事实写入运行状态 → 判断播放前读取为 `PlaybackContext`。

**代码位置：** `src/core/playback_context.py`，测试 `tests/test_playback_context.py`。

**为什么重要：** 这是**决策上下文（decision context）**。请求描述“想播什么”，上下文描述“现在发生什么”，两者不能混成一个对象。

**当时唯一下一步：** 定义 Gate 可以返回哪些正式决定。

### 3. 播放决定合同

**一句话结果：** 播放判断统一返回 `READY / DEFERRED / DROP / PREEMPT`，不再用零散布尔值表达。

**用户操作发生了什么：** 请求和上下文进入判断 → 返回立即播、延后、丢弃或抢占之一 → Scheduler 按决定执行。

**代码位置：** `src/core/playback_decision.py`，测试 `tests/test_playback_decision.py`。

**为什么重要：** 这是**代数数据类型式的显式状态（explicit outcome states）**。一个 `true/false` 无法区分“现在不能播但稍后要播”和“永远不要播”。

**当时唯一下一步：** 写出重要性与播放时机之间的纯规则。

### 4. 优先级与时机规则

**一句话结果：** 不同重要性的语音在讲话、识别和播放状态下应如何处理，变成可单独测试的纯规则。

**用户操作发生了什么：** 普通追问遇到用户讲话 → 延后；过期追问 → 丢弃；满足限定条件的安全提示 → 可抢占。

**代码位置：** `src/core/playback_rules.py`，测试 `tests/test_playback_rules.py`。

**为什么重要：** 这是**策略规则（policy rule）**与执行分离。纯规则不直接播放音频，因此输入相同就应得到相同结果，便于穷举边界。

**当时唯一下一步：** 用 Gate 把请求、快照和规则组合起来。

### 5. PlaybackGate

**一句话结果：** `PlaybackGate` 成为无副作用的统一播放许可判断口。

**用户操作发生了什么：** Scheduler 提交请求和快照 → Gate 只计算决定 → 不碰队列、不调用 TTS、不修改状态。

**代码位置：** `src/core/playback_gate.py`，测试 `tests/test_playback_gate.py`。

**为什么重要：** 这是**纯函数边界（pure decision boundary）**。决定和动作分开后，才能准确证明规则，而不是靠“好像没有声音”猜测。

**当时唯一下一步：** 为 `DEFERRED` 请求建立专用队列。

### 6. 延后播放队列

**一句话结果：** 暂时不能播放但仍有价值的请求会进入 `DeferredPlaybackQueue`，而不是直接消失。

**用户操作发生了什么：** 用户正在讲话 → 普通提示被判 `DEFERRED` → 队列保存 → 等状态变化后再判断。

**代码位置：** `src/core/deferred_playback_queue.py`，测试 `tests/test_deferred_playback_queue.py`。

**为什么重要：** 这是**缓冲（buffering）**，但不是无条件积压。延后项仍受过期、替代和会话取消规则约束。

**当时唯一下一步：** 定义哪些状态变化会触发重新判断。

### 7. 重新判断触发器

**一句话结果：** 用户停止讲话、ASR 完成或 TTS 结束等状态变化，会明确触发延后队列重评。

**用户操作发生了什么：** 用户讲话结束 → Coordinator 更新状态 → 产生重评触发 → Scheduler 再把队列项交给 Gate。

**代码位置：** `src/core/playback_reevaluation.py`，测试 `tests/test_playback_reevaluation.py`。

**为什么重要：** 这是**事件驱动（event-driven）**。队列不会自己醒来，必须由真实状态变化推动，才能避免轮询和漏播。

**当时唯一下一步：** 让已经失去时效的延后语音不再补播。

### 8. 超期丢弃

**一句话结果：** 延后过久、已经失去语境的语音会被丢弃。

**用户操作发生了什么：** 一条追问进入队列 → 用户持续讲话 → 当前时间超过有效期 → 重评得到 `DROP` → 不再播放。

**代码位置：** `src/core/playback_expiry.py`，测试 `tests/test_playback_expiry.py`。

**为什么重要：** 这是**时效性（time-to-live, TTL）**。语音提示不是普通消息，晚几秒播放可能从帮助变成打扰。

**当时唯一下一步：** 处理新追问覆盖旧追问。

### 9. 新请求替代旧请求

**一句话结果：** 同一语义位置出现更新的追问时，旧追问会被替代。

**用户操作发生了什么：** 旧追问因讲话被延后 → 系统生成同替代键的新追问 → 队列移除旧项 → 只保留最新项。

**代码位置：** `src/core/playback_supersession.py`，测试 `tests/test_playback_supersession.py`。

**为什么重要：** 这是**最新值语义（latest-value semantics）**。若不替代，用户会在讲话后连续听到互相过时的问题。

**当时唯一下一步：** 会话结束时取消所有剩余语音。

### 10. 会话取消

**一句话结果：** 挂断或会话结束会清理该会话尚未执行的播放请求。

**用户操作发生了什么：** 用户挂断 → 产生会话取消 → 队列按会话清理 → 后续状态变化也不会把旧语音重新放出来。

**代码位置：** `src/core/playback_session_cancel.py`，测试 `tests/test_playback_session_cancel.py`。

**为什么重要：** 这是**生命周期管理（lifecycle management）**。请求必须从属于会话，否则旧会话的副作用会泄漏到新会话。

**当时唯一下一步：** 建立唯一的语音运行状态写入者。

### 11. VoiceStateCoordinator

**一句话结果：** `VoiceStateCoordinator` 成为 `VoiceRuntimeState` 的唯一更新入口。

**用户操作发生了什么：** VAD、ASR 或 TTS 报告事件 → Coordinator 校验并更新状态 → 其他模块只读取，不各自改状态。

**代码位置：** `src/core/voice_runtime_state.py`，测试 `tests/test_voice_runtime_state.py`。

**为什么重要：** 这是**单一写入者（single writer）**。多个模块直接改同一状态会产生竞态：先后顺序稍变，服务器就可能错误地认为用户没有讲话。

**当时唯一下一步：** 从可变状态生成一次判断专用的不可变快照。

### 12. PlaybackContextFactory

**一句话结果：** 播放判断不再直接抓取变化中的运行状态，而是先复制成不可变快照。

**用户操作发生了什么：** Scheduler 准备判断 → Factory 在一个时点读取运行状态 → 生成 `PlaybackContext` → Gate 对该快照作决定。

**代码位置：** `src/core/playback_context_factory.py`，测试 `tests/test_playback_context_factory.py`。

**为什么重要：** 这是**快照一致性（snapshot consistency）**。若判断过程中状态被另一事件改掉，同一次决策可能前半段看到“讲话中”、后半段看到“空闲”。

**当时唯一下一步：** 建立唯一执行编排者 `PlaybackScheduler`。

### 13. PlaybackScheduler

**一句话结果：** Gate、Queue 和 TTS 的动作由 `PlaybackScheduler` 统一编排。

**用户操作发生了什么：** 播放请求到达 → Scheduler 创建快照并询问 Gate → `READY` 交给 TTS、`DEFERRED` 入队、`DROP` 丢弃、`PREEMPT` 走抢占。

**代码位置：** `src/core/playback_scheduler.py`，测试 `tests/test_playback_scheduler.py`。

**为什么重要：** 这是**应用服务/编排器（orchestrator）**。Gate 负责决定，Scheduler 负责副作用，避免每个 Web 入口自己复制一套播放流程。

**当时唯一下一步：** 把具体 TTS 限制在一个薄适配器中。

### 14. TTSAdapter 执行事件

**一句话结果：** TTS 只负责 `play/stop`，并用开始、结束、失败等事件报告执行事实。

**用户操作发生了什么：** Scheduler 发出播放命令 → Adapter 调真实 TTS → 报告 `STARTED` → 完成报 `FINISHED`，异常报 `FAILED`。

**代码位置：** `src/core/tts_adapter.py` 及相应 TTS 适配测试。

**为什么重要：** 这是**端口与适配器（Ports and Adapters）**。业务层不依赖某个播放器的细节，只依赖稳定合同，后续才能替换实现。

**当时唯一下一步：** 只允许限定的关键请求抢占当前播放。

### 15. 限定抢占

**一句话结果：** 只有满足规则的 `CRITICAL` 请求才能停止当前语音并抢占播放。

**用户操作发生了什么：** TTS 正在播放 → 关键安全提示到达 → Gate 返回 `PREEMPT` → Scheduler 先 stop 再播放新请求；普通追问不会这样做。

**代码位置：** `src/core/playback_scheduler.py`、`tests/test_playback_preemption.py`。

**为什么重要：** 这是**优先级抢占（priority preemption）**。抢占过宽会让系统频繁自我打断，过窄又会延误安全信息，所以必须由显式规则约束。

**当时唯一下一步：** 隔离 TTS 失败，防止一次播放异常破坏整个会话。

### 16. TTS 失败边界

**一句话结果：** TTS 失败被限制在单次执行边界内，并明确是否可重试。

**用户操作发生了什么：** Scheduler 请求播放 → TTS 抛错或报告失败 → 失败边界记录结果 → 运行状态被正确收尾 → 其他已保存业务数据不被回滚。

**代码位置：** `src/core/tts_failure_boundary.py` 及对应测试。

**为什么重要：** 这是**失败隔离（failure isolation）**。语音是呈现层副作用，不能因为“没念出来”就破坏已经成功保存的实验记录。

**当时唯一下一步：** 把多个记录入口统一到同一个保存业务服务。

## 三、第 17～29 项：把记录、呈现和播放入口接到同一条链

### 17. SharedRecordService

**一句话结果：** 保存记录的业务流程被抽成共享服务，HTTP 路由和工具入口不再各写一套。

**用户操作发生了什么：** 录音或工具产生观察 → 共享服务校验并保存 → 保存成功后才生成屏幕/追问等呈现意图。

**代码位置：** `web/record_service.py`，测试 `tests/test_shared_record_service.py`。

**为什么重要：** 这是**应用服务复用（application service reuse）**和**事务边界（transaction boundary）**。先保存再呈现，避免用户听到“已记录”但数据库实际失败。

**当时唯一下一步：** 让 `/record` 路由改用共享服务。

### 18. `/record` 使用共享服务

**一句话结果：** 浏览器录音提交入口不再直接编排保存和反馈，而是调用共享记录服务。

**用户操作发生了什么：** 浏览器提交 ASR 文本 → `POST /record` 接收 → 调 `SharedRecordService` → 返回保存后的正式结果。

**代码位置：** `web/api/record.py`、`web/record_service.py`。

**为什么重要：** 这是**薄控制器（thin controller）**。HTTP 层只做协议转换，业务规则留在共享服务，减少入口之间行为漂移。

**当时唯一下一步：** 让 `record_observation` 工具也走同一服务。

### 19. 工具入口使用共享服务

**一句话结果：** Agent 的 `record_observation` 工具与 `/record` 共用同一保存业务逻辑。

**用户操作发生了什么：** 对话触发记录工具 → `web/lab_tools.py` 解析工具参数 → 调共享服务 → 返回固定字段结果。

**代码位置：** `web/lab_tools.py`、`web/record_service.py`，测试 `tests/test_lab_tool_record_service.py`。

**为什么重要：** 这是**多入口单业务核心（multiple adapters, one use case）**。入口可以不同，但保存顺序和失败语义必须相同。

**当时唯一下一步：** 把工具结果转换成正式呈现对象。

### 20. 工具结果呈现

**一句话结果：** 工具结果先转换成 Intent、文案和 DeliveryPlan，再交给屏幕与语音渠道。

**用户操作发生了什么：** 工具完成 → 生成 `PresentedToolResult` → 确定用户看见的文案和允许的交付方式 → 不再让前端猜工具字段。

**代码位置：** `web/tool_presentation.py`、`web/agent/core.py`，测试 `tests/test_tool_presentation.py`、`tests/test_agent_tool_presentation.py`。

**为什么重要：** 这是**呈现模型（presentation model）**。业务结果和用户话术分开，保存合同不会因 UI 文案变化而改变。

**当时唯一下一步：** 把 chat 的普通文本增量限定为纯屏幕事件。

### 21. chat delta 只负责屏幕

**一句话结果：** chat 的 `delta` 只增量显示文字，不再天然代表“这段文字可以播放”。

**用户操作发生了什么：** 模型输出文本块 → 后端发送 `screen_delta` → 浏览器追加屏幕文字 → 不直接送入 TTS。

**代码位置：** `web/stream_contract.py`、`web/api/chat.py`、`web/frontend/streaming_chat_v2.js`。

**为什么重要：** 这是**渠道分离（channel separation）**。可见文本和可播放语音不是同一种授权，否则每个 token 都可能绕过 PlaybackGate。

**当时唯一下一步：** 由后端发送显式语音交付事件。

### 22. 后端显式 `voice_delivery`

**一句话结果：** 后端开始发送带正式语义的 `voice_delivery`，而不是让前端从文字事件猜测是否朗读。

**用户操作发生了什么：** 业务产生可呈现结果 → 后端形成语音交付批次 → 经过许可判断 → SSE 发送显式事件给浏览器。

**代码位置：** `src/core/voice_delivery.py`、`web/tool_presentation.py`、`web/stream_contract.py`、`web/api/chat.py`。

**为什么重要：** 这是**能力授权（capability authorization）**。事件不仅携带内容，还表达“这段内容被哪个后端规则批准用于语音”。

**当时唯一下一步：** 删除前端 `delta → enqueueSpeech` 的旧旁路。

### 23. 删除 delta 直达 TTS

**一句话结果：** 两套流式聊天前端都不再把文本 delta 直接塞进朗读队列。

**用户操作发生了什么：** 浏览器收到 delta → 只更新屏幕 → 没有 `enqueueSpeech` → 只有正式语音事件才能进入播放链。

**代码位置：** `web/frontend/streaming_chat.js`、`web/frontend/streaming_chat_v2.js`。

**为什么重要：** 这是**消除旁路（remove bypass path）**。新架构存在时若旧路仍可播放，门控就只是“可选建议”而非真正的唯一入口。

**当时唯一下一步：** 删除 `task_queued` 触发朗读的第二条旁路。

### 24. 删除 `task_queued` 直达 TTS

**一句话结果：** “任务已排队”这类状态事件不再自动触发语音。

**用户操作发生了什么：** 浏览器收到 `task_queued` → 更新任务状态或提示 → 不调用朗读 → 等正式 `voice_delivery`。

**代码位置：** `web/frontend/streaming_chat.js`、`web/frontend/streaming_chat_v2.js`。

**为什么重要：** 这是**事件语义单一化（single semantic meaning）**。状态通知只说明任务状态，不能同时暗含播放权限。

**当时唯一下一步：** 建立只消费获准事件的前端播放客户端。

### 25. 前端播放事件客户端

**一句话结果：** 前端通过专门客户端校验并执行后端获准的播放事件。

**用户操作发生了什么：** 浏览器收到 `voice_delivery` → `voice_delivery_client.js` 校验结构和决定 → 只有允许的决定进入 TTS，其他决定不播放。

**代码位置：** `web/frontend/voice_delivery_client.js`、`web/app.py`，测试 `tests/js/test_voice_delivery_client.js`。

**为什么重要：** 这是**协议消费者（protocol consumer）**。即使后端是权威，前端仍要拒绝畸形事件，避免 UI 代码随意调用播放器。

**当时唯一下一步：** 让 `/record`、tool 和 chat 真正共用 Scheduler。

### 26. 三入口统一调度

**一句话结果：** `/record`、工具和 chat 的语音请求都经过同一个 `PlaybackScheduler`。

**用户操作发生了什么：** 任一入口生成呈现意图 → 转为播放请求 → `web/playback_runtime.py` 交给共享 Scheduler → 决定后才下发前端。

**代码位置：** `web/playback_runtime.py`、`web/api/record.py`、`web/api/chat.py`、`web/frontend/voice_asr.js`、`web/frontend/mobile.js`。

**为什么重要：** 这是**统一执行路径（single execution path）**。规则统一不只靠“复制相同代码”，而要让所有入口调用同一个权威对象。

**当时唯一下一步：** 用自动化测试冻结这条职责边界。

### 27. C5 自动验收与职责冻结

**一句话结果：** 自动测试开始保护“谁能产生播放、谁只能显示文字、谁负责保存”的架构边界。

**用户操作发生了什么：** 后续有人修改前后端 → 架构冻结测试扫描关键行为 → 若重新引入 delta 朗读或旁路，测试失败。

**代码位置：** `tests/test_c5_architecture_freeze.py` 及 C5 各专项测试。

**为什么重要：** 这是**架构适应度函数（architecture fitness function）**。它把设计约定变成机器可检查的约束，防止旧路悄悄长回来。

**当时唯一下一步：** 修复真实验收发现的自由实验追问丢失。

### 28. 保留自由实验的语义追问

**一句话结果：** 自由实验中统一理解产生的缺失字段和追问，不再在 Web 桥接或空方案评估中丢失。

**用户操作发生了什么：** 用户说出不完整观察 → 统一理解产出 `missing_fields` 和 `follow_up_question` → 桥接层完整透传 → 保存成功 → 页面显示正式追问；保存失败则不显示成功回执或追问。

**代码位置：** `llm_bridge` 相关实现、`web/record_service.py`、对应桥接与共享服务测试。

**为什么重要：** 这是**语义保真（semantic preservation）**和**提交后投影（post-commit projection）**。中间层不能只保留部分字段，也不能在数据未落盘前向用户承诺成功。

**当时唯一下一步：** 缩短 `/record` 等待期间的首次可见反馈。

### 29. `/record` 流式首反馈

**一句话结果：** 录音提交后会先显示“正在理解”，保存完成后再给最终结果，但这不是模型 token 或 TTS 内容级流式。

**用户操作发生了什么：** 浏览器 `POST /record/stream` → 服务端立即发 `record_status/understanding` → 共享记录事务执行 → 成功发 `record_result`，失败只发 `record_error`。

**代码位置：** `web/api/record.py`、桌面和手机录音前端的 `ReadableStream` 消费代码；旧 `POST /record` 仍保留兼容。

**为什么重要：** 这是**渐进反馈（progressive feedback）**与**NDJSON 流协议**。它降低用户等待时的不确定感，但不能被夸大成“理解过程或语音已经逐字流出”。

**当时唯一下一步：** 为通话模式定义 Silero VAD 适配合同。

## 四、第 30～32 项：区分人声、停顿与断句

### 30. Silero VAD 合同

**一句话结果：** VAD 输入、四类状态事件和失败回退被先定义清楚，尚未在这一项直接替换真实麦克风链。

**用户操作发生了什么：** 16 kHz 单声道、512 采样点音频帧进入适配器 → 输出讲话开始、短暂停顿、继续或断句 → 映射为 `VoiceRuntimeEventType`；运行库或推理失败则明确要求 `USE_RMS`。

**代码位置：** `src/core/silero_vad_contract.py`、`tests/test_silero_vad_contract.py`。

**为什么重要：** 这是**先合同后集成（contract-first integration）**。VAD 负责声学边界，ASR 负责把已经固化的音频段变成文字；用户说话中间的短停顿不应立即当成一句结束。

**当时唯一下一步：** 把通话模式从 RMS 主判断切到 Silero，同时保留明确回退。

### 31. Silero 接入连续通话

**一句话结果：** 连续通话入口优先使用 Silero，成功时不再同时创建 RMS 麦克风链，失败时才回退 RMS。

**用户操作发生了什么：** 用户点击通话 → `phone_call.js` 启动 Silero → `call_silero_vad.js` 接收开始、概率和结束回调 → 形成 16 kHz 音频段 → 送入既有 WAV/ASR 队列；初始化或运行失败则停掉 Silero 后启用 RMS。

**代码位置：** `web/frontend/call_silero_vad.js`、`web/frontend/phone_call.js`、`tests/js/test_call_silero_vad.js`、`tests/js/test_phone_call_silero_fallback.js`。

**为什么重要：** 这是**主路径与降级路径（primary/fallback path）**。两条麦克风链不能同时工作，否则同一声音可能被录两次、提交两次或互相争抢设备。

**当时唯一下一步：** 验证边界、失败回退以及真实模型固定样本。

### 32. VAD 回归与空段修复

**一句话结果：** 修复了 sherpa 队列先出队再读样本导致空音频段的问题，并用真实模型固定样本覆盖人声、静音和噪音。

**用户操作发生了什么：** VAD 检出一段语音 → `VadSegmenter` 先复制并组装 `VoiceSegment` → 成功后才 `pop()` → ASR 得到非空音频；若底层读取失败，不提前破坏队列内容。

**代码位置：** `src/audio/vad_segmenter.py`、`tests/test_vad_segmenter.py`、`tests/test_vad_real_model_regression.py`，固定音频 `web/voice/reference.wav`。

**为什么重要：** 这是**先取值后提交（read/construct before commit）**的异常安全设计。若先 `pop()`，数据所有权已经移走，再访问就可能只剩空壳；测试还必须区分模拟状态机正确和真实模型样本正确。

**当时唯一下一步：** 进入真实浏览器与真实声学环境，验证播放时机。

## 五、当前我们已经能证明什么

**一句话结果：** 第 1～32 项已达到计划中的 `AUTO_OK`，但“不抢话”的真实体感仍没有被自动测试替代。

**用户操作发生了什么：** 自动测试构造请求、状态、事件和固定音频 → 验证规则、接线、回退与固定样本 → 尚未覆盖你在真实浏览器中边说边听时的房间回声、设备延迟和主观节奏。

**代码与记录位置：** `docs/VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 当前 41 项清单及第 30～32 项闭环记录。

**为什么重要：** `AUTO_OK` 是**自动化证据**，`REAL_OK` 是**真实环境功能证据**，`UX_CONFIRMED` 是**用户体验裁决**。三者不能混写；固定 WAV 通过不能证明真实麦克风环境一定不误触。

**当前唯一下一步：** 第 33 项 `VOICE-C3-1-PLAYBACK-TIMING-REAL`——只真机验证“用户讲话期间不播放、讲话结束后延后项恢复、过期项不补播”，暂不同时做第 34 项 barge-in 验收。

## 六、2026-08-25 流式 TTS 真机测量发现的问题

### 后台任务结果仍存在直接播放旁路

**现象：** 浏览器计时表中出现一条 `intent_id = null`、`delivery_to_play_ms = null` 的 275 字语音样本；正式 chat 样本的 `delivery_to_play_ms` 为 311～360 ms，均低于 1 秒。

**代码证据：** `web/frontend/task_panel.js` 的 `deliverResults()` 在后台任务完成后直接调用 `window.enqueueSpeech?.(text)`，没有消费后端 `voice_delivery`，因此不会携带正式播放授权及 intent 身份。`tests/test_c5_architecture_freeze.py` 和 `tests/test_frontend_screen_delta.py` 当前还把这条旁路固定为“例外”。

**影响：** 系统实际上仍有两种语音触发方式。后台任务播报无法完整进入统一的 READY/PREEMPT 决策、会话状态、打断和播放时机追踪；现有架构测试通过也不能证明所有发声都已收敛到唯一入口。

**唯一修复方向：** 删除 `task_panel.js` 对 `enqueueSpeech` 的直接调用，后台任务结果暂时只显示文字；将来确需播报时，由后端生成正式 `voice_delivery`，再由 `voice_delivery_client.js` 消费。同步把两项测试改为禁止该旁路，而不是继续保留第二条播放路径。

**当前状态：** `RECORDED / TODO`。本项只记录问题，尚未修改生产代码。
