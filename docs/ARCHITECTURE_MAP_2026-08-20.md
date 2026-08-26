# 架构梳理结论（2026-08-20）

> 把"杂糅版"彻底理清后的**地图**：两套大脑、三个桥、两条数据流、四条前后端通道、工具调用机制。
> 可作为简历/面试的素材。现状快照见 [`CODE_STATE_SNAPSHOT_2026-08-20.md`](CODE_STATE_SNAPSHOT_2026-08-20.md)。

---

## 1. 一句话总览

**实验助手**：语音/文字驱动的实验室记录与规划助手。实验者口述操作，系统转录 → 结构化抽取 → 按方案确定性判断缺字段 → 追问补齐 → 落库。**web 是产品，CLI 是兜底。**

---

## 2. 两套大脑（双轨对照表）

| 维度 | CLI 统一链（`src/`，本人写） | web agent（`web/`，组员写） |
|---|---|---|
| 入口 | `src/main.py` 终端循环 | `web/app.py`（FastAPI）→ `/record` 或 `/chat` |
| 大脑 | `UnifiedUnderstandingProcessor`（一次 LLM） | `agent/core.py` 的 tool-calling LLM（≤6 轮） |
| 判断方式 | 精确规则 + 一次 LLM 分类，**缺字段由程序按方案算** | 模型自主决定调哪个工具 |
| 数据合同 | `frozen=True` dataclass，构造时校验 | dict / JSON |
| 副作用 | `main.py` 编排，JSONL 落盘 | `database/` SQLite + 工具函数 |
| 测试 | 422+ 单元/集成测试 | 较薄 |
| 定位 | 兜底 | 产品 |

**关键边界（迁移契约 6）**：统一链管理解、工具管执行。迁移不替换执行工具。

---

## 3. 三个桥（组员复用本人 src 的通道）

```
        本人的 src（理解层权威，frozen dataclass + 严格校验）
        ▲                  ▲                    ▲
        │                  │                    │
    llm_bridge.py      domain.py      degraded_producer.py + web_renderer.py
   （复用统一理解）  （复用方案评估/安全）   （复用呈现层三件套）
        │                  │                    │
        └──────────────────┴────────────────────┘
                        web 组员写的部分
```

- **`llm_bridge.py`**：提供符合 `src.llm.client.LLMClient` 协议的客户端（配置来自网页设置），让 web 用上 `src` 的 `UnifiedUnderstandingProcessor`。**不重写提示词与解析。**
- **`domain.py`**：复用 `src` 的 `evaluate_segment`（缺字段/偏离判断）、`select_protocol`、`HazmatStore`（试剂安全）。**只装配与转译，不做业务判断。**
- **`degraded_producer.py` + `web_renderer.py`**：把 `src` 的"降级生产者 → 投影 → 渲染"三层呈现链，翻译成前端能吃的 JSON（`kind`/`screen_target`/`text`/`voice_text`）。

---

## 4. 数据流图（两条线）

### 记录链 `/record`（语音口述 → 结构化记录）

```
前端录音(voice_asr.js) → 编码 WAV → POST /asr/transcribe → SenseVoice 转文字
  → POST /record {transcript}
  → record.py:
      ① llm_bridge.extract() ──→ src 统一理解链抽实体（experiment/control/uncertain）
      ② extract_entities() ────→ 规则兜底（数量/单位/温度，LLM 失败或没抽到才用）
      ③ domain.evaluate() ─────→ 确定性判断：缺字段/偏离方案【不调 LLM】
      ④ degraded_producer ─────→ 翻译成 UnifiedObservation（部分观察）
      ⑤ messages_for_observation → 投影成 PresentationIntent 列表
      ⑥ WebRenderer.render() ──→ dict(kind/screen_target/text/voice_text)
      ⑦ save_record() ────────→ SQLite
  → 返回 {item, messages} → 前端只"画"和"念"，不再判断
```

### 对话链 `/chat`（文字/通话 → 对话与命令）

```
输入框(composer.js) / 通话(phone_call.js)
  → POST /chat {message}（或 /chat/stream 流式）
  → agent/core.py run_agent/stream_agent:
      INSTRUCTIONS + 长期记忆 + 历史 → OpenAI（tools=TOOLS）
      模型选工具 → run_tool():
         calculate / list_experiments / check_conflicts
         propose_experiment / confirm_create_experiment
         propose_memory / confirm_save_memory
         + lab_tools 9 个工具（record_observation/查安全/计时/选方案…）
      ≤6 轮循环
  → 回复文字（流式带 [[LABTHINK]]/[[LABCARD]] 标记）→ 前端显示 + TTS 朗读
```

---

## 5. 后端 → 前端四条通道

| 通道 | 机制 | 用在哪 |
|---|---|---|
| A. 普通 JSON | `return` 一次性响应 | `/record` 返回 `messages` |
| B. SSE 流 | `StreamingResponse(text/event-stream)` | `/chat/stream` 打字机效果 |
| C. 后台任务 + 轮询 | `task_manager`（ThreadPoolExecutor）+ `/tasks` | 排期/查询类请求 |
| D. TTS | `POST /tts` → 音频 blob → `Audio.play()` | 后端文字 → 前端声音 |

---

## 6. 工具调用机制（function calling）+ "知识库"真相

- **工具调用**：OpenAI function calling。`agent/core.py` 把工具清单当"菜单"传进 `tools=TOOLS`，模型吐 `tool_calls` JSON"点菜"，`run_tool` 执行，结果塞回对话再进下一轮（≤6 轮，agentic loop）。
- **工具分两层**：① `agent/core.py` 硬编码 7 个工具；② `lab_tools.py` 插件注册表（`@tool` 装饰器自注册，`openai_tools()` 导出，`call()` 分发，`present` 函数决定卡片外观）。
- **"知识库"真相：没有 RAG**。`web/knowledge/`、`web/memory/` 目录只有 README。所谓"知识"= ① 长期记忆（SQLite `memories` 表注入 prompt）② 试剂安全库（`HazmatStore`，PubChem 数据）③ 实验方案库（`ProtocolStore`，JSON）。全是**查表**，不是文档检索。真正的 RAG（`KnowledgeBase` 协议）在 `PROJECT_ARCHITECTURE.md` 第九节规划，未实现。

---

## 7. 前端入口散落根因

**没有构建工具、没有模块系统**：`web/frontend/` 28 个文件是独立 IIFE（`(function(){...})()`）脚本，靠 `app.py` 的 `page.replace('</body>', scripts)` 字符串拼装注入。每个脚本 `document.createElement` 自画按钮、自挂 fetch，没有统一入口清单。

造成的具体 bug（`VOICE_WEB_MIGRATION_PLAN` §5.3 VOICE-ENTRY-01 已登记）：

- 两个冗余"对话"入口（`vad_mode.js` 的「语音对话」+ `avatar.js` 头像点击）职责重叠。
- `phone_call.js` 的 `$('#sh-call')` 因 `$` 封装成 `getElementById`（不认 `#` 前缀）恒为 null，通话按钮 onclick 从未接上。
- `index.html` 内联巨型脚本与 `composer.js` 画的输入区并存，`composer.js` 专门写代码隐藏旧表单。

---

## 8. 迁移进度与边界

- **当前卡点**：`VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 第 1 步 **C5 语音输出受控**（话术统一 + TTS 硬截断 + no_action 反馈）待做；后续 C4 噪音治本、C3 barge-in 真机、Phase D 命令处理迁入、Phase E 收尾。
- **明确不做**：全双工、CLI 终端 UX 镀金、在薄字典上另立平行投影、提前通用化 QUERY/DENY、把执行工具收敛进统一链。
