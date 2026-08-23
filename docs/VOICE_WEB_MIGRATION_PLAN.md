# 语音接入 Web 迁移计划（精简独立版）

> ⚠️ **2026-08-20 起，执行顺序请看 `VOICE_WEB_MIGRATION_PLAN_2026-08-20.md`（重排版）**。
> 本文件保留：语音形态决定、迁移契约、Phase A/B 历史拆解、§6 旧任务归属表（PRESENT/TIMING）、
> §7 本轮发现的问题。两者不冲突：新文件是"按顺序做"，本文件是"细节与归档"。

> 建于 2026-08-18。此文件是本轮讨论的**唯一简明落点**，替代在超长文档里翻找。
> 只记三样：语音形态决定、两个已知风险、从现在到全部结束的路线图。

---

## 一句话目标

把 CLI 已开发的"统一理解"脊椎迁进 web 当**唯一语义权威**；过渡期 web 不崩盘；
前端只负责"画"和"念"，**不负责"判"**。

> **产品形态（用户 2026-08-18 定）**：最终展示产品 = **web（桌面）+ 手机（/m），以 web 优先**。
> 验收、体验、后续 Phase C/D 均以 web 桌面为主路径，手机页为同构辅助（两者统一走 messages 渲染）。

---

## 1. 语音形态决定

- **优先保留：半双工 + 打断（barge-in）** —— 能说、能被用户随时打断，但不追求"俩人同时说"。
- **明确砍掉：全双工**（真·边说边听同时对话）—— 需额外回声消除工程，高风险、对 demo 低收益，不做。

---

## 2. 两个已知风险（记录在案，暂不修，后续在 Phase C 处理）

- **风险 A · 回声自打断**：连续通话麦克风常开，仅靠浏览器回声消除防止听到自己。
  用**外放**时可能：漏检打断（TTS 太响没触发），或把自己的 TTS 当成用户说话而**自我打断**。
  **尚未真机验证**，是未知风险不是结论。
- **风险 B · 三张嘴打架**：`local_tts.js` / `speak.js` / `mobile.js` 各自定义 `speak`/`stopSpeech`，
  **谁后加载谁占用 `window.speak`**。后果：打断时调的 `stopSpeech` 可能停错对象，
  导致 barge-in 失灵。**收敛为单一 `window.speak`（建议保留 `local_tts.js`，它最完整）。**

---

## 3. 迁移契约（不变量 + 五条）

**不变量（总闸）**：所有渠道（CLI / Web / TTS）从 `UnifiedObservation` 投影；
**允许**"降级生产者"产出**部分** `UnifiedObservation` 以支撑过渡，
**不允许**绕过 `UnifiedObservation` 另立投影。

1. **方向**：CLI 统一链（`UnifiedObservation` + 投影/闸门/文案）迁入 web；web 是产品，CLI 降为开发/兜底形态。
2. **不崩盘**：过渡期用**降级生产者**（确定性、不调 LLM、不改输入、不托管有状态会话）产出部分 `UnifiedObservation`，
   走**完整输出层**；真观察器就绪后 **drop-in 抽换生产者，输出层一行不动**。
3. **呈现**：前端为最终呈现（主渠道）；保留 `TerminalRenderer` 兜底（保持能跑、供验证，**不镀金**）。
4. **单一语义权威**：语义只在 intent/copy 层决定；前端只按 `screen_target`/`kind` 上样式，
   **不再用正则二次判断**。迁移是**做减法**（删前端重复逻辑）。
5. **TTS**：**嘴在前端**（现有供应商 + 播放 + barge-in），**词在后端**（copy 层语音渠道文案，短、按 `screen_target` 过滤）。
6. **理解/执行分层**：统一链是"理解"的唯一权威（辨意图、抽实体、判缺字段）；"执行"（建实验/查冲突/列实验/记忆/算数/时间/推步骤等工具）是独立一层，由统一链的理解结果驱动，**迁移不替换执行工具**。`record_observation` 里的规则抽取属于"理解"、迁入统一链；落库仍由工具层做。

---

## 4. 路线图：从现在到全部结束

> 原则：一次只推进一个可独立验证的环节；先单测→影子→切换；外部服务失败可回退。

### Phase A · 立契约与基线（现在）
- [x] 建本文档，记录形态决定 / 风险 / 契约。
- [ ] （可选）把"不变量"镜像进 `docs/PROJECT_ARCHITECTURE.md` 5.3/5.4，作为约束后续 agent 的硬闸。

### Phase B · 输出层接线（已完成 REAL_OK，2026-08-18 真实验收通过；降级过渡，web 输出收敛、不崩盘）
- [x] B1 敲钉子（纯设计，已定稿，2026-08-18）：**选"容忍部分观察的分支"，不拼富字段**。结论见下"B1 敲钉子结论"。
- [x] B2 实现降级生产者 + `WebRenderer`（意图→结构化 JSON）；全单元测试，零真实服务。
      （2026-08-18 全部完成：B2-1 `UnifiedObservation` partial 字段 + 校验分叉 + 投影 partial 分支，
      13 项测试；B2-2 `web/degraded_producer.py` 降级生产者，12 项测试；
      B2-3 `web/web_renderer.py` WebRenderer，10 项测试；全量 790 通过，零真实服务）
- [x] B3 `/record` 影子式新增 `messages` 字段（**保留原始 evaluation**）；肉眼核对顺序 + 单问题闸门生效。
      （2026-08-18 完成：`web/api/record.py` 内联"降级生产者→投影→WebRenderer"，messages 挂接口返回
      不入库；6 项测试，全量 796 通过）
- [x] B4 前端切到渲染 `messages`，退役正则分类；写 `PROJECT_ARCHITECTURE.md` 5.3 职责迁移对照表（标等价/降级/丢失）。
      （2026-08-18 完成，Phase B 收官：speak.js/lab_panel.js/voice_asr.js/mobile.js 切渲染 messages，
      保留点 views.js 历史视图 + labEvaluate 面板；5.3 WEB-RENDER-01 + 5.4 web 侧 5 行；合同测试更新）

> **Phase B 真实验收通过（REAL_OK，2026-08-18/19）**：用户实测语音记录链路闭环——
> 桌面灰色圈圈（语音记录）→ 录音 → /record → 右侧面板"第 N 段口述"+ 回执"已记录"；
> 选方案后口述缺字段 → 面板"小科追问：…"+ TTS 朗读纯问题。验收期间暴露并修复：
> ① WEB-RENDER-02 桌面语音链死代码（B4 的 /record 直连分支因聊天框分支在前从未执行）；
> ② 话术撒谎硬问题（"结构化成功却说不可用"，拆成 RECORDED_NO_STEP/已记录 vs DEGRADED/不可用）；
> ③ `lab_panel.js` 未注入（结果无处渲染）；④ 语音入口混乱（4 入口职责混杂，cp-mic 误触发电话）；
> ⑤ 文案"助手追问"→"小科追问"、TTS 不念"小科"前缀。全量 **800 tests OK**。
> **关键定位纠正（用户）**：统一理解链的核心是**处理命令（control 分支：查看/暂缓/确认/结束/回答）**，
> B 阶段降级生产者只有"实验记录 + 按方案追问"，命令处理是 **Phase D** 接真观察器（含 LLM）才能迁入。

> **B1 敲钉子结论（2026-08-18 定稿）**
>
> **决策：选"容忍部分观察的分支"，不拼富字段（否掉含 `pending_action` 的富字段方案）。**
>
> - 降级生产者填 10 个字段：`request_id / session_id / segment_id / status / partial=True /
>   destination / acceptance_kind / missing_fields / follow_up_required / partial_question`。
>   - `destination`：`follow_up_required` → `CLARIFICATION_CONTEXT`；否则 `EXPERIMENT_PIPELINE`。
>   - `acceptance_kind`：追问 → `None`；记录 → `degraded_evidence_note`（降级生产者无真·统一理解，
>     语义 = "原始记录已保存"）。
> - `UnifiedObservation` 新增 `partial: bool = False` + `partial_question: str | None = None`；
>   `partial=True` 时放宽 OBSERVED 校验（只对降级构造放行，CLI 完整路径校验不变）。
> - `messages_for_observation` 在 OBSERVED 内新增 partial 分支：有 `partial_question` →
>   `CLARIFICATION`（screen_target=CURRENT_QUESTION）；无 → `RECORD_ACK`（降级语义）。
> - 否掉富字段的理由：① "记录成功"路径需要 step_number（CLI 由会话级计数器提供），web 降级生产者
>   契约禁止托管有状态会话 → 语义缺口无法诚实补齐；② 拼 `ClarificationAction` 要伪造
>   asr_transcript/reason/mutation_permission 等一串样板值，违反"模型推断不覆盖原始事实"。
> - 真观察器 drop-in（D3）时：partial 分支自然闲置，`messages_for_observation(observation)` 签名
>   不变，调用点零改动。
> - **层边界（契约 4/5，2026-08-18 用户确认）**：投影层只产出**意图**（`PresentationIntent`，
>   不含中文）；**话**由 copy 层文案 + 渲染器生成——CLI 是 `TerminalRenderer`
>   （`render(intent) -> str`），web 是 B2 的 `WebRenderer`（意图→结构化 JSON）。
>   前端只按 `screen_target`/`kind` 上样式、按 `priority` 排序，**不产话、不判意图**。

### Phase C · 语音收敛与加固（不阻塞 B，可穿插）
- [x] C1 三张嘴收敛为单一 `window.speak`（保留 `local_tts.js`，删另两份）—— 解决风险 B。
      （2026-08-20 完成：speak.js 改薄适配层、mobile.html 加载 local_tts.js、mobile.js 委托 window.speak、
      local_tts.js 补浏览器兜底 + status 空安全；全量 804 测试通过）
- [x] C2a 后端 copy 层新增 `voice` 通道 + `voice_text` 字段（词在后端）；前端不再剥"小科："前缀。
      （2026-08-20 完成：copy_for_intent(voice=True) + WebRenderer.voice_text + 前端 labSpeakMessages/mobile.js 改读 voice_text；
      新增 4 项 voice 测试，全量 804 通过）
- [ ] C2b 替换现状"念 /chat agent 回答"（对话链路 TTS 改读 copy 层语音文案）—— **暂缓到 Phase D**：
      对话链路的 agent 回答是自由文本、无 copy 层短文案，需 D 阶段真观察器接管对话后才能干净替换。
- [ ] C3 真机验证 barge-in：外放 + 耳机分别测漏检/自激 —— 解决风险 A，留证据。
      （2026-08-20 已做部分：噪音误触调参（阈值/回滞/最短语音）+ 朗读结束状态字修复"正在聆听，请说话"；
      但"自激/漏检"真机验证仍未做；噪音治本见 C4）
- [ ] C4 噪音误触治本：通话模式 energy-VAD → Silero VAD（`vad_mode.js` 已在用）——能量检测天生怕噪音，阈值调高治标不治本。
- [ ] C5 语音输出受控：①话术来源统一（理解结果 `Intent→copy` 与工具结果 `present` 汇到同一话术层，TTS 只读统一来源）；
      ②pre-TTS 硬约束（硬截断/内容过滤/分句选优先级 + 认知负担预算 `PRESENT-03` 2条/50字/1问）；
      ③`PRESENT-NOACTION-FEEDBACK-01`（LLM 弃权时给反馈、不沉默）。

### Phase D · 升级到真·统一理解（drop-in 抽换生产者）
- [ ] D1 服务端托管有状态会话（`reply_coordinator` 等），按对话 keyed、并发安全（**不用全局单例**）。
- [ ] D2 `/record` 输入从"已抽取 entities"改为"原始 `ASRResult`"，接 `UnifiedObserver.observe`（含 LLM，带可回退开关）。
- [ ] D3 抽换：降级生产者 → 真观察器；**输出层不动**；跑全量回归。

### Phase E · 收尾验收
- [ ] E1 功能验收（REAL_OK）：真实录音→记录→追问→确认闭环。
- [ ] E2 体验验收（UX_CONFIRMED）：按 `UX_WALKTHROUGH_CHECKLIST.md` 九维走查，**最终裁决权在用户**。
- [ ] E3 固化"明确不做"清单，更新三份必维文档。

---

## 5. 明确不做（防止范围蔓延）

- 全双工（真·边说边听同时对话）。
- CLI 终端 UX 镀金（终端仅作兜底/验证，不做产品级打磨）。
- 在薄字典（`evaluate_segment` 结果）上另立平行投影 —— 违反不变量。

---

## 6. 旧任务归属表（PRESENT / TIMING → 新计划）

> 建表 2026-08-20。目的：清单里 PRESENT 那批 + TIMING 是为 CLI 终端写的，迁 web 后逐一重新归类，
> 防止"任务凭空消失"或"没人管"。本表是唯一书面归宿，与 `PROJECT_TASK_CHECKLIST.md` 对账。
> 状态标记：`[完成]` 已落地；`[部分]` 部分落地；`[待做]` 重新归类后待做；`[砍]` 有理由地不做。

### 6.1 PRESENT 十项

| 旧任务 | 归到哪 | 状态 |
|---|---|---|
| `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01`（P0 复合确认+回答） | 先在 CLI 独立收掉（B 方案，已 REAL_OK） | [完成]（集合方案 + 确定性/LLM 混合，808 测试，会话 20260820_122234） |
| `PRESENT-NOACTION-FEEDBACK-01`（no_action 容错反馈） | Phase C5（语音输出受控） | [待做]（LLM 弃权/无动作时投影层给反馈，不再沉默） |
| `UX-MODE-01`（user/admin 分层） | 拆：copy 层 `ui_mode` → Phase B 复用；终端双会话对照验收 → [砍] | [部分]（语义已随 copy 层存在；终端对照砍） |
| `SYNC-UI-CLAIMS-01`（文案与行为一致） | 契约第 4 条 + Phase B4 | [部分]（B4 退役前端正则已落地；余项随各 Phase 收口） |
| `PRESENT-RECORD-PREVIEW-01`（规范记录预览） | Phase B | [待做]（`normalized_text` 预览，归记录回执语义） |
| `PRESENT-DELIVERY-BOUNDARY-01`（交付链路合同） | Phase B 本身 | [部分]（web 链=降级生产者→投影→WebRenderer→messages；CLI Coordinator/Pump 架构不迁） |
| `PRESENT-EXTENSION-SEAMS-01`（QUERY/DENY/WARNING/导出接缝） | 拆：WARNING/安全抢占 → Phase B；QUERY/DENY/导出 → Phase D 后按需 | [待做]（留接缝，不提前通用化） |
| `GAPS-FIX-ANSWER-HINT-01`（回答编号提示） | Phase B/D 小改（copy 层） | [待做]（依赖 `SESSION-IDENTITY-CONTRACT-01`） |
| `UX-FIX-TONE-01`（事件提示音） | Phase C | [待做]（提示音≠TTS，前端音频能力） |
| `PRESENT-FINAL-UX-VERIFY-01`（最终双模式 UX 验收） | Phase E2（挪到 web） | [待做]（终端最终验收 [砍]，web 九维走查） |

### 6.2 PRESENT 散项

| 旧任务 | 归到哪 | 状态 |
|---|---|---|
| `PRESENT-03`（认知负担预算 2条/50字/1问） | Phase C5（pre-TTS 硬约束） | [待做] |
| `PRESENT-05`（用户输出与 debug 分离） | Phase B（WebRenderer 按 `screen_target` 过滤） | [部分] |
| `PRESENT-07`（编号答复后状态回执） | Phase B/D 投影层 | [待做] |
| `PRESENT-STYLE-01`（语义与前端/TTS 样式分离） | 契约第 4/5 条（B WebRenderer + C TTS） | [部分] |
| `PRESENT-04`（编号分离） | Phase D 前后（卡 `SESSION-IDENTITY-CONTRACT-01`） | [待做]（先定合同） |

### 6.3 TIMING 三项

| 旧任务 | 归到哪 | 状态 |
|---|---|---|
| `TIMING-01`（LLM 完成即显示） | 保留 | [完成]（web 天然 request-response，每次 /record 当场返回） |
| `TIMING-02`（用户说话时不输出/播放） | Phase C3/C4（barge-in + 噪音治本） | [待做]（phone_call.js 已有雏形，C4 换 Silero VAD 后做实） |
| `TIMING-03`（安全回复判断接口） | Phase B + Phase C | [待做]（copy 安全分支 B + TTS 按 screen_target 选念 C） |

### 6.4 明确砍掉（有理由地不做）

1. `UX-MODE-01` 的终端双会话对照验收、`PRESENT-FINAL-UX-VERIFY-01` 的终端最终 UX 验收——契约第 3 条"终端降为兜底、不镀金"，真实 UX 验收整体挪到 web（E2）。
2. 提前通用化 QUERY/DENY/导出——按"留接缝、不提前造"，功能上线时再扩。

### 6.5 已拍板（2026-08-20）

- `CLARIFICATION-COMPOUND-CONFIRM-ANSWER-01`（P0）：**选 B（先在 CLI 独立收掉）**，已 REAL_OK（回填见 6.1 该行）。

---

## 7. 本轮（2026-08-20）发现的问题 + 重新设计的路线

> 本轮完成 P0（复合确认+实体 REAL_OK）+ 语音入口治理 + 噪音调参，过程暴露一批新问题。
> 本节只记**新暴露、且上面路线图没落点**的问题，以及**重新设计后的推进顺序**。

### 7.1 待解决问题清单（本轮新发现，按优先级）

| 优先级 | 问题 | 落点 |
|---|---|---|
| 高 | 通话模式 energy-VAD 对噪音太敏感（阈值调高治标不治本） | Phase C4（换 Silero VAD） |
| 高 | 话术来源不统一：理解结果 `Intent→copy` vs 工具结果 `present` 各走各的，TTS 无统一来源 | Phase C5 |
| 高 | 语音长文本无硬闸（靠 prompt 软约束，LLM 可能不听） | Phase C5 |
| 高 | `no_action` 沉默（LLM 弃权时用户得不到任何反馈） | Phase C5 / `PRESENT-NOACTION-FEEDBACK-01` |
| 中 | "对，是X"等非"是的"前缀的确认仍靠 LLM（可能 abstention，P0 只覆盖了确定性前缀） | Phase D |
| 中 | 语音输出"时机"不清晰（朗读完状态字回不到"正在聆听"，已修状态字、待统一两处措辞） | Phase C 收尾 |
| 中 | ASR"是的"→"日的"误识别 | 已登记 `ASR-DEMO-NOISE-01` |
| 环境 | 工作区分裂：`Desktop\asr_demo`（完整数据）vs `Documents\107`（缺模型/.env/audio），每跑一次撞一个缺文件 | 环境，非迁移 |

### 7.2 重新设计后的推进顺序

**主线不变**：语音受控是根本目的（不是"统一/确定"本身）。调整后：

```
Phase C（语音收敛与加固，扩展后）
  C1✅ C2a✅ C2b(暂缓D)
  → C5 语音输出受控（话术统一 + 硬截断 + no_action 反馈）   ← 先做，这是"语音受控"的核心
  → C4 噪音治本（Silero VAD）
  → C3 真机 barge-in（C4 治本后再验才干净）
Phase D（命令处理迁入）
  含"理解/执行分层"边界（契约 6）：只收敛 record_observation 的规则抽取，保留执行工具
Phase E（收尾验收）
```

**为什么 C5 排在 C4/C3 之前**：噪音和打断都是"前端发声"的体验问题，但"语音说什么"（话术统一 + 硬截断）才是"语音受控"这个根本目的的直接落地；先定"说什么"，再调"怎么听/怎么停"。
