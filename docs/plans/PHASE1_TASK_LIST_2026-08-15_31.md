# asr_demo 阶段一任务清单（2026-08-15 ~ 08-31）

> 从 `PLAN_2026-08-14_31.md` 阶段一抽出的独立任务清单，只回答"这半个月要做什么、按什么顺序、做完什么算过"。
> 任务状态、完整任务库与历史证据以 `PROJECT_TASK_CHECKLIST.md` 为准。

**阶段目标**：8/31 提交线上评审版完整功能 Demo —— 识别 → 结构化 → 追问确认 → 结束 → 导出记录 → 消息链路 → TTS 语音播报 + 轻量前端，配评审视频/设计文档/材料。演示输入可控（标准说法一次跑通），**功能不砍**。

## 1. 现状

- 清理五连已完成四刀：FLAGS / SUBMIT / COMMAND / NAMING（REAL_OK 或 AUTO_OK），VERIFY 待总验收。
- 全量自动测试 468 项通过。
- 最近真实会话：`20260814_113958`（显示一致性复验）。
- 尚未完成：导出记录、PRESENT 消息链路、TTS、轻量前端、评审材料。

## 2. 闸门规则

- **硬问题**（程序崩溃 / 数据丢失或错位 / 核心交互失败）修完才进 PRESENT，**不设固定日期**（进展快则提前）。
- **软问题**（显示/话术/误识别但语义能兜底、边缘表达）与 PRESENT 并行，出现即修，不阻塞主线。
- 真实验收暴露的问题，先按上面硬/软判据归类再定优先级，不"发现即必修"。

## 3. 任务清单（按任务逐条列出）

### 主线任务（按先后顺序）

| # | 任务 | 优先级 | 状态 | 做完要得到的结果 |
|---:|---|---|---|---|
| 1 | `RESTORE-NONBLOCK-01` 恢复非阻塞录音 | P0 | TODO | 说完继续说、连续口述不卡（后台处理 + 背压）；同步修正"无需等待 LLM"等与实际行为不符的文案 |
| 2 | `GAPS-FIX-END-01` 结束语追问确认 | P1 | TODO | 非精确结束语 → 系统追问是否结束 → 用户肯定后结束；消除"观察失败 ValueError" |
| 3 | `GAPS-FIX-DEFER-01` 按编号暂缓 | P1 | TODO | 可逆的暂缓候选放行到上下文校验；"问题二先跳过"真正暂缓 |
| 4 | `ANSWER-FALLBACK-ADJACENCY-01` 无编号回答"紧邻"约束 | P1 | TODO | 无编号回答只在"问题来源段 + 1 == 当前段"时自动接，避免隔几句误判成回答 |
| 5 | `INTENT-02-CLEANUP-NAMING-01` 轻量复验 | P0 | AUTO_OK（待复验） | 真实会话确认显示前缀 `[统一链]`、行为与之前一致、不退化 |
| 6 | `GAPS-REVERIFY-01` 复验 | P1 | TODO | 重跑旁路确认⑤②现状、复测③PHG/E，把缺口现状说清楚 |
| 7 | `INTENT-02-CLEANUP-VERIFY-01` 清理后总验收 | P0 | TODO | 五类口述连续会话，清理 + GAPS 定稿、真实功能不减 |
| 8 | 导出：`LLM-10` + `SESSION-02` + `EXPORT-01` | P1 | TODO | 每次实验可导出 Markdown/JSON 记录（评审材料的数据证据） |
| 9 | `PRESENT-INTEGRATE-01` 消息链路基础版 | P1 | TODO | 追问/回执/确认消息有条理输出到屏幕与消息流，不再散落 print |
| 10 | TTS 半双工：`TTS-01` → `TTS-05` | P3 | TODO | 系统语音播报追问和回执；失败回退终端文本、不破坏录音；打断半双工第一版 |
| 11 | 轻量前端（≤1 天） | P3 | TODO | 简单页面实时显示对话消息（喂 PRESENT 消息流），与 C 正式前端不冲突 |
| 12 | 联调 + 评审材料 | — | TODO | 2~3 分钟标准脚本连续跑 3 次；录评审视频、整理设计文档与材料、提交包 |

### 并行任务（软问题 + 铺路，不阻塞主线）

| # | 任务 | 优先级 | 状态 | 做完要得到的结果 |
|---:|---|---|---|---|
| 13 | `RESTORE-DEGRADED-HINT-01` 降级人话 | P1 | TODO | LLM 失败/降级时给用户一句"原始记录已保存、结构化暂不可用" |
| 14 | `SYNC-UI-CLAIMS-01` 文案一致性修正 | P1 | 已扫（2 处 + 2 处） | 用户看到的每句话都与实际行为一致 |
| 15 | `GAPS-FIX-ANSWER-HINT-01` 回答编号提示 | P1 | TODO | 有待确认问题时提示"回答请指定问题编号（如'问题一，…'）" |
| 16 | UX 系列：`UX-FIX-TONE-01` 提示音 / `UX-MODE-01` 输出分层 | P1 | TODO | 关键事件提示音；用户版只显 SCREEN 层、管理员版显全部 |
| 17 | 铺路 Phase 1a/1b：`QUERY-TYPES-01` / `SAFETY-TYPES-01` / `KNOWLEDGE-PROTOCOLS-01` → `UNIFIED-QUERY-01` / `DISPATCH-QUERY-01` / `BYPASS-QUERY-01` / `CONFIG-QUERY-SAFETY-01` / `RAG-CONTEXT-CONTRACT-01` | P1 | TODO | 三组类型合同与 Fake 就位；feature flag 全关时行为不变 |

### 重点展开 · 任务 8 导出记录（`LLM-10` + `SESSION-02` + `EXPORT-01`）

一句话目标：一次实验从原始口述、结构化事件、确认答复到总结都能追溯，并导出为真正可用的 Markdown/JSON 记录（评审材料的数据证据）。

| 子项 | 内容 | 现状 |
|---|---|---|
| 答复目标持久化 | 编号答复与目标问题的关联（target_clarification_id）落盘，形成可审计关联 | `CLARIFY-TARGET-PERSIST-01` TODO |
| 事件版本化 | 事件记录加 schema_version、严格 from_dict、未知字段拒绝、历史兼容读取、request_id、ASR 证据引用、生成路径、采用状态；新写新版本、旧读旧版本、不原地覆盖 | `EXPERIMENT-EVIDENCE-CONTRACT-01` TODO |
| 会话聚合 | 按 session_id 把 ASR / 事件 / 确认 / 总结聚合为一个 `SessionRecord`（当前尚无该聚合类，需新建） | `SESSION-02` TODO |
| 结束总结 | 会话结束时生成 `SessionSummary`（步骤 / 观察 / 异常 / 遗留问题）；`ExperimentSummary` 已 AUTO_OK（`LLM-09`），缺接入主流程与确认收尾 | `LLM-10` TODO |
| 导出 | 从 `SessionRecord` 生成 Markdown/JSON；不读取终端输出或 TTS 历史 | `EXPORT-01` TODO |

**数据来源（已 REAL_OK，导出只做读取聚合）**：ASR JSONL（`STORE-01`）、实验事件 JSONL（`STORE-02`）、确认记录 JSONL（`CONF-STORE-01/02`），每条都能追溯 session/segment。

**验收**：

- 自动：`SessionRecord` 聚合 + 导出器单测；Markdown/JSON 内容与 JSONL 事实逐项一致。
- 真实：一次真实会话导出，人工核对"步骤数 / 异常数 / 待确认数 / 答复关联"与终端、JSONL 一致。
- 门槛：`SESSION-02` 至少 AUTO_OK、`EXPORT-01` 至少 AUTO_OK 并完成一次真实导出——这是进 TTS 的前置条件之一。

**边界**：导出只读 `SessionRecord`，不能根据"曾经显示/朗读过的消息"反推实验事实；事件版本化坚持"旧读旧版本、不原地覆盖"，历史文件不变。编号展示依赖 `SESSION-IDENTITY-CONTRACT-01`（需在 `PRESENT-04` 前定稿）。

### 重点展开 · 任务 9 PRESENT 消息链路（基础版）

一句话目标：把散落 `main.py` 的 `print` 收进统一消息链路，追问/回执/确认消息有条理输出，用户版/开发版分层，实验步骤编号不跳号。

> 基础版范围（`PRESENT-INTEGRATE-01` 已明确）：先接**一种**待确认结果（PendingClarification → PresentationMessage → 简单终端 Presenter），不一次迁移全部 print；完整管线等基础版稳定后展开。

| 子项 | 内容 | 现状 |
|---|---|---|
| 消息对象 | `PresentationMessage`：message_id / kind（DIALOGUE、CURRENT_QUESTION、STATUS、ALERT、SUMMARY）/ priority / 允许渠道 / TTS 策略 | `PRESENT-01` AUTO_OK |
| 协调器 | `PresentationCoordinator`：排序、取消过期消息、按认知负担预算组成消息组 | 待新增 |
| 接入对象 | 先把 PendingClarification → PresentationMessage → 简单终端 Presenter 打通 | `PRESENT-INTEGRATE-01` TODO |
| 认知负担预算 | 同一安全间隙最多 2 条、≤50 字、最多 1 个问题；典型组合"回执 + 一个相关问题" | `PRESENT-03` DESIGN |
| 编号分离 | 内部 utterance_id 与用户看到的 experiment_step_number 分开，确认答复不占实验步骤号 | `PRESENT-04` TODO（依赖 `SESSION-IDENTITY-CONTRACT-01`） |
| 输出分层 | 用户版只显 SCREEN 层；DEBUG 单独写 `results/debug_<session>.log` | `UX-MODE-01` 随此落地 |
| 回执时机 | 当前回答回执优先于旧后台追问 | `PRESENT-02` REAL_OK |
| 明确回执 | 指定编号答复完成后明确显示"问题 N 已解决 / 仍缺哪些字段" | `PRESENT-07` TODO |

**验收**：

- 自动：全量测试通过 + 现有测试数据更新。
- 真实：输出顺序真实验收（`PRESENT-06`）——先回执、再在下一个安全间隙提新问题；实验步骤编号不跳号。
- 体验：九维走查重点看维 1（终端可读）/ 维 7（节奏），`UX-MODE-01` 的 ✗→✓。

**边界**（`OUTPUT_PRESENTATION_POLICY.md` 第 9 节）：`PresentationCoordinator` 不识别命令、不改待确认状态、不直接访问麦克风；GAPS 已修好的行为逻辑（结束语/暂缓/回答）不被 PRESENT 推翻。

### 重点展开 · 任务 10 TTS 半双工

一句话目标：系统语音播报追问和回执；失败回退终端文本、不破坏录音；用户开始说话即停（半双工第一版）。

| 子项 | 内容 | 现状 |
|---|---|---|
| 接口 | `TTSClient`：`stop()` 打断、`is_speaking` 状态、播放生命周期回调（开始/分句结束/全部结束）、失败回退；音色/语速等可变项收进 `TTSOptions` | `TTS-01` TODO |
| 第一版实现 | 系统 TTS（不先接 GPT-SoVITS） | `TTS-02` TODO |
| 播放协调 | 走 `FULL-DUPLEX-01` 的"播放 + 监听"统一接口，半双工是第一个实现 | `TTS-03` TODO |
| 半双工状态 | 新增 SPEAKING 状态：播放期间暂停 KWS/VAD | `TTS-03` TODO |
| 分句与降级 | 长句分句播放；TTS 失败回退终端文本 | `TTS-04` TODO |
| 打断 | 用户开始说话立即停止播放 / 禁止启动 | `TTS-05` TODO |

**文本规则**（`OUTPUT_PRESENTATION_POLICY.md` 第 7 节）：

- 每条语音尽量 <25 字，过长分句；先说来源，再问最关键的一个问题；一次只问一个可立即回答的问题。
- 不朗读 JSON 字段名（`duration` 说"时间"）、文件路径、异常类名、token、耗时。
- 用户开始说话后立即停止或禁止启动 TTS。
- TTS 失败保留 SCREEN 文本，不影响记录和会话。

**验收**：

- 自动：`TTSClient` Fake 单测（打断 / is_speaking / 生命周期回调 / 失败回退）。
- 真实：追问与回执真实语音播报；打断生效；TTS 失败回退到终端文本且记录不丢。
- 体验：九维走查（提示音 ≠ TTS 朗读；TTS 失败用户仍能看到文本）。

**边界与依赖**：TTS 只消费 VOICE 类型消息（`PresentationMessage` 中允许朗读的），不自行挑选业务问题；TTS 失败不影响录音和记录。TTS 在 PRESENT 稳定后展开；`UX-FIX-TONE-01` 提示音顺延到 `PRESENT-INTEGRATE-01` 之后做（触发点挂消息链路，输出层只动一次）。

## 4. 标准演示脚本（供评审/路演）

唤醒"小科小科" → 实验口述 ×2-3 → 追问 → 回答（带编号）→ 查看 → 结束实验记录 → 展示导出记录。全程标准说法（演示可控，不考验非标准输入）。

## 5. 说明

- 主线 1–12 按依赖先后排列：先清债、做总验收，再盖导出 → 消息链路 → TTS → 前端 → 联调。
- 并行 13–17 不阻塞主线，出现即修或空档推进。
- 本清单是 `PLAN_2026-08-14_31.md` 阶段一的抽取版；状态冲突时以 `PROJECT_TASK_CHECKLIST.md` 为准。
