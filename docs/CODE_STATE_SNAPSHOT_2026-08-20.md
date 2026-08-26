# 代码现状快照（2026-08-20）

> 目的：记录"杂糅版"（`C:\Users\dahli\Documents\107`）在 2026-08-20 的代码状态，作为后续整理与简历化的基线。
> 本文件只记录**现状是什么**，不做价值判断；理解性结论见 [`ARCHITECTURE_MAP_2026-08-20.md`](ARCHITECTURE_MAP_2026-08-20.md)。

---

## 1. 仓库与分支

| 项 | 值 |
|---|---|
| 仓库根 | `C:\Users\dahli\Documents\107` |
| 分支 | `codex/asr-demo-unified-understanding` |
| 干净权威版 | `C:\Users\dahli\Desktop\asr_demo`（不在本仓库，是"src 我原来写的那份"的出处） |

最近 8 条 commit：

```
77b8731 feat: 手机演示页/火山TTS/设置面板修复/语音体验加固
b9f4e46 [web] update: UI network switch, AI protocol draft, time/timer tools, voice UX
9f22eda docs: reorder remaining PRESENT tasks
4e97fa4 feat:compltet PRESENT delivery and output cleanup
2e7e037 PRESENT 子步 B: 单一输出链路接线 + 真实验收问题登记
fd889f3 PRESENT 子步 A: 会话级呈现纯函数链路（Intent/文案/渲染/投影）+ answer 结构化字段
2d290ab docs: 新增 ENGINEERING_FIRST_POLICY 总纲（demo与工程同步）+ CLAUDE.md 引用
c242dac docs: 新增根目录 README 项目介绍
```

---

## 2. 目录结构

```
107/  （git 仓库根）
├── src/            # CLI 统一理解链（用户本人写的部分）
│   ├── main.py     #   组合根 + 会话循环（20KB）
│   ├── config.py   #   集中配置
│   ├── core/       #   领域逻辑层（26 文件：纯数据合同 + 规划器）
│   ├── asr/        #   语音识别后端（SenseVoice）
│   ├── audio/      #   音频采集（VAD + 预录制）
│   ├── llm/        #   LLM 客户端 + 统一理解处理器
│   ├── storage/    #   JSONL 持久化
│   ├── wakeword/   #   唤醒词
│   └── evaluation/ #   离线评估
├── web/            # 网页产品（组员做的部分，含对 src 的三座桥）
│   ├── app.py      #   FastAPI 入口，挂 11 个路由
│   ├── agent/core.py    #  tool-calling 对话大脑（/chat）
│   ├── api/        #   record/chat/tts/protocols/experiments/... 路由
│   ├── database/   #   SQLite（crud/db/lab_record_store/memory_store/task_store）
│   ├── frontend/   #   无构建的 28 个 JS/HTML（入口散落在此）
│   ├── lab_tools.py     #  插件式工具注册表（9 个 @tool）
│   ├── tools/      #   calculator/experiment_tools/memory_tools
│   ├── planner/    #   conflicts/templates
│   ├── tasks/      #   后台任务队列（ThreadPoolExecutor）
│   ├── realtime/   #   后台任务路由判断（正则）
│   ├── local_tts/  #   TTS 引擎
│   ├── llm_bridge.py    #   桥①：接 src 统一理解
│   ├── domain.py        #   桥②：接 src 方案评估/安全
│   ├── degraded_producer.py  # 桥③：接 src 呈现层（降级生产者）
│   ├── web_renderer.py       # 桥③：接 src 呈现层（渲染器）
│   └── knowledge/  #   只有 README（无知识库实现）
├── tests/          # 测试（含 4 个未跟踪的新测试）
├── docs/           # 文档（3 份超大过程文档见 §5）
├── audio/          # 录音
├── data/           # 协议 JSON 等
├── results/        # JSONL 证据
├── models/         # 本地模型
├── scripts/  bin/  pre/  evaluation/   # 辅助
└── 一堆 .bat / dump 文件（见 §4）
```

---

## 3. 工作区改动状态（`git status --short`，2026-08-20）

### 已修改未提交（M）—— 30 个文件

**src/（用户侧核心，9 个）**
```
src/main.py
src/core/clarification_acceptance.py
src/core/clarification_executor.py
src/core/interaction_command.py
src/core/presentation_copy.py
src/core/presentation_projection.py
src/core/reply_coordinator.py
src/core/unified_observer.py
src/core/unified_prompts.py
src/core/unified_understanding.py
```

**web/（组员侧 + 桥，15 个）**
```
web/app.py
web/agent/core.py
web/api/record.py
web/llm_bridge.py
web/frontend/avatar.js
web/frontend/composer.js
web/frontend/lab_panel.js
web/frontend/local_tts.js
web/frontend/mobile.html
web/frontend/mobile.js
web/frontend/phone_call.js
web/frontend/speak.js
web/frontend/vad_mode.js
web/frontend/voice_asr.js
```

**tests/（3 个）**：`test_clarification_executor.py`、`test_presentation_copy.py`、`test_web_mobile_page.py`

**docs/（4 个）**：`CLAUDE.md`、`LEARNING_REVIEW_FROM_DEVELOPMENT.md`、`NEXT_SESSION_HANDOFF_2026-08-09.md`、`PROJECT_ARCHITECTURE.md`、`PROJECT_TASK_CHECKLIST.md`

### 未跟踪（??）—— 10 个

```
2026-08-20-005939-get-indexhtml-7.txt      # 抓包产物（69KB），疑似误留
docs/VOICE_WEB_MIGRATION_PLAN.md
docs/VOICE_WEB_MIGRATION_PLAN_2026-08-20.md
tests/test_degraded_producer.py
tests/test_observation_partial.py
tests/test_web_record_messages.py
tests/test_web_renderer.py
web/degraded_producer.py                   # 桥③ 之一（迁移新增）
web/web_renderer.py                        # 桥③ 之二（迁移新增）
```

> 观察：**新增的降级生产者/渲染器（`degraded_producer.py`、`web_renderer.py`）和它们的 4 个测试都还没 `git add`**，是"迁移进行到一半"的直接证据。

---

## 4. 根目录散落文件（不属于 src/web/docs/tests 的杂物）

| 文件 | 说明 |
|---|---|
| `2026-08-20-005939-get-indexhtml-7.txt` | 69KB 抓包 HTML，疑误留 |
| `home_dump.html` | 17KB 页面 dump |
| `check_vad_mode.py` | 临时诊断脚本 |
| `launcher.py` | 启动器 |
| `build_exe.bat` / `package.bat` / `upload.bat` / `start*.bat` ×8 / `install*.bat` ×2 / `debug_*.bat` ×2 / `setup_and_start.bat` | 15+ 个 .bat 脚本 |
| `.env` / `.env.example` | 配置（.env 不应提交） |

---

## 5. "乱"的三个来源（事实记录，非评判）

1. **过程文档爆炸**：`LEARNING_REVIEW_FROM_DEVELOPMENT.md`（344KB）、`PROJECT_TASK_CHECKLIST.md`（205KB）、`NEXT_SESSION_HANDOFF_2026-08-09.md`（55KB）——价值高，但是"给维护者看的流水账"，不是"给陌生人看的地图"。

2. **双轨过渡期**：`src/`（CLI 统一链）与 `web/`（网页 agent）两套"大脑"并行，迁移进行到一半（`VOICE_WEB_MIGRATION_PLAN_2026-08-20.md` 第 1 步 C5 待做，Phase D 未开始）。过渡中间态天然显得乱。

3. **前端无构建**：`web/frontend/` 28 个文件是独立 IIFE 脚本，靠 `app.py` 字符串 `replace` 拼装注入，每个脚本自画按钮自挂事件，入口散落、有重叠与失灵 bug（详见 ARCHITECTURE_MAP §7）。
