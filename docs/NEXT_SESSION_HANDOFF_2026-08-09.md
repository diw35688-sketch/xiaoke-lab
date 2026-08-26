# asr_demo 当前工作区交接说明

最后整理：2026-08-15

> 本文件是下一会话的短入口，不保存完整历史。任务状态以
> `PROJECT_TASK_CHECKLIST.md` 为准，架构原因见 `PROJECT_ARCHITECTURE.md`，
> 文档关系见 `docs/README.md`。

## 1. 当前结论

- 正式解释器：Python 3.11.9，项目 `.venv` 可用。2026-08-15 曾因受限执行权限
  无法启动而被误判为环境损坏；正常权限复核全量 497 项通过，环境无问题。
- **PRESENT 子步 A 全部完成（A-1/A-2a/A-2b/A-3/A-4）= AUTO_OK**：A-1 不可变 `PresentationIntent`；A-2a 记录回执文案目录；A-2b 追问/回答/确认/暂缓文案 + 字段名中文化（temperature→温度）；A-3 `TerminalRenderer`（封装 ui_mode + review 多行文案）；A-4 投影层（业务事实→Intent，补 answer 结构化字段）。专项 57/57、正式全量 544/544 通过。未接 main，用户输出零变化，均跳过 UX 走查。
- 核心依赖和 `src.main` 导入成功；冷启动约 113 秒。
- 全量自动测试：`Ran 562 tests — OK`（含 PRESENT 子步 A + B-1/B-2/B-3 全部）。
- `RESTORE-NONBLOCK-01`（P0）恢复非阻塞录音 + 拆两句谎话：**REAL_OK**（会话 20260815_094954 连说 10 段不卡、计数正确；新建 `OrderedTaskQueue` + `UnifiedSegmentProcessor`，main 主循环改为"录音→提交后台→显示"；两句谎话已拆）。体验=用户接受当前"结果延后显示"节奏，前瞻要求 **TTS 不乱序朗读**（登记 TIMING-02）。
- 三个硬 GAPS + TIMING-01：**END-01/DEFER-01/TIMING-01 REAL_OK、ADJACENCY-01 AUTO_OK**（会话 20260815_111049/112341）。真实验收抓出并修复"`register_clarification` 不设 current 导致暂缓弃权"根因（新问题创建即当前问题）。全量 **488 项**。**defer_targeted（按编号暂缓"问题二先跳过"）仍 TODO**。
- `MAIN-SESSION-CONTEXT-01`/`MAIN-RUNTIME-HARDEN-01`/`INTENT-02-CLEANUP-FLAGS-01`/`INTENT-02-CLEANUP-SUBMIT-01`/`INTENT-02-CLEANUP-COMMAND-01`：全部 REAL_OK。
- A+B（任务 34/35/36）与显示一致性：**全部 REAL_OK**（会话 `20260814_113958` 验证兜底显示自洽）。
- `INTENT-02-CLEANUP-NAMING-01` 去影子命名：**AUTO_OK**（shadow 全部改为正式执行链命名：`UnifiedObserver`/`UnifiedObservation`/`display_observation`/`unified-` 前缀/`[统一链]` 显示；468 项通过），待一次轻量真实会话不退化复验。
- `INTENT-02-ASR-ROBUSTNESS-01`：REAL_OK；7 缺口登记 `ASR-ROBUSTNESS-RULE-GAPS-01`；补充观察登记 `ASR-ROBUSTNESS-RULE-GAPS-02`（项 E 已结案，其余**用户指示先不改代码、等确认**）。
- **`UX-BASELINE-01` 体验基线走查（用户 2026-08-14 提出"终端看不出体验"后建立）：完成，体验状态 UX_ISSUES**。产出：`docs/UX_WALKTHROUGH_CHECKLIST.md`（九维走查表 + 标准脚本 + 判定规则 + **7.5 UX 价值追踪表**（UX 问题↔任务映射，回答"当前工作对体验有没有用"），体验状态已入任务清单）；会话 `20260814_174441` 走查，11 项问题 UX-01~11，证据 `results/walkthrough_baseline_session_20260814_174441.txt`，逐行标注版 `results/walkthrough_baseline_annotated_20260814_174441.md`。**用户 2026-08-14 决定暂不与 PRESENT 强制绑定**；UX-09 提示音登记 `UX-FIX-TONE-01`（P1，**等 GAPS 修复完成后做**）；UX-10 嘈杂识别三个真实样例已入鲁棒性语料（`narration_plan.json` 段 29/30/31，28→31 段，全量 468 项通过），修复走既有 ASR 线；**UX-11 用户版/管理员版输出分层与 PRESENT-INTEGRATE-01 同源，作为其用户可见验收标准，登记 `UX-MODE-01`（随 PRESENT 排期 8/23 落地）**。注意：GAPS 阶段即解决 UX-03（ANSWER-HINT 编号提示）与 UX-05（END 固定结束语提示）两个体验项，不必等 PRESENT。
- 最近真实会话：`20260814_174441`（体验基线走查）。
- **评委审计发现（2026-08-14，三笔此前漏记的债）**：①**非阻塞录音丢失**——删后台线程后 main 主循环同步串行（observe 调 LLM 期间麦关闭，热2.6s/冷10.98s），但 main.py 319-320 仍打印"无需等待 LLM 处理完成"（**系统在说谎**）；旧路靠 SessionProcessingQueue 后台线程+背压真机验收过"连续5段不卡"，此能力已丢且 5.3 表曾误写成"无此需求"。②**降级人话提示丢失**——LLM 失败时用户看不到"原始记录已保存"，只有开发日志。③**文案与行为一致性**未核查。已登记 `RESTORE-NONBLOCK-01`(P0)/`RESTORE-DEGRADED-HINT-01`(P1)/`SYNC-UI-CLAIMS-01`(P1)；硬/软判据补充"文案说谎"归类规则（误导操作节奏=硬问题）。
- `INTENT-02-ASR-ROBUSTNESS-01` ASR 误识别鲁棒性评测：**REAL_OK（提前执行，用户直接要求，不改变 NAMING-01 的 P0 顺序）**。交付：`evaluation/narration_robustness/narration_plan.json`（28 段噪声口述语料，每段 spoken/observed 双文本+期望标注）、`src/evaluation/narration_robustness_plan.py`（严格 schema）、`tests/test_narration_robustness_plan.py`（21 项）、`scripts/evaluate_narration_robustness.py`（--mode deterministic/real）。确定性：零误触发 13/依赖 LLM 7/精确命中 5/已知限制 3。真实 DeepSeek 旁路（只读）：**21/28 一致、7 缺口**。
- **重要：7 个缺口用户明确指示先不改代码、只记录**（已登记任务清单第 37 项 `ASR-ROBUSTNESS-RULE-GAPS-01`，每条含段号/输入/实际/期望/修复方向；详见该行与 LEARNING_REVIEW 最新条目）。
- **ASR 后处理接入计划（2026-08-14 决策）**：`ASR-CMD-02-POSTPROCESS-01` 已 REAL_OK（术语后处理 0/4→4/4、零回退），但样本内选词有过拟合风险故未接 main。**接入时机 = 组长确定演示实验领域（生物/物理/医药）后，重启该领域术语采集 + 独立语音复验 + 接入**（工厂给 `SenseVoiceBackend` 注入术语后处理函数，下游无感，不影响换模型等后续路线）。**提醒：组长确定后立刻启动，别压到 8 月底**——后处理是 P2 不阻塞评审，但赶工风险要规避。
- 孤儿模块（`clarification_command_handler.py`、`targeted_clarification.py`）main 已不调用，删除与否留待 VERIFY 前集中处理。
- 工作区存在用户累计未提交修改；不得覆盖、回退或混入无关变更。

## 2. 当前唯一下一项

**明天开工清单（2026-08-14 夜定）**：按"硬问题清零即进 PRESENT"的闸门，先做硬问题：

1. ~~`RESTORE-NONBLOCK-01`~~ ✅ **已完成 REAL_OK（2026-08-15，会话 20260815_094954）**；开工从第 2 项起
2. ~~`GAPS-FIX-END-01`~~ ✅ **REAL_OK**（会话 111049：追问"是否结束？"→"是"→结束）
3. ~~`GAPS-FIX-DEFER-01`~~ ✅ **REAL_OK**（会话 112341：暂缓生效；defer_targeted 按编号暂缓已补）
4. ~~`ANSWER-FALLBACK-ADJACENCY-01`~~ ✅ **AUTO_OK**（紧邻约束 + 单测）
5. ~~`RESTORE-DEGRADED-HINT-01`~~ ✅ **REAL_OK**（降级打印人话"原始记录已保存，结构化处理暂时不可用"）
6. ~~`GAPS-REVERIFY-01`~~ ✅ **REAL_OK**（真实旁路 21/31；真实会话 E/③/D 闭环）

> **硬问题已清零，下一步进 PRESENT-INTEGRATE-01**。遗留：②同音错词确认（走 ASR 层）、"是"单字易被 ASR 听成"Sure."（已改提示语引导说"是的"，根治走 ASR 层）。

> PRESENT 当前停靠点：子步 A + B-1/B-2/B-3/B-4 全部完成。B-4 真实验收（会话 20260815_212615）通过项：编号分离、结束汇总用户语言、回执及时（维4/5/9✓）；**发现 4 个软问题已登记看板 19-22**：①开发输出泄漏（`PRESENT-FIX-LEAK-01`）、②投影层 no_action 无容错反馈（`PRESENT-NOACTION-FEEDBACK-01`）、③**LLM 缺字段追问漂移**（`LLM-FOLLOWUP-DRIFT-01`，prompt 未变、模型服务端漂移，缺确定性兜底）、④ASR 误识别走 ASR 线。全量 562 项。

> **PRESENT 呈现筛选决策（用户 2026-08-16）**：不把旧 `print()` 原样迁入新链路，按
> `ONCE_PER_SESSION / ON_EVENT / ON_STATE_CHANGE / ON_REQUEST / END_ONLY / LOG_ONLY`
> 六类准入。会话说明与“请开始口述”只出现一次；删除每段“系统将立即继续监听”及
> VAD/录音过程噪声；无变化时静默监听；结束信息合并成单一摘要。完整合同见
> `docs/PRESENT_DESIGN.md` 第 13 节。后续 QUERY/DENY/WARNING/TTS 均必须复用该时机分类。

> **`PRESENT-ADMISSION-01` 第一刀 AUTO_OK（2026-08-16）**：首次“请开始口述”并入
> 会话开始块，只显示一次；删除每段“系统将立即继续监听”。集成测试证明三段会话中
> 两条一次性提示各出现 1 次、循环噪声为 0，同时逐段失败回执和结束反馈仍存在；
> 专项 1/1、全量 562/562 通过。下一刀处理 `LOG_ONLY` 输出泄漏。

> **`PRESENT-ADMISSION-01` 第二刀 AUTO_OK（2026-08-16）**：`vad_recorder.py` 的模型加载、
> 麦克风就绪、人声检测、溢出、音频时长和保存路径，`wakeword/detector.py` 的模型加载、
> 待唤醒和溢出，以及手动 recorder 的设备状态/保存路径均由直接 `print` 改为模块日志；
> 手动录音器“正在录音，再按 Enter 结束”是完成操作必需的提示，明确保留。新增测试证明
> VAD 默认内部状态进入日志且不调用 print；VAD 专项 6/6、全量 563/563 通过。尚未做
> FunASR 进度条屏蔽和真实 user/admin 会话走查，`PRESENT-FIX-LEAK-01` 仍未闭环。

> **`PRESENT-ADMISSION-01` 第三刀 AUTO_OK（2026-08-16）**：新增独立
> `IdleNoticeTracker`，把连续 TimeoutError 映射为“首次等待→约60秒→约30秒”三个
> 用户可见阶段；同阶段不重复，检测到新口述后 reset，达到总超时仍由 main 结束会话。
> 时间规则专项 5/5、会话集成 1/1、全量 568/568 通过。尚未真实等待五分钟验收。

> **PRESENT 收口审计补记（用户 2026-08-16）**：新增看板 25–28，防止此前口头审计结论
> 丢失：①`PRESENT-FEEDBACK-REGRESSION-01` 补回启动/唤醒/退出及“零待确认项”明确反馈；
> ②`PRESENT-PUMP-FLUSH-01` 用真正 flush/join 或 in-flight 完成确认替代
> `pending_count == 0` 猜测，作为 TTS/慢 sink 前置；③`PRESENT-EXTENSION-SEAMS-01`
> 固定 QUERY/DENY/WARNING/导出走结构化 projection→Intent，并定义 WARNING 抢占规则；
> ④`PRESENT-LEGACY-MESSAGE-CLEANUP-01` 删除旧 PresentationMessage 双轨。

> **PRESENT 当前范围起初固定为 12 项（用户 2026-08-16）**：任务清单 3.1A 新增统一收口表，
> 覆盖呈现准入、必要反馈、pump flush、旧消息清理、泄漏、no_action、扩展接缝、
> user/admin、文案一致、最终真实验收、回答编号提示、事件提示音；新增缺失的独立验收任务
> `PRESENT-FINAL-UX-VERIFY-01`。推进时以该表为 PRESENT 当前统一入口，不再从旧 H2 表重复计数。

> **SUMMARY 命名盘点（用户 2026-08-16）**：当前 PRESENT 枚举
> 原 `MessageKind.SESSION_SUMMARY` 的生产直接引用仅为枚举定义、copy 文案分派、main 结束投递；
> 它实际只是即时收尾回执。后续 `LLM-10` 已正式规划领域 `SessionSummary`（步骤/观察/异常/
> 遗留问题），`SESSION-02/EXPORT-01` 又以 `SessionRecord` 为聚合和导出来源，继续同名会造成
> 显示回执与正式内容总结混淆。已登记 `PRESENT-CLOSING-NAME-01`：改为
> `SESSION_CLOSING_SUMMARY` 或等效明确命名；作为清单第13项，但不扩大为新总结链路。

> **记录预览决策（用户 2026-08-16）**：新增 `PRESENT-RECORD-PREVIEW-01`，收口清单
> 在收尾命名成为第13项后，再由13项更新为14项。普通 user 不再以原始 ASR 作为主输出，改为显示系统最终采纳的
> `accepted_analysis.events[].normalized_text`，例如“已记录实验步骤2：将溶液加热至60℃”；
> 原始 ASR 必须继续持久化，并在 admin/debug 或按需详情可查。实施分 A 对照透传、B 隐藏
> user TRANSCRIPT、C 真实语音验收三步；不启用当前统一 Prompt 明确为 null 的
> `assistant_reply`，不增加第二次 LLM 调用。

> **PRESENT 交付链路架构决策（用户 2026-08-16）**：新增
> `PRESENT-DELIVERY-BOUNDARY-01`，收口清单由14项更新为15项。用户不排斥统一链路，反对的是
> 没有现实需求支撑的过度抽象。现在固定结构化结果→projection→`PresentationIntent`→
> Coordinator→Pump→Renderer→Sink 的唯一交付合同：Coordinator 只管排序/去重/生命周期，
> Pump 只执行交付并报告 complete/fail，Renderer 只做纯格式化，Sink 是唯一 I/O；普通新消息
> 不应修改 Coordinator/Pump。未来采用渐进扩展：QUERY/DENY/导出状态随业务增加 projection/copy；
> WARNING 首次真实接入前补最小调度规则；TTS/Web 等第二真实渠道接入前再安排有限架构子步，
> 根据真实交付语义提取 DeliveryPlan/Renderer 协议，不提前建设通用多渠道框架。每个大阶段结束
> 做轻量收口，并以直接 print 泄漏、FIFO、in-flight flush、Renderer 无 I/O 等测试守住边界。

软问题（显示/话术/误识别，与 PRESENT 并行、不阻塞）：`SYNC-UI-CLAIMS-01` 改文案、`GAPS-FIX-ANSWER-HINT-01` 编号提示、UX 系列、`ASR-CMD-02-POSTPROCESS-01`（等组长定演示领域后重启采集接入）。

> 原待办：①`INTENT-02-CLEANUP-NAMING-01` 去影子命名（纯机械改名）；②`ASR-ROBUSTNESS-RULE-GAPS-01/02` 各项缺口定案——已并入上面第 3/6 项。

> **GAPS 收尾验收方式（用户 2026-08-14 拍板）**：GAPS 修复完成后做**轻量检查**——聚焦行为正确性（结束语不崩/暂缓生效/回答编号提示出现且内容对），用现有工具（`verify_session_context`、JSONL 计数、真实会话）+ 九维表轻量对照（只看 GAPS 触及维度：维3/维6 的行为部分）；不追求输出美化（留给 PRESENT）。**UX-FIX-TONE-01 提示音已顺延到 PRESENT-INTEGRATE-01 之后做**（触发点挂消息链路，输出层只动一次避免返工）。
>
> **PRESENT 与 GAPS 返工风险评估（用户 2026-08-14 反向提问后记录）**：GAPS 修核心层（判断/状态机），PRESENT 修输出层（展示）——职责边界按 `OUTPUT_PRESENTATION_POLICY.md` 第 9 节画死（PRESENT 不识别命令、不改待确认状态），数据流单向，故 PRESENT 不会推翻 GAPS 行为逻辑。唯一风险：PRESENT 重构 main.py 时误伤 GAPS 判断顺序——防护 = PRESENT 后全量测试 + 真实会话回归 + 对照基线会话 `20260814_174441` 行为证据。ANSWER-HINT 提示在 PRESENT 时从散落 print **迁移**到消息链路（迁移非返工，行为判据在轻量检查时记录）。
>
> **推进闸门（用户 2026-08-14 最终决策）**：硬问题（崩溃/数据丢错/核心交互失败，判定标准见任务清单第 1 节"硬问题 vs 软问题"）修完即进 PRESENT，**不设固定日期**（进展快于计划则提前）；软问题（显示/话术/误识别但语义兜底/边缘表达）与 PRESENT 并行、出现即修。**历史教训**：过去把软问题（显示矛盾/双句号/降级无人话/误识别）也标成必修，导致 PRESENT 无限推迟——今后真实验收暴露问题必须先过硬/软判据再定优先级，不得"发现即必修"。

> 说明（2026-08-14）：`INTENT-02-ASR-ROBUSTNESS-01` 因用户直接要求**提前执行完毕**（只建评测体系、不改代码），其发现的 7 个缺口已登记 `ASR-ROBUSTNESS-RULE-GAPS-01` 待定案。这两项都不改变 NAMING-01 的 P0 顺序。

真实会话核验工具：`.\.venv\Scripts\python.exe -B -m scripts.verify_session_context <session_id>`（输出 ASR 段数、事件数、预期上下文计数）。

## 3. 后续固定顺序

```text
MAIN-SESSION-CONTEXT-01（REAL_OK）
→ MAIN-RUNTIME-HARDEN-01
→ INTENT-02-CLEANUP-FLAGS/SUBMIT/COMMAND/NAMING/VERIFY
→ Query / Safety / Knowledge 类型合同
→ QUERY 第四分支与只读分派
→ PRESENT 稳定后接真实安全规则、设备查询和 RAG
```

为什么这样排：当前系统首先要保证配置合法、原始证据先于状态变化、会话上下文不断链；
随后删除双轨代码。否则未来查询、安全和 RAG 会复制当前过渡层的错误边界。

## 4. main 已知风险

| 优先级 | 风险 | 期望修复 |
|---|---|---|
| `P0` | execute flag 可在 observer 未创建时开启 | **已修（2026-08-14）**：两个 shadow flag 已随 CLEANUP-FLAGS-01 删除，配置校验函数一并移除 |
| `P0` | `ClarificationExecutor` 可能先改协调器，main 后写 ASR | 统一采用 prepare → persist → commit |
| `P0` | 新链 observe 未传 `recent_context`、事件落盘后未更新 `SessionContext` | **已修（2026-08-14，REAL_OK）**：observe 传 `as_prompt_context()` 快照；事件落盘成功后 `add_analysis`；会话 20260814_092200 复验通过 |
| `P1` | `experiment_segment_count` 在确认实验分析前加一 | **已修（2026-08-14，REAL_OK）**：`is_experiment_evidence` 判定，只统计实验/降级证据段；会话 20260814_093515 复验通过 |
| `P1` | 持续唤醒错误立即重试 | **已修（2026-08-14）**：`src/core/retry.py` 指数退避 1→2→4→8→10s 封顶，成功重置，Ctrl+C 不受影响 |
| `P2` | Answer 执行器有重复 `if not supplied_fields` | **已修（2026-08-14）**：删除不可达重复分支 |
| `P1` | 统一链识别到 review 时无查看结果输出（只显示"已保存"） | `INTENT-02-REVIEW-OUTPUT-01`：review 动作显示待确认列表或"没有待确认问题"；随 `CLEANUP-COMMAND-01` 删旧门卫时把显示职责搬进新链 |

## 5. 恢复命令

```powershell
cd C:\Users\dahli\Desktop\asr_demo

.\.venv\Scripts\python.exe --version

.\.venv\Scripts\python.exe -B -c `
  "import dotenv, sherpa_onnx, sounddevice, soundfile, funasr, modelscope, torch; import src.main; print('IMPORTS_AND_MAIN_OK')"

.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v

git status --short
git diff --check
```

受限沙箱中的 `Access denied` 不等于虚拟环境损坏。先在获准执行边界中验证解释器，
不要直接删除 `.venv`，也不要用 Python 3.14 加载 Python 3.11 的二进制依赖。

## 6. 真实验收门槛

修改涉及 `main.py`、麦克风、真实 ASR/LLM、存储或状态提交时：

1. 先通过单元和集成测试；
2. 说明真实输入、数据外发范围和成功/失败标准；
3. 获得本轮明确授权后再启动真实设备或外部 LLM；
4. 记录 session_id、终端证据和 JSONL 数量；
5. 更新任务清单、学习日志和本交接文件。

下一次真实连续会话至少覆盖：实验、CREATE、ANSWER、REVIEW、DEFER、结束命令，
并验证 ASR/事件证据顺序和最终 SessionContext 数量。

`MAIN-SESSION-CONTEXT-01` 的专门复验标准：**已完成（2026-08-14，会话 20260814_092200）**
- 至少 2 段普通实验口述（第二段依赖第一段内容，如"先加缓冲液"→"加热到六十度"）：✅ 2 段；
- 结束时终端打印"最终上下文包含 N 条事件"，N 必须等于各段已落盘事件总数（修复前为 0）：✅ N=2=事件数；
- 结束命令不进入分段；ASR/事件 JSONL 数量与显示一致：✅ 3 录音文件仅 2 条 ASR 记录；
- 附加证据：第 2 段 prompt_tokens 959→971（cached 896 不变），前文上下文条目确实进入提示词。

## 7. 数据与 Git 边界

- `.env`：本机密钥和配置，不提交。
- `audio/recordings/`、`results/`：真实数据，不提交。
- `.venv*`、模型缓存：不提交。
- 当前目标分支：`codex/asr-demo-unified-understanding`。
- 未经用户明确要求，不提交、不推送、不创建 PR。
- 当前工作区已有累计修改，只处理本轮范围，不清理用户其他改动。

## 8. 2026-08-16 PRESENT END_ONLY 停靠点

- `PRESENT-ADMISSION-01` 四刀已 `AUTO_OK`：结束阶段改为唯一结构化
  `SESSION_CLOSING_SUMMARY` Intent，一次性显示实验步骤数和待确认明细。
- `PRESENT-CLOSING-NAME-01` 已 `AUTO_OK`：旧 `SESSION_SUMMARY` 已无兼容别名地迁移为
  `SESSION_CLOSING_SUMMARY`；未引入正式 LLM SessionSummary、SessionRecord 或导出。
- 零待确认时明确显示“没有待确认问题”；有待确认时在同一摘要块列出编号、
  状态和问题，不再另发最终 `CLARIFICATION_REVIEW`。
- 删除旧“提交 M 段实验口述”内部术语；不引入正式 `SessionSummary`、额外 LLM
  或导出逻辑。
- 专项 41/41、全量 571/571 通过；未做真实麦克风 UX 验收，状态不升为
  `REAL_OK`/`UX_CONFIRMED`。
- **当前唯一下一项**：`PRESENT-FEEDBACK-REGRESSION-01`，补回 user 可见的启动、
  唤醒成功和用户主动退出反馈，全部走统一 PRESENT 链路。

## 9. 2026-08-16 PRESENT 程序级反馈停靠点

- `PRESENT-FEEDBACK-REGRESSION-01` 已 `AUTO_OK`：新增结构化 `PROGRAM_STATUS`
  （starting/ready/exited），`WAKE_ACK` 改为携带 `keyword` 的结构化合同。
- pump 生命周期从单会话上移到整个程序；启动、就绪、唤醒、会话内消息和退出
  共用一个 Coordinator/Pump，没有第二个生产 stdout 出口。
- Ctrl+C 在模型加载期间或待机/会话期间都能投递“已退出”反馈。
- 程序状态与唤醒结果均有独立 projection→Intent 合同；专项 56/56、全量 578/578 通过。
  未做真实麦克风 UX 验收，仍不标
  `REAL_OK`/`UX_CONFIRMED`。
- **当前唯一下一项**：`PRESENT-PUMP-FLUSH-01`，用真正的 pending + in-flight
  完成确认取代 `pending_count == 0` 猜测，确保慢 sink 不丢尾消息。

## 10. 2026-08-16 PRESENT pump flush 停靠点

- `PRESENT-PUMP-FLUSH-01` 已 `AUTO_OK`：Coordinator 以原子 unfinished 计数统一覆盖
  pending、deferred 与已取走但仍在 renderer/output 中的 in-flight 消息。
- `PresentationPump.flush(timeout)` 只有在所有已提交消息真正完成输出后返回 `True`；
  超时返回 `False`，renderer/output 失败则抛出含 intent id、错误类型和原因的
  `PresentationDeliveryError`。
- 单条消息失败不会杀死 pump；失败被记录后，后续消息继续交付。语义去重丢弃项会正确
  扣减 unfinished，deferred 项继续保留未完成所有权。
- 会话收尾和程序退出已移除 `pending_count == 0` 轮询，统一先 flush、显式记录失败或超时，
  再停止自己拥有的 pump。
- 专项 24/24、全量 584/584 通过；未使用真实麦克风，不标 `REAL_OK`/`UX_CONFIRMED`。
- **当前唯一下一项**：`PRESENT-LEGACY-MESSAGE-CLEANUP-01`，删除旧
  `PresentationMessage`、专属 channel/status/speech policy 与旧合同测试，不保留双轨兼容。

## 11. 2026-08-16 PRESENT 旧消息双轨清理停靠点

- `PRESENT-LEGACY-MESSAGE-CLEANUP-01` 已 `AUTO_OK`。
- `MessageKind`、`MessagePriority`、`ScreenTarget` 三个现役语义枚举已归位到
  `src/core/presentation_intent.py`；所有生产与测试 import 均从 Intent 模块取得。
- 删除 `src/core/presentation_message.py`、`tests/test_presentation_message.py`，以及只属于旧模型的
  `PresentationMessage`、`DeliveryChannel`、`MessageStatus`、`SpeechPolicy`、
  `VoiceDeliveryPolicy`；无兼容文件、别名或导出。
- `src/tests` 对上述旧符号及模块的引用为 0。专项 86/86 通过；全量从 584 变为 574，
  恰好减少被删除的 10 项旧合同测试，其余 574/574 全绿。
- 本轮只改变代码归属和删除废弃模型，没有改变用户文案或交互，不新增真实 UX 状态。
- **当前唯一下一项**：`PRESENT-FIX-LEAK-01`，清理 user 屏幕上的 recorder/VAD/wakeword
  与第三方模型开发输出，并做真实 user 模式无泄漏确认。

## 12. 2026-08-16 PRESENT 开发输出泄漏停靠点

- `PRESENT-FIX-LEAK-01` 已 `AUTO_OK`：主程序涉及的 recorder、VAD、wakeword、ASR、
  state、LLM 和 main 模块均无直接 `print()`；项目内部状态统一进入 logging。
- SenseVoice/FunASR 在 `AutoModel` 初始化与每次 `generate` 时都显式设置
  `disable_pbar=True`、`disable_log=True`，不采用进程级 stdout/stderr 重定向，避免并发时吞掉
  Pump 的合法用户输出。
- 新增 AST 架构护栏，只检查生产运行模块；独立 VAD/唤醒诊断脚本和结果查看工具仍可主动打印。
- 专项 16/16、全量 575/575 通过。未启动真实模型与麦克风，真实 user 屏幕零泄漏复核
  并入 `PRESENT-FINAL-UX-VERIFY-01`，本轮不标 `REAL_OK`/`UX_CONFIRMED`。
- **当前唯一下一项**：`PRESENT-NOACTION-FEEDBACK-01`，让问题编号不存在、无目标回答、
  无法暂缓/弃权等 no_action 场景不再沉默。

### 12.1 真实会话 20260816_141745 修正

- 功能链通过：两步记录、追问、review、指定回答、自然结束确认、END_ONLY 摘要与退出反馈均正确。
- 启动泄漏未通过：出现 FunASR 版本检查、ModelScope 两组仓库检查/下载日志与 tqdm；说明
  `disable_pbar/disable_log` 只覆盖 FunASR 推理层，没有覆盖更新检查和下载层。
- 已补 `disable_update=True`、初始化前 `TQDM_DISABLE=1`、ModelScope 下载 logger 降噪；
  READY 文案补“按 Ctrl+C 可以退出程序”。专项49/49、全量576/576通过。
- 需要一次最短二次启动复验：只观察 starting→ready，确认零第三方行且 READY 含 Ctrl+C 后即可退出；
  通过后 `PRESENT-FIX-LEAK-01` 升 `REAL_OK`。

### 12.2 真实会话 20260816_142352 再修正

- 下载日志、两个进度条和更新联网提示已经消失，证明 `disable_update`、`TQDM_DISABLE` 与 logger
  降噪有效；仅残留 `funasr version: 1.4.1.`。
- 精确定位到 FunASR 1.4.1 `utils/version_checker.py`：它先 print 版本，再检查 `disable`。
  创建 AutoModel 前只将该 `check_for_update` 入口替换为空操作，不做进程输出重定向。
- 用户确认会话结束后应可再次唤醒；新增 `ProgramStatus.WAITING`，正常会话返回后显示
  “已返回待机，可再次说小科小科开始新会话；按 Ctrl+C 退出”。
- 专项63/63、全量576/576通过。下一次真实复验需覆盖零版本横幅、WAITING 和第二次唤醒。

### 12.3 真实会话 20260816_142945 最终结论

- `PRESENT-FIX-LEAK-01` 升为 `REAL_OK`。
- starting→ready 之间无 FunASR 版本、更新、ModelScope 下载日志或进度条；整轮无模型路径、
  RTF、音频时长/保存路径、识别耗时或 token 泄漏。
- READY 正确提示 Ctrl+C；会话结束摘要后 WAITING 明确提示可再次唤醒；Ctrl+C 后 EXITED
  完整交付，三者顺序和含义正确。
- 本轮 WAITING 后直接 Ctrl+C，未实际发起第二次唤醒；自动集成已覆盖循环返回，真实双会话
  复验留到 `PRESENT-FINAL-UX-VERIFY-01`，不阻塞泄漏任务。
- 当前唯一下一项保持 `PRESENT-NOACTION-FEEDBACK-01`。

### 12.4 双会话复验 20260816_143151 → 20260816_143201

- 同一进程第一轮零步骤结束，WAITING 后再次唤醒成功，第二轮生成新 session_id；最后再次
  WAITING，再由 Ctrl+C 交付 EXITED。再次唤醒与程序级 Coordinator/Pump 生命周期真实通过。
- 两轮均无 FunASR/ModelScope、路径、进度条、RTF、耗时或 token 泄漏，巩固 FIX-LEAK REAL_OK。
- 复现下一项证据：“制业枪”后只有 ASR，无业务处理反馈，归入
  `PRESENT-NOACTION-FEEDBACK-01`。
- 根因确认并将原登记更正为 `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01`：ASR完整保留
  “是的，是一夜枪，体积为50毫升”，该段没有LLM调用；确定性命令因句首“是的”走
  AFFIRM→CONFIRM，只清确认标志、不提取体积，确认记录仍缺 amount_value/amount_unit。
  这是程序复合意图执行缺陷，文案误导只是后果。

## 13. 2026-08-16 PRESENT 剩余施工顺序重排（用户确认）

此前交接记录中的“当前唯一下一项”是各轮结束时的历史停靠点，不再代表当前顺序。
从本节起，PRESENT 剩余工作严格按以下顺序推进：

1. `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01`：P0 复合确认+回答不能丢字段；
2. `PRESENT-NOACTION-FEEDBACK-01`：NOACTION 容错反馈；
3. `UX-MODE-01`：user/admin 输出分层；
4. `SYNC-UI-CLAIMS-01`：文案与真实状态一致性；
5. `PRESENT-RECORD-PREVIEW-01`：规范记录预览；
6. `PRESENT-DELIVERY-BOUNDARY-01`：Delivery Boundary 架构护栏；
7. `PRESENT-EXTENSION-SEAMS-01`：QUERY/DENY/WARNING/导出扩展接缝；
8. `GAPS-FIX-ANSWER-HINT-01`：回答编号提示；
9. `UX-FIX-TONE-01`：事件提示音；
10. `PRESENT-FINAL-UX-VERIFY-01`：最终双模式真实 UX 验收。

**当前唯一下一项**：`CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01`。先修数据正确性，确保
同一句中的确认和实体回答都被执行、字段不丢，再处理 NOACTION 和后续呈现体验；未经用户重新
确认不得跳项。

---

## 合并补充：protocol / TTS / 危化品三层（2026-08-14）

以下内容来自与主线并行开发的分支，合并时以主线记录为基底，本节仅补充主线未覆盖的部分。

最后整理：2026-08-12
`PROTOCOL-INTEGRATION-01`：把实验方案接入会话级状态，仍不修改主流程业务规则。
具体是：会话开始时记录已选方案与当前步骤，普通实验记录经实体结构化后调用
`compute_missing_fields`，把确定性缺失字段送入现有追问采用链；选择结果为自由
模式（`None`）时，必须完整保留现在的无方案自由记录行为。
最后才在 `src/main.py` 做最薄的一层依赖连接。
`PROTOCOL-01` 语义修正已完成并达到 AUTO_OK：95项专项、全量517项通过。旧链重复问题、LLM偶发
abstention和启动慢仍是已知问题，本轮没有顺手处理。
## 2. 可复现基线
- 真实项目：`C:\Users\dahli\Desktop\asr_demo`（已拆平，无 asr_demo/ 嵌套）
- 正式解释器：`.venv` 中的 Python 3.11.9
- 全量自动测试：`535 tests OK`（项目 `.venv`，2026-08-12；本轮新增17项TTS纯逻辑测试）
- 当前 Git 分支：`codex/asr-demo-unified-understanding`
- 当前远程：`total = https://github.com/diw35688-sketch/ai107.git`
- 工作区有未提交改动；本轮明确不提交、不推送。`src/core/unified_understanding.py`、`src/llm/unified_processor.py`和`scripts/demo_offline_session.py`为本轮开始前已有改动，未回滚或覆盖。
### 采用合同
- 实验候选经过来源、原文、目标、权限和降级形状检查后，才生成不可变规范快照。
- 待确认动作被建模为 create/review/defer/answer/confirm/reject_suggestion/no_action。
- PREPARE_CREATE/PREPARE_UPDATE 只表示准备动作，没有 commit 方法。
- LLM 中风险状态候选不能直接修改问题；降级 NOTE 不能制造正式问题。
### 实验方案与确定性缺失字段
- `ProtocolStep`和`ExperimentProtocol`使用frozen dataclass，并由`ProtocolError`统一承接非法输入。
- 正式字段是`protocol_values`（方案目标值，永不追问）和`must_record`（现场实测值，缺失才追问）；旧`required_fields`/`expected_values`仅作为读取兼容别名。
- `SourcedFieldValue`与`FieldValueSource`保存`SPOKEN`、`PROTOCOL_DEFAULT`、`DEVIATION`来源；默认值不覆盖学生原始值。
- `ProtocolStore`严格读取新JSON字段，拒绝未知/缺失字段、版本不符、重复ID、文件缺失和损坏JSON；上一轮临时旧数据保留读取兼容。
- `compute_missing_fields`只比较`must_record`，按字段原顺序稳定输出，不调用LLM、不做IO。
- `detect_protocol_deviations`只做字符串级比较，不做单位归一化或数值换算；例如`60℃`与`60摄氏度`暂判为不一致。
- `ProtocolStepCursor`是不可变显式游标，仅支持`next`/`prev`/`jump_to`，越界明确报错，不做LLM步骤对齐。
- `data/protocols/undergraduate_basic_protocols.json`中的3份本科方案已按“方案已定/现场必测”重写。
- 本轮未修改`main.py`、`InteractionCommandType`，未接LLM/ASR/OCR/上传，也未改现有统一理解合同。
### main影子模式
- `UNIFIED_SHADOW_ENABLED` 默认 false；本机 `.env` 当前为真实测试临时开启状态，提交时 `.env` 不进入 Git。
- 影子链读取同一最终 ASR 证据和只读待确认快照。
- 影子摘要只显示目标、权限、采用类型、缺失字段、追问标志和动作类型。
- 影子不写业务文件、不改 SessionContext/ReplyCoordinator、不发 TTS；异常只产生失败摘要，旧流程继续。
## 4. 最近真实验收
### 影子会话：Prompt缺失字段 + 执行器验证
- 会话：`20260811_103134`（1段实验口述"将溶液加热。"+ 结束命令）
- 影子输出：`目标=experiment_pipeline, 缺失字段=('temperature','duration'), 需要追问=True, 待确认动作=create；未执行`
- 旧流程：正常创建追问问题1，终端显示"请问加热的目标温度是多少？需要加热多长时间？"
- 结论：新旧链对"将溶液加热"的判断完全一致，新链的施工单正确产出但未执行（影子隔离生效）。
### Prompt缺失字段能力修复 + 项目拆平
- 统一Prompt实验规则新增一行，与旧ANALYSIS_SYSTEM_PROMPT第4条规则一致。
- 真实DeepSeek以独立脚本复验"将溶液加热。"：missing_fields=['temperature','duration']、1次成功2.32秒。
- 项目拆平：消除asr_demo/嵌套，消除路径断裂问题（.env、models、测试命令全部简化）。
- 推送到total/codex/asr-demo-unified-understanding。
### main影子接入
- 会话：`20260810_120209`
- 前3段真实进入 experiment_pipeline/structured_experiment，影子明确“未执行”。
- 结束候选进入旁路未开放目标后安全失败，旧流程继续，证明失败隔离。
### 结束命令单一来源
- 真实问题：“接受实验记录。😔”被旧 main 当作 NOTE。
- 已删除 main 独立结束字典/正则，统一委托 `InteractionCommandParser`。
- 修改后短真实会话中，ASR业务记录保持186条、事件保持133条，结束口述没有进入分段、LLM或存储。
- 状态：`REAL_OK`。
### 新旧追问差异
- 会话：`20260810_180242`
- 真实 ASR：”将溶液加热。”
- 旧链：`missing_fields=[temperature, duration]`，生成追问。
- 新统一链及保存证据重放：`missing_fields=()`、`follow_up_required=False`、`no_action`。
- 根因不是合同矛盾：统一 Prompt 缺少”何时登记缺失字段”的业务能力规则。
### 统一Prompt缺失字段能力修复
- 修改：`unified_prompts.py` 实验规则新增一行，与旧 `ANALYSIS_SYSTEM_PROMPT` 第4条规则文字一致。
- 真实 DeepSeek 复验”将溶液加热。”：`missing_fields=['temperature','duration']`、`should_ask_follow_up=True`、`follow_up_question=”加热到什么温度？需要加热多长时间？”`、降级=False、1次成功2.32秒。
- 状态：`REAL_OK`。
## 5. 当前工作区构成
累计修改大致分为：
src/asr/              后端抽象与证据schema
src/core/             统一理解、分派、执行、采用、影子合同
src/llm/              统一Processor与Router
src/evaluation/       控制语料基线与术语后处理对照
scripts/              Fake/真实旁路及评测入口
tests/                每个新增边界的专项和集成测试
docs/                 任务清单、交接和学习记录
本机数据边界：
- `.env`：忽略，包含本机配置/密钥，不提交。
- `audio/recordings/`：忽略，真实录音不提交。
- `results/`：忽略，真实会话数据不提交。
- `.venv*`、模型下载缓存：忽略，不提交。
- `audio/wav/`：仓库已有固定非敏感测试样本，保持跟踪。
- `evaluation/asr_commands/` 中的计划、人工基线和清单可跟踪；采集尝试与生成报告已忽略。
## 6. 仍未开放的能力
- ClarificationExecutor尚未接入main.py影子位（CREATE/DEFER/CONFIRM只产出施工单，未真实修改协调器）。
- ANSWER施工单不填充实体字段（需LLM从answer_text中提取结构化entities）。
- 自然表达（"我先跳过/可先跳过"）会误入实验管线，需COMMAND-03修复后DEFER才能正常走新链路。
- 实验方案尚未接入会话状态、当前步骤、主流程或追问执行；当前只有稳定合同、读取、选择和纯函数。
- 新统一链尚未接管旧 SegmentProcessor 或真实存储。
- ClarificationAction 尚未提交到 ReplyCoordinator。
- 结束会话副作用尚未通过统一执行器开放；main仍在正式本地Parser命中后直接结束。
- 热词候选模型尚未验证或切换。
- 专业词后处理尚未接入主链。
- Presentation/TTS 尚未接入。
- 未提交、未推送、未创建 PR。
## 7. 提交前整理门
当前分支是 `main`，且累计改动较多。提交到新总仓前必须：
1. 确认目标远程地址，不把改动误推到当前 `origin`。
2. 新建 `codex/` 前缀工作分支，不在 `main` 提交。
3. 复核 `git status --short`，只暂存源码、测试、脚本和文档。
4. 确认 `.env`、录音、结果、模型、虚拟环境没有进入暂存区。
5. 运行 `392+` 全量测试与 `git diff --check`。
6. 按能力边界拆分提交；不要把全部累计修改压成无法审查的一次提交。
7. 推送前检查远程和分支名；未经用户明确要求不提交、不推送。
建议提交分组：
1. ASR后端抽象＋ASR证据schema v2
2. 控制语料基线＋术语后处理评测
3. 统一理解Prompt/Processor/Router
4. 安全分派＋执行请求合同
5. 实验/待确认采用合同＋集成旁路
6. main影子模式＋结束命令单一来源
7. 任务清单、交接与学习日志
## 8. 教学与真实验收约定
每轮按“目的、技术路线、设计原因、实现功能、本轮知识、验收方法、下一步建议”讲解。
修改触及麦克风、真实 ASR、真实 LLM、持久化或主流程时，自动测试通过后必须主动安排真实环境验收；验收前说明输入、数据外发范围、观察指标和成功/失败标准，验收后用终端、文件计数、会话编号等证据更新状态。历史单次外发授权不能自动扩大。
## 2026-08-12 本轮验收补充
- 全量：`Ran 517 tests ... OK`。相对上一轮501项，新增16项协议语义专项测试。
- 新增模块：`src/core/protocol_cursor.py`、`src/core/protocol_deviations.py`；来源值结构位于`src/core/protocol.py`。
- 禁止误读：本轮只有纯数据结构和纯函数，不代表方案已接入会话状态或主流程；下一轮仍需显式接线。
## 2026-08-12 旧语义兼容层清除
- 上一轮为保住旧测试保留了 `required_fields`/`expected_values` 到新字段的迁移兼容层，
  实测发现它把已判定为错误的行为原样保留（旧写法构造仍会追问方案里写死的值），本轮彻底删除。
  `ProtocolStep` 现在只接受 `protocol_values` 和 `must_record`，`ProtocolStore` 同步删除旧字段读取兼容。
- 约 28 处使用旧字段的测试**逐个按新语义改写**，不是删除；每条原有校验意图都有新测试接住，
  并新增 `test_protocol_values_are_not_missing_even_when_unprovided` 锁住修正后的语义。
- 验收：项目 `.venv` 跑 `python -B -m unittest discover`，518 项全部通过。
- 全库确认 `src/` 与 `tests/` 中不再出现 `required_fields` / `expected_values`。
- 本轮未改 `src/main.py`、未改 `InteractionCommandType`、未接主流程、未调用 LLM，也未提交或推送。
- **教训**：语义变更时，"保持所有旧测试全绿"是有害约束。旧测试若编码了已被判定为错误的语义，
  正确做法是改写测试，而不是加兼容层保护错误行为。
## 2026-08-12：可打断TTS纯逻辑地基
### 已完成
- 新增`CancelScope`：32位代数计数器，提供`generation`、`cancel()`、`is_stale()`、`new_response()`和`reset()`。
- 新增`TTSBackend`：`runtime_checkable Protocol`，要求后端按块生成`int16`单声道NumPy音频。
- 新增`InterruptibleTTSPlayer`和`TTSPlaybackResult`：每块播放前检查取消，完成/取消/失败均返回不可变结果；后端和sink异常不冒泡。
- 新增`NullTTSBackend`与`create_tts_backend()`：当前只支持`null`，使用集中配置的`TTS_BACKEND`和`SAMPLE_RATE`。
- 配置新增`TTS_BACKEND=null`、`TTS_ENABLED=false`；`.env.example`已同步。
### 验收证据
- TTS专项：17项通过。
- 全量：`Ran 535 tests ... OK`。
- 语法编译：新增TTS模块、配置和测试均通过`py_compile`。
- `git diff --check`通过。
- UTF-8自检：`.env.example`、`src/config.py`、5个TTS源码文件和`tests/test_tts.py`均可用无BOM UTF-8读回，中文字符未损坏。
### 下一轮注意
本轮没有真实TTS、没有`OutputStream`、没有模型下载、没有声卡操作、没有`main.py`或`InteractionCommandType`改动；不能把本轮`AUTO_OK`解释成真实播放已验收。接入真实设备前，需要先确定半双工策略、`AssistantState.SPEAKING`生命周期、用户打断入口以及真实sink的线程/资源释放规则。
## 2026-08-13：PROTOCOL-INTEGRATION-01 会话级方案状态
### 本轮已完成
- 新增 `src/core/protocol_session.py` 的 `ProtocolSessionState`：不可变会话级方案状态，自由模式下 `cursor=None`；
  `next/prev/jump_to/current_step` 在自由模式下均有明确定义的行为，不抛异常。
- 新增 `src/core/protocol_segment_evaluation.py` 的 `evaluate_segment(state, entities)`：纯函数适配器，
  把缺失字段、偏差、带来源的字段值汇聚成 `SegmentEvaluation`，供追问链直接消费。
- `ProtocolStep` 新增 `field_prompts`（字段缺失时的追问话术）；`ProtocolStore` 支持读取该字段。
  强校验：key 必须属于实体白名单，且**必须同时出现在 `must_record` 里**——给 `protocol_values`
  配追问话术是语义矛盾，构造阶段直接拒绝。
- 新增 `scripts/demo_protocol_session.py` 离线演示，运行方式：
  `$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -B scripts\demo_protocol_session.py`
- 测试基线从 535 项增至 553 项，`.\.venv\Scripts\python.exe -B -m unittest discover` 全部通过。
### 下一轮接线要点
下一轮做最薄的追问链连接：从 `ProtocolSessionState` 取当前步骤，调 `evaluate_segment`，
当 `follow_up_required=True` 时调用现有 `ReplyCoordinator.register_clarification`
（参数为 `segment_id / raw_text / question / missing_fields / requires_confirmation / clarification_id_prefix`）。
偏差走独立确认路径，不复用缺失字段追问。仍然最后才在 `main.py` 做入口层薄连接。
### 本轮故意未做
未改 `src/main.py`，未接 TTS / ASR / LLM，未改 `InteractionCommandType`，未做真实设备验收，未提交未推送。
## 2026-08-16：手机端 Card Flow 骨架（MOCK 原型）
### 本轮已完成
- 新增移动端原型三件套：`web/frontend/mobile.html`（骨架）、`mobile.css`（竖屏卡片样式 + 滑入滑出动画 + 四态配色）、`mobile_cards.js`（5 步 mock、applyState 统一入口、触摸手势、DEV 调试按钮）。
- 页面地址：本机 `http://127.0.0.1:8000/static/mobile.html`；真手机同 WiFi 经 `/phone` 页扫码或直接访问局域网地址的该路径。
- PC 页面零改动：首页 `/` 返回 200，字节数与改动前一致（17453）；git 工作区仅新增上述三文件，未提交未推送。
### 验收证据
- HTTP：`/`、`/static/mobile.html`、`/static/mobile.css`、`/static/mobile_cards.js` 全部 200，Content-Type 正确。
- 语法：`node --check` 通过（Node v25.9.0）。
- 后端全量测试任务本轮零 Python 改动，不受影响；该任务运行超 30 分钟仍未结束，属环境异常待查。
### 下一轮注意（等用户 UI 确认后）
- 正式完成判定放后端：结合协议步骤的 required_fields / completion_condition 等确定性条件设计，不允许 LLM 或前端仅凭一句"好了"推进步骤。
- 前端接线样板：`/protocols/session/steps` 返回 → 映射为 Card 形状（step/total_steps/title/instruction/description/warning/status/image/params）→ `applyState()`；status 字段需后端补充。
- iOS Safari 不支持 Web Speech API：手机端语音方案需重新评估（浏览器 ASR 不可用 / SenseVoice 服务端）。
### 本轮故意未做
未接真实 Protocol、ASR、TTS；未改真实实验流程；未改 PC 端任何文件；未提交未推送未部署。
## 2026-08-16：手机端接入真实浏览器语音识别
### 本轮已完成
- 新增 `web/frontend/mobile_voice.js`：Web Speech API（zh-CN）真实识别；中间结果实时显示；错误码中文映射；iOS 不支持时给出提示。
- `mobile.html` 增加"听到：…"转写行并加载新脚本；`mobile_cards.js` 删除假聆听占位、导出 `setVoice`；`mobile.css` 补转写行样式。
- 边界：识别文本只显示、不推进步骤；跳步仍只走 DEV 按钮。
### 验收证据
- `node --check` 两个 JS 均通过；`/static/mobile_voice.js` 200；PC 首页 `/` 17453 字节零改动。
- 真实麦克风验收需用户在 Chrome 实测（权限弹窗 → 说话 → 看转写行）。
### 下一轮注意
- 真机语音需要 HTTPS（非 localhost 浏览器才给麦克风权限）：用 `scripts/start_phone_server.py` 局域网 HTTPS 模式。
- iPhone Safari 无 Web Speech API：iOS 语音方案 = 服务端 SenseVoice（模型未下载，需单独一轮）。
- 下一步主线不变：后端确定性完成判定（required_fields / completion_condition）+ Card 数据接口，前端 mock 换真实数据。
### 本轮故意未做
未让语音文本驱动步骤；未接后端；未改 PC；未提交未推送未部署。
## 2026-08-16：移动端卡面视觉改版
### 本轮已完成
- 卡面重设计：核心操作改左侧色条+深蓝大字；状态徽章改圆点+文字（running 只闪圆点）；参数改两列浅灰小卡；警告改左琥珀色条；顶部进度线改底部分段条；卡片微渐变底；页面背景微渐变。
- 仅改 `mobile_cards.js`（cardHtml 结构）与 `mobile.css`（样式）；PC 零改动。
### 验收证据
- `node --check` 通过；CSS/JS 均 200；PC 首页 17453 字节不变。
- 视觉裁决权在用户：Chrome 模拟器刷新 `http://127.0.0.1:8000/static/mobile.html` 查看。
### 下一轮注意
主线不变：后端确定性完成判定 + Card 数据接口。若用户对卡面还有具体不满，继续在 mobile.css 层迭代，不涉及业务逻辑。
## 2026-08-16：卡面主题自定义
### 本轮已完成
- 卡面 4 套预设主题（晨雾蓝/午夜深蓝/极简白/暖沙）：DEV 面板一键切换，localStorage 记住选择。
- 实现：CSS 变量换肤（15 个 --card-* 变量），主题类挂 `.m-shell`（卡片重建不丢主题）。
### 验收证据
- `node --check` 通过；三文件均 200；PC 首页 17453 字节不变。
- 用户验收路径：`http://127.0.0.1:8000/static/mobile.html` → DEV 面板「卡面主题」。
### 下一轮注意
- 若用户想要"自定义图片背景"（照片/插画），可复用 Card 规格里已有的 image 字段：后端/数据层提供图片地址，`.m-card` 加背景图 + 遮罩保证文字可读。
- 主线不变：后端确定性完成判定 + Card 数据接口。
## 2026-08-16：新增「怪盗扑克」卡面主题
### 本轮已完成
- 第 5 套主题「怪盗扑克」：象牙白卡纸、藏青墨、基德红、双层描边、中心淡黑桃水印、右下角 180° 镜像牌角、左上竖排牌角（衬线大数字+黑桃+总数）、衬线标题、油墨印章状态徽章。
- 仍走 CSS 变量换肤框架；镜像牌角用 content:attr(data-step) 纯 CSS 实现。
### 验收证据
- `node --check` 通过；CSS/JS 均 200；PC 首页 17453 字节不变。
- 用户验收：DEV 面板「卡面主题」选「怪盗扑克」，重点看牌角、水印、红黑对比。
### 下一轮注意
- 卡面主题已 5 套，视觉迭代可暂告一段落；回到主线：后端确定性完成判定 + Card 数据接口。
## 2026-08-16：卡面背景图上传
### 本轮已完成
- DEV 面板支持选择本地图片作卡面背景：自动压缩（1200px/JPEG0.82）、按主题薄纱遮罩、localStorage 记住、一键清除。
### 验收证据
- `node --check` 通过；三文件均 200；PC 首页 17453 字节不变。
- 用户验收：mobile 页 DEV 面板「卡面背景图」→ 选择图片 → 看文字可读性与压缩后效果。
### 下一轮注意
主线不变：后端确定性完成判定 + Card 数据接口。
## 2026-08-17：确定性步骤状态机（方案 B：完成打勾不自动翻页）
### 本轮已完成
- 新增 `web/step_progress.py` 纯逻辑追踪器；`domain.py`/`lab_tools.py` 接线；`/protocols/session/steps` 每步与当前步输出 `status`（completed/error/waiting_user）。
- 前端：✓ 圆勾、绿色完成段、当前高亮、未到变暗、st-completed/st-error 卡片强调；DEV 按钮改"模拟记录完成（打勾，不翻页）/模拟记录偏差"。
- 测试：新增 8 项全过；接口真实验收通过（选方案→5 步 status=waiting_user→恢复自由模式）。
### 环境注记（重要）
- 本机沙箱对临时目录（Temp\dsh-*）拒绝写入，test_protocol_store 等 23 项测试在 setUp 处 PermissionError——环境性错误，与本轮代码无关；全量基线需沙箱权限升级后重跑（后台任务 pwsh-4）。
### 下一轮注意
- 把移动端 MOCK 换成真实 `/protocols/session/steps` 数据（cardFromProtocolView 映射样板已留）；语音文本 → record_observation 的接线。
- 偏差确认流程（error 状态的消除路径）待设计；PC 端尚未消费 status 字段（有意）。
## 2026-08-17：移动端视觉与状态机交互 UX_CONFIRMED
- 用户实测验收通过：勾 ✓/绿完成段/当前高亮/未到变暗的视觉呈现、方案 B（完成打勾不自动翻页）、DEV 按钮交互，全部确认。
- 移动端当前能力总账：5 步卡片流 + 切换动画与手势；真实浏览器语音识别（转写显示）；5 套卡面主题；背景图上传；确定性 status 渲染（✓/亮/暗）。
- 下一轮唯一主线：移动端接真实 `/protocols/session/steps` 数据 + 语音文本接入 record_observation（让"说一句→真实打勾"闭环）。
## 2026-08-17：移动端真实链路接线完成（待用户实测 LLM 闭环）
### 本轮已完成
- 移动端双数据源（默认真实接口）：轮询 /protocols/session/steps；手势/按钮→/session/move；语音文本→/chat；方案下拉→/protocols。
- Agent 指令补实验步骤规则；全量测试基线重跑。
### 用户实测验收路径
1. 刷新 http://127.0.0.1:8000/static/mobile.html（Chrome，F12 手机模拟）；
2. DEV 面板「实验方案」选一份（如"0.1 mol/L pH 7.4 磷酸缓冲液配制"）；
3. 点底部语音按钮，说第 1 步要求的内容（如"我称了三点五八克"）→ 等 AI 回复 → 卡片应出现 ✓ 或仍等你操作（取决于必测字段是否记齐）；
4. 说"下一步"→ 卡片翻页动画；说"上一步"→ 回退；
5. 失败边界：最后一步上滑应有提示不崩溃。
### 下一轮注意
- 语音回答播报（浏览器 TTS）未接移动端；偏差确认流程未设计；PC 端仍未消费 status（有意）。
## 2026-08-17：修复语音对话失忆与"完成了"追问（待用户复测）
### 本轮已完成
- conversation_id 持久化（localStorage），每次 /chat 带上；DEV 面板可"重置对话记忆"。
- "完成了"改为事实核对：get_current_step 工具返回 status/recorded/missing；Agent 指令规定核对后如实回答、一次只问一个。
- 测试 719/719 OK；服务器已重启加载修复。
### 用户复测路径
1. 刷新 mobile 页（Ctrl+Shift+R），选方案；
2. 说"我称了三点五八克"→ AI 只追问还缺的字段（如果还有）；
3. 补齐后说"完成了"→ AI 应确认完成/或明确说出还缺哪一项，不应机械重复问；
4. 说"下一步"→ 翻页；「重置对话记忆」按钮用于开新上下文。
### 下一轮注意
- 若复测仍有"笨"的表现，把用户原话与 AI 回复原文记录下来（这是调指令/工具的输入）；语音播报、偏差确认、真机 HTTPS 待排期。
## 2026-08-17：横竖屏自由切换适配
### 本轮已完成
- `@media (max-height: 520px)` 紧凑模式：字号留白降档、卡片内滚动兜底、手势让位 ‹ › 按钮、怪盗扑克牌角缩小；竖屏行为不变。
### 用户验收路径
- Chrome 模拟器：`Ctrl+Shift+M` 选 iPhone 后，点设备工具栏的**旋转图标**（↻）在横竖屏间切换；或真手机直接转动机身。
- 横屏应看到：卡片完整（必要时可上下滚动）、‹ 语音 › 按钮可用、DEV 面板不再撑爆。
### 下一轮注意
- 语音播报、偏差确认、真机 HTTPS 待排期；全量测试基线仍为 719/719（本轮零 Python 改动）。
## 2026-08-17：卡片级交互按钮
### 本轮已完成
- 卡片新增「完成本步 ✓」「下一步 ›」两个大按钮；新增只读接口 GET /protocols/session/progress（status/recorded/missing）。
- 完成按钮=查账：未记齐时卡片内红条列出还缺字段；无手点改状态入口。
### 用户验收路径
- 刷新 mobile 页 → 选方案 → 卡片底部两个按钮：点「完成本步」看查账反馈（缺什么列什么）；说/记录完必测数据后再点→确认完成 ✓；点「下一步」翻页。
### 下一轮注意
- 语音播报（TTS）、偏差确认、真机 HTTPS 待排期；全量基线 719/719。
## 2026-08-17：产品化第 1/4 轮——移动端 AI 形象接入
### 本轮已完成
- 手机页顶部形象栏"小科"：复用 PC 5 张立绘，5 状态（待机/聆听/思考/回答/完成）由 setVoice 驱动，横屏自动缩小；静态资源版本号 v=20260817d。
### 用户验收路径
- 刷新 mobile 页：看到小科 → 点语音说话看"聆听脸"→ AI 处理看"思考脸"→ 回答看"说话脸"→ 完成本步看"开心脸"；旋转屏幕看缩小效果。
### 下一轮（产品化第 2/4 轮，等用户确认）
- 任务会话持久化：SQLite 存当前方案/当前步/各步状态，刷新、旋转、重启服务器都不丢进度。
- 第 3 轮：卡片类型化 + POST /session/steps/{n}/complete 显式完成接口；第 4 轮：横屏两栏布局。
## 2026-08-17：产品化第 2/4 轮——任务会话持久化（完成）
### 本轮已完成
- 新增 web/database/session_store.py（三张表）；domain 自动恢复/落盘；/record 同步登记进度；测试 729/729。
- 真实验证：选方案→第 2 步→杀光 python→重启→第 2 步原样恢复（已清理回自由模式）。
### 用户验收路径
- 选方案→推进到某步→刷新页面（进度应在）；说"下一步"后**重启服务器**（或直接告诉我重启）再打开，进度还在。
### 下一轮（第 3/4 轮，等用户确认）
- 卡片类型化（6 类卡片渲染器）+ POST /protocols/session/steps/{n}/complete 显式完成接口（后端校验，不齐拒绝并返回缺什么）。
- 第 4 轮：横屏两栏布局（左形象+进度、右卡片）。
## 2026-08-17：产品化第 3/4 轮——卡片类型化 + 显式完成接口（完成）
### 本轮已完成
- 每步输出 card_type/recorded/missing；新增 POST /protocols/session/steps/{n}/complete（当前步才可完成、有偏差/缺字段则拒绝并说明）；前端 ✓/○ 字段清单；完成按钮改走新接口。
- 测试 733/733；接口实测拒绝逻辑正确。
### 用户验收路径
- 刷新 mobile 页（版本已升 v=20260817e）→ 选方案 → 卡片应出现 ○字段清单 → 说一句必测数据 → ○ 变 ✓ → 点「完成本步」→ 全部 ✓ 则确认完成、否则卡片内红条列出还缺什么。
### 下一轮（第 4/4 轮，等用户确认）
- 横屏两栏布局：左小科+任务进度清单，右大卡片；同一份数据，纯响应式，进度不重置。
## 2026-08-17：产品化第 4/4 轮——横屏两栏布局（完成）
### 本轮已完成
- 横屏（高≤520px）自动切两栏：左栏小科+✓/→/○进度清单，右栏大卡片；顶栏/控制条跨两列；版本号 v=20260817f。
- 至此产品化 4 轮全部落地：①AI形象 ②任务会话持久化 ③卡片类型化+显式完成接口 ④横屏两栏——"任务跟进式 Agent"完整形态。
### 用户验收路径
- 刷新 mobile 页 → 选方案 → 旋转屏幕：横屏应见左栏进度清单（✓/→/○）与右栏卡片，进度与竖屏一致；来回旋转不重置。
### 下一轮注意（候选）
- 语音回答播报（TTS）；偏差确认流程（error 消除路径）；真机 HTTPS 验收；把"新建实验确认流"卡片化（form/confirm 类型已预留）；PWA 打包（远期）。
## 2026-08-17：横屏卡片加宽加大（微调）
### 本轮已完成
- 左栏收窄至 24%、顶栏/控制条压矮、字号微涨（标题 22px/操作 16px）、块间距收紧；版本 v=20260817g。
### 用户验收
- 刷新后旋转屏幕：卡片应明显更大；若仍偏小，可继续把左栏收窄或改为"控制条悬浮"方案。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS、新建实验确认流卡片化、PWA。
## 2026-08-17：横屏卡片内部改横排布局
### 本轮已完成
- 横屏卡片内部两栏（左信息流/右参数警告、按钮通栏贴底），怪盗牌角横屏隐藏；版本 v=20260817h。
### 用户验收
- 刷新旋转：横屏卡片应布局舒展、不再靠缩字硬塞。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS、新建实验确认流卡片化、PWA。
## 2026-08-17：竖屏滚动兜底 + 横屏断点修正
### 本轮已完成
- 竖屏：整体缩字号、卡片内容超屏自动滚动（手势让位、按钮翻页）；横屏两栏断点加 min-width 条件；版本 v=20260817i。
### 用户验收
- 手机竖屏：内容不再被切，放不下时可在卡片内上下滚动，‹ › 翻页；
- 手机横屏：先确认手机"自动旋转"未锁（下拉快捷栏/控制中心），转过来应见两栏。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：横屏"一目了然"空间重分配
### 本轮已完成
- 横屏：顶栏极简、DEV 面板/调试徽标/重复下一步隐藏，底部仅语音+上一步；卡片内容平铺不滚动；版本 v=20260817j。
### 用户验收
- 手机横屏：整步内容一眼看全（无需滚动）；上一步在底部、下一步在卡片上；DEV 面板竖屏仍在。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：横屏铺满全宽
### 本轮已完成
- 横屏解除 max-width:460px 居中限制，布局铺满整屏宽度；版本 v=20260817k。
### 用户验收
- 手机横屏：左右不再有大片空白，两栏铺满屏幕。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：语音自动聆听模式
### 本轮已完成
- 删除大麦克风按钮；页面加载即自动聆听（连续识别、自动重启）；状态行"语音已开/已关"小开关；版本 v=20260817l。
### 用户验收
- 手机刷新后直接说话：小科变聆听脸、转写出现、AI 回复；点"语音已开"可暂停，再点恢复；权限弹窗点允许。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：DEV 面板竖屏可滚动
### 本轮已完成
- .m-dev[open] 基础样式加 max-height:40vh + overflow-y:auto；版本 v=20260817m。
### 用户验收
- 手机竖屏展开 DEV 面板：可在面板内上下划动看全部调试项。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：AI 回复气泡 + 完成仪式感动效
### 本轮已完成
- 小科气泡显示 AI 完整回复（8 秒淡出、点按关闭）；完成瞬间 ✓ 弹入 + 绿光 + 震动（仅转变瞬间触发）；版本 v=20260817n。
### 用户验收
- 手机：说一句话→卡片上方出现"小科"气泡全文；点「完成本步」通过后→✓ 弹出、卡片绿光一闪、手机轻震。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、新建实验确认流卡片化、PWA。
## 2026-08-17：实验完成结束卡 + 演示模式
### 本轮已完成
- 全部步骤完成→"实验完成 🎉"结束卡（含记录段数）；演示模式一键隐藏 DEV 面板（齿轮退出、状态记忆）；后端 all_completed 字段；版本 v=20260817o。
### 用户验收
- 手机：把某方案所有步骤完成→出现 🎉 结束卡；DEV 面板点"进入演示模式"→面板消失、右上角齿轮可见，点齿轮可退出。
### 待补事项
- 全量测试本轮审批被取消未跑（可下次补跑 733 基线）；下一轮候选不变：TTS、偏差确认、真机 HTTPS 全链路、确认流卡片化、PWA。
## 2026-08-17：手动确认直接完成（完成条件更新）
### 本轮已完成
- 「完成本步」按钮=手动确认直接打勾（不再要求口述数据）；后端 confirmed 状态 + 持久化；完成步清单全勾；全量测试 739/739（上轮欠账一并补齐）。
### 用户验收
- 手机（版本 v=20260817p）：选方案 → 什么都不记录直接点「完成本步」→ 立即 ✓ 完成、震动、无追问；说"下一步"翻页正常。
### 下一轮注意（候选不变）
- TTS 播报、偏差确认、真机 HTTPS 全链路、确认流卡片化、PWA。

