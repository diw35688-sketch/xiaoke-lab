# 主动规划型实验智能体（Proactive Lab Agent）设计

> 目标：把当前“聊天 + 方案 + 记录”的实验助手，升级为一个**会主动规划、能长期记忆、会每天心跳反思、能跟着主人进化**的实验智能体。
>
> 参考：OpenClaw 2.0（Agent Loop、Heartbeat/Cron、Skills、Memory、Logbook）、Agent Laboratory、ChemCrow、eLabFTW 等开源项目，以及本项目已有的方案/步骤/记录/试剂/语音能力。

---

## 1. 产品愿景

用户打开系统后，不再是面对一个空白聊天框，而是面对一个“知道我现在在做什么、上次做到哪、今天该做什么”的实验室队友。

核心体验：

```text
早上 8:00   → 主动心跳：今天有 3 个实验待做，其中 2 个需要先配液
实验前      → 一键生成准备清单：试剂、耗材、仪器、安全、预计时长
实验中      → 你说操作，它自动记录时间戳；需要等 30 分钟 → 自动计时
实验后      → 自动写实验记录，晚上自动反思，沉淀经验
长期        → 记住你的实验领域、偏好、常用方法，越来越懂你
```

## 2. 从 OpenClaw 2.0 借鉴什么

### 2.1 Agent Loop（最核心）

OpenClaw 的 Agent Loop 不是“按模式路由”，而是：

```text
组装上下文（会话 / 记忆 / 工具 / 状态）
  → 让 Agent 判断当前该做什么
  → 执行工具
  → 更新记忆
  → 主动触发下一步
```

我们当前的问题正是“强加路由”：每条消息先被塞进聊天/记录/推进的固定管道，导致用户说“在菜楼”也要被追问称量值。

**改造原则：**

```text
不再由系统先选路由，而是由 Agent 在明确约束下决策：
- 用户只是在聊天 → 聊天
- 用户陈述实验事实 → 记录
- 用户明确说下一步 → 推进并给出下一步操作
- 用户问怎么做 → 直接讲当前步骤
- 用户没说下一步 → 绝不问“要进入下一步吗”
```

### 2.2 Heartbeat / Cron / Tasks / Hooks

| OpenClaw 机制 | 我们对应场景 |
|---|---|
| Heartbeat | 每天早上主动汇报今日计划、上次进度 |
| Cron | 精确到点的实验定时器、每晚反思任务 |
| Background Tasks | 论文检索、批量生成 protocol |
| Task Flow | “论文 → protocol → 清单 → 执行 → 反思”长流程 |
| Hooks | 步骤完成、定时结束、实验会话关闭等生命周期事件 |

### 2.3 Skills（技能包）

每个技能是一个可独立加载、可组合的能力单元：

```text
skills/
  paper-to-protocol/     # 论文检索 → protocol 草稿
  prelab-checklist/      # 实验前准备清单
  experiment-runner/     # 方案执行、记录、推进
  timer/                 # 实验定时器
  daily-heartbeat/       # 每日主动汇报
  daily-reflection/      # 每晚实验复盘
  owner-profile/         # 主人画像与偏好
```

### 2.4 Memory（记忆分层）

```text
短期记忆：当前会话、当前方案、当前步骤
中期记忆：今天的实验记录、今天的定时任务
长期记忆：主人画像、实验经验、反思沉淀、常用 protocol
```

实现建议：

- 短期/中期：现有 SQLite（conversations、lab_records、protocol_sessions）
- 长期：SQLite + 向量检索（Chroma/LanceDB 或本机轻量方案）
- 反思：每晚由 LLM 读取当天记录，生成结构化“经验条目”

### 2.5 Logbook（自动日志）

OpenClaw 的 Logbook 基于定期快照自动形成工作日志。我们对应：

```text
每条 lab_record 自动带 created_at
“今天做了哪些实验” = 按日期查询记录 + 实验会话
“本周做了什么” = 自动汇总
```

## 3. 目标架构

```text
┌────────────────────────────────────────────────────────────┐
│ 入口层                                                      │
│ Web 聊天 / 电话 / 语音 / 定时任务 / Webhook / 手机          │
├────────────────────────────────────────────────────────────┤
│ Gateway                                                      │
│ 统一接收消息和事件，不做业务路由                             │
├────────────────────────────────────────────────────────────┤
│ Agent Loop（核心改造）                                      │
│  - 组装上下文：会话、方案、步骤、记忆、技能、安全           │
│  - 让模型决策：聊天 / 记录 / 推进 / 查试剂 / 创建定时       │
│  - 执行后主动触发下一步                                     │
│  - 失败可重试，事件可恢复                                   │
├────────────────────────────────────────────────────────────┤
│ Skills                                                      │
│  paper-to-protocol / prelab-checklist / experiment-runner   │
│  timer / daily-heartbeat / daily-reflection / owner-profile │
├────────────────────────────────────────────────────────────┤
│ 记忆层                                                      │
│  主人画像 / 实验经验 / 反思沉淀 / 历史记录 / 论文库         │
├────────────────────────────────────────────────────────────┤
│ 数据层                                                      │
│  protocols / protocol_steps / lab_records / reagents        │
│  storage / conversations / timers / reflections / papers    │
└────────────────────────────────────────────────────────────┘
```

## 4. 数据模型扩展

### 4.1 新增表

```text
owner_profiles
  id, user_id, field, study_stage, preferred_methods,
  lab_hours, interests, created_at, updated_at

reflections
  id, user_id, date, summary, deviations, lessons,
  next_day_plan, created_at

paper_sources
  id, user_id, title, authors, source, url,
  pdf_path, parsed_text_path, doi, status, created_at

generated_protocols
  id, paper_id, protocol_id, generator_version,
  source_text, confidence, status, created_at

prelab_checklists
  id, protocol_id, session_id, checklist_type,
  items_json, generated_at

timers
  id, conversation_id, protocol_session_id, step_number,
  title, duration_seconds, started_at, fire_at,
  fired, status, created_at

agent_skills
  id, name, enabled, config_json, updated_at

daily_heartbeats
  id, user_id, date, summary_json, delivered, created_at
```

### 4.2 现有表复用

```text
conversations        → 会话
messages             → 聊天历史
lab_records          → 实验记录（已含 created_at）
protocol_sessions    → 方案执行状态
protocols            → 方案
reagents / storage   → 库存与准备清单交叉核对
```

## 5. Skills 详细设计

### 5.1 paper-to-protocol

```text
触发：用户说“查一下 xxx 的 protocol”“从这篇论文生成方案”
流程：
  1. 检索 arXiv / Semantic Scholar / OpenAlex / PubMed
  2. 下载 PDF（如需要）→ MinerU 解析
  3. 提取 Methods / 试剂 / 仪器 / 步骤 / 条件
  4. LLM 生成结构化 protocol 草稿
  5. 用户确认后写入 protocols
```

### 5.2 prelab-checklist

```text
触发：方案开始前，或用户说“准备一下”
输出：
  - 试剂（含浓度/体积/储存条件）
  - 耗材（枪头/离心管/手套等）
  - 仪器（分析天平/离心机/水浴锅）
  - 安全提示
  - 预计时长
  - 需要提前配制的试剂
与 storage/reagents 库存交叉，标记“缺货”
```

### 5.3 experiment-runner（现有状态机增强）

```text
- 每个步骤自动记录开始时间
- 用户口述 → 自动写入 lab_records（含时间戳）
- 字段齐全且明确 → 自动推进并说出下一步操作
- 缺字段但不影响安全 → 不追问，允许继续
- 只有影响安全/结果/审计时才创建确认问题
```

### 5.4 timer

```text
触发：方案步骤含“等待/孵育/离心 xx 分钟”或用户说“30 分钟后提醒我”
行为：
  - 创建 timer
  - 到点后通过 Web/电话/TTS 通知
  - 自动在记录中写入“xx 定时结束”
  - 询问是否记录观察结果
```

### 5.5 daily-heartbeat

```text
每天早上（可配置）：
  - 读取今天的计划/待办实验
  - 读取昨天未完成实验
  - 生成今日建议
  - 推送到 Web / 语音 / 手机
```

### 5.6 daily-reflection

```text
每天结束后（可配置）：
  - 读取当天 lab_records
  - 总结完成度、偏差、风险
  - 沉淀经验到 reflections
  - 生成明天计划
```

### 5.7 owner-profile

```text
从对话/实验行为中提取：
  - 实验领域
  - 常用方法/试剂
  - 学习阶段
  - 偏好（文字简洁/语音播报/自动记录）
只保存用户可查看、可删除的信息
```

## 6. 自动化调度

```text
scheduler（APScheduler）
  ├── HeartbeatJob    每天 08:00（可配置）
  ├── ReflectionJob   每天 21:00（可配置）
  ├── TimerJobs       一次性，步骤到点触发
  └── PaperScanJob    每周/手动，检索相关论文
```

## 7. API 设计草案

```text
GET    /agent/heartbeat/today          # 今日心跳内容
POST   /agent/heartbeat/run            # 手动触发心跳
POST   /agent/reflect                  # 手动触发当日反思
GET    /agent/timeline?date=           # 某天实验时间线

POST   /papers/search                  # 论文检索
POST   /papers/{id}/parse              # 解析 PDF
POST   /papers/{id}/to-protocol        # 论文 → protocol 草稿

POST   /checklists/generate            # 生成准备清单
GET    /checklists/{protocol_id}

POST   /timers                         # 创建实验定时器
GET    /timers/active
POST   /timers/{id}/cancel

GET    /owner/profile
PATCH  /owner/profile
```

## 8. 用户体验原则（必须遵守）

1. **不强行路由**：先理解这句话是聊天、事实、提问还是指令。
2. **主动但不烦人**：只在有意义时主动开口（开始实验、定时结束、当天待办）。
3. **记录不打断**：记录是后台动作，不需要用户确认“是否记录”。
4. **字段不追问**：非关键字段缺失先继续，后续补充自然累计。
5. **下一步直接说**：推进后直接告诉用户“下一步做什么、怎么做”，不问“要不要继续”。
6. **可干预**：用户随时说“别提醒我”“不要自动记录”“跳过这步”。

## 9. 落地阶段

### 阶段 0：当前修复（已进行中）

- 聊天不再强加字段追问
- 结构化回复去掉“要进入下一步吗”
- 纯标点不再调模型
- 模型重试提升到 3 次

### 阶段 1：Agent Loop 改造

- 建立统一的 `AgentContext`（会话、方案、步骤、记忆、可用技能）
- 把当前 `turn_processors` 的硬路由改为“决策 + 执行 + 反馈”
- 保留现有协议状态机作为 experiment-runner 技能

### 阶段 2：记忆与主人画像

- 新增 `owner_profiles`、`reflections`
- 实现简单记忆读写 API
- 让 Agent 在回答时读取长期记忆

### 阶段 3：Heartbeat / Reflection / Timer

- 引入 APScheduler
- 实现每日心跳、每晚反思
- 实现实验定时器 + 到点通知

### 阶段 4：论文 → protocol

- 接入 arXiv / Semantic Scholar / OpenAlex
- 接入 MinerU 解析
- 实现 `paper-to-protocol` 技能

### 阶段 5：准备清单与批量实验

- 实现 `prelab-checklist`
- 支持“点菜多个实验”批量排程
- 与库存/试剂交叉核对

## 10. 风险与决策

| 风险 | 应对 |
|---|---|
| 主动提醒打扰用户 | 所有心跳/提醒可配置开关，默认低频 |
| 记忆隐私 | 只保存用户可见、可删除的本地数据 |
| 自动记录误写 | 高价值/不可逆操作仍先确认 |
| 论文生成 protocol 不可靠 | 标为“草稿”，必须用户确认后才能进入方案库 |
| Agent Loop 成本/延迟 | 普通聊天走轻量路径；复杂规划才走完整 Agent Loop |

## 11. 已确认决策

1. 每日心跳时间：**用户自己在设置中心配置**（默认 08:00，可开关）。
2. 定时器到点通知：**Web 弹窗**（后续可扩展到语音/电话）。
3. 论文来源：**先做上传论文解析，不做联网检索**；用户上传 PDF/图片 → OCR/解析 → 生成 protocol 草稿。
4. 准备清单：**需要与现有试剂配置库/储存库同步**，自动标出缺货。
5. 主人画像：**在设置中心由用户自己补充**，AI 不自动写入。

## 12. 当前实现进度

### 已实现

- 设置中心：每日心跳开关/时间、主人画像（用户自行填写）。
- 心跳调度：读取 `heartbeat_time`，可关闭。
- 实验计时器：
  - `POST /timers` 创建
  - `GET /timers/active` 查询
  - `DELETE /timers/{id}` 取消
  - 前端轮询到点弹窗 `timer_popups.js`
  - 计时器到点后自动写一条实验记录
- 准备清单：
  - `POST /checklists/generate` / `GET /checklists/{protocol_id}`
  - 从方案 terms/字段/预配需求提取试剂、仪器、耗材、安全
  - 与储存库 `storage_items` 交叉核对，标记库存缺失
  - 方案详情页新增“生成准备清单”按钮
- 论文上传：
  - `POST /papers/upload` 上传论文并持久化（原文件、OCR 文本、草稿）
  - 已有 `/protocols/upload-file` 支持 PDF/图片 OCR → protocol 草稿
  - 现在自动把来源文件名写入草稿 `source`，确认保存后可知出处
- 实验点菜/批量规划：
  - 方案列表支持勾选多个实验 → “点菜加入今日计划”
  - `POST /planning/order` 批量创建实验计划项
  - `POST /planning/combined-checklist` 合并多份方案准备清单
  - 自动从准备清单带出仪器信息到实验项
- 每日心跳内容：
  - `POST /agent/heartbeat/run` 手动触发
  - 自动生成“今日计划 + 昨日工作”通知
- 每晚反思：
  - `POST /agent/reflect` 手动触发
  - 自动生成当天实验总结与明日建议通知
- 实验时间线：
  - `GET /agent/timeline?date=YYYY-MM-DD`
  - 返回当天实验记录、实验计划、通知

### 待实现/可增强

- 反思内容接入 LLM：真正读取当天记录生成“经验教训/偏差分析”
- 准备清单保存为结构化数据（当前每次实时生成）
- 论文库前端页面：浏览已上传论文、回看 OCR 文本、一键重新生成方案
- 定时器到点通知手机/语音
- 论文联网检索

## 13. OpenClaw 深度移植进度

已对照 `_openclaw_ref` 源码移植：

- **持久化 cron**：
  - `cron_jobs` 表，支持 `at` / `every` / `cron` 三种 schedule
  - `cron_store.py` 增删改查、next_run_at 计算
  - `cron_service.py` 后台调度，重启不丢
  - 心跳/反思以系统 cron job 持久化
- **Heartbeat loop / Harness**：
  - `agent_harness.py` 模型驱动循环
  - 强制调用 `heartbeat_respond` / `reflection_respond`
  - 模型返回 `notify + notificationText`
  - `notify=false` 时静默跳过
  - 模型不可用时静默失败，不打扰用户
- **Context Engine / Embedded Agent Runner / Multi-Agent Routing**：
  - `agent_loop.py` 新增 `AgentContextEngine`：组装系统提示、长期记忆、任务上下文
  - 新增 `EmbeddedAgentRunner`：多轮工具循环，模型可先查今日上下文/库存，再调用终端工具
  - 新增 `MultiAgentRouter`：按 heartbeat / reflection / planner / experimenter / general 路由到不同子智能体
  - 心跳/反思不再是单轮决策，而是“查工具 → 继续推理 → 终端工具结束”的多工具 Agent Loop
  - OpenAI 客户端显式 `trust_env=False`，避开系统代理导致的 SSL 断连
- **Transcript Compaction（超长会话压缩）**：
  - `compaction.py`：历史超过阈值时，旧消息交给模型生成摘要
  - 摘要 + 最近 N 条原文继续作为上下文
  - `conversation_compactions` 表持久化摘要，避免重复压缩
  - 已接入 `run_agent` / `stream_agent` / `_run_skill_agent`
- **Automations API**：
  - `GET/POST/PATCH/DELETE /automations`
  - `POST /automations/{id}/run` 手动立即执行
- **UI**：
  - “今日规划”页新增“自动化任务”列表
  - 每条任务显示 schedule、enabled、下次运行时间、立即运行按钮
