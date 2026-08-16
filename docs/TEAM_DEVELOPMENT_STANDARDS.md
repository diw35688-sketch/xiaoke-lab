# 团队开发标准（统一技术栈）

> 目的：避免不同成员各写各的技术栈、各写各的目录，导致后续无法合并。
> 所有人必须按本文档执行；新成员先读本文件。

## 1. 技术栈（锁定）

| 层 | 标准 |
|---|---|
| 后端 | Python 3.12 + FastAPI + Uvicorn |
| 前端 | 原生 JavaScript（无 React/Vue，无构建步骤） |
| 样式 | 原生 CSS / CSS Variables，统一用 `web/frontend/theme.css` 的 token |
| 数据库 | SQLite（`web/lab_agent.db`），禁止换其他数据库 |
| ASR | SenseVoiceSmall（FunASR / ModelScope） |
| TTS | 浏览器 TTS 或 `/tts` 供应商接口 |
| 隧道 | cloudflared quick tunnel（项目内 `bin/cloudflared.exe`） |
| 包管理 | `pip` + `requirements.txt` / `web/requirements.txt` |

禁止引入：React、Vue、TypeScript、Webpack、Node 后端、MongoDB、MySQL。

## 2. 目录职责（禁止乱放）

| 路径 | 职责 |
|---|---|
| `src/` | 领域核心逻辑、纯函数、测试最多的部分 |
| `web/` | FastAPI 装配、前端页面、工具注册表 |
| `web/api/` | 仅 HTTP 接口，不写业务规则 |
| `web/database/` | SQLite 存取层 |
| `web/frontend/` | 原生 JS / CSS / HTML |
| `data/` | 方案库、试剂安全库、外部数据许可台账 |
| `models/` | 模型缓存（VAD、wakeword、ASR modelscope_cache） |
| `bin/` | cloudflared.exe 等内置可执行文件 |
| `results/` | 运行产生的 JSONL 结果 |
| `tests/` | 单元测试 |
| `docs/` | 设计、交接、标准文档 |

## 3. 分层铁律

- `web/` 不做业务判断，只负责装配和转译。
- 所有业务规则必须放在 `src/`，并由测试保护。
- 入口文件（`app.py`、`start_best.py`）只做启动/装配，不写业务逻辑。

## 4. 前端规则

- 原生 JS，使用 `var/function` 或现代 ES 均可，但**必须保持同一文件内风格一致**。
- 不要引入构建工具；不要写 `.jsx/.ts/.vue`。
- UI 里所有功能必须可见、可操作；**不要做成启动脚本入口**。
- 长期隐藏的元素写进 CSS，不要用 JS 设 `style.display='none'`（会被定时刷新覆盖）。
- 所有中文字符串使用 UTF-8，禁止在 `.md/.json` 中出现 `?` 乱码。

## 5. 后端规则

- 路由只做参数校验和调用 `domain` / service。
- 新增能力优先做 `@tool` 插件，参考 `web/lab_tools.py`。
- 数据库迁移用 `web/database/db.py` 的 `initialize_database()` 增量建表/加列。
- 外部服务（LLM/ASR/TTS）失败不能破坏核心功能。

## 6. 模型与数据

- 模型缓存固定放 `models/modelscope_cache`，不写系统盘。
- `web/settings.json` 只存运行时配置，不进版本库。
- `lab_agent.db` 可保留本地开发数据，但不要提交到仓库。

## 7. 测试标准

- 测试放在 `tests/`，命令：
  ```powershell
  cd D:\me\ai107
  .\.venv\Scripts\python.exe -B -m unittest discover
  ```
- 每个测试只验证一个行为，覆盖正常/边界/失败。
- 文件测试用临时目录，不污染真实数据。
- 改动 `src/` 必须保证相关测试全绿。

## 8. Git / 提交标准

- 分支命名：`feature/xxx`、`fix/xxx`。
- 提交信息格式：
  ```
  [模块] 简述
  详情...
  ```
- 不要提交：
  - `.venv/`
  - `__pycache__/`
  - `dist/`
  - `build/`
  - `web/settings.json`
  - `web/certs/`
  - `web/lab_agent.db`（可选）
  - `results/`（如需保留请单独说明）

## 9. 打包/发布标准

- 最终发布用 `scripts/build_exe.py` 生成 `dist/AI107LabAssistant/`。
- 最终用户只双击 `AI107LabAssistant.exe`。
- 所有模型、cloudflared、依赖必须随包内置，禁止让用户下载。
- 源码包用 `scripts/package.py` 生成，排除 `.venv`、`dist`、`build` 等。

## 10. 交接与文档

- 每轮结束更新：
  - `docs/PROJECT_TASK_CHECKLIST.md`
  - `LEARNING_REVIEW_FROM_DEVELOPMENT.md`
  - `docs/NEXT_SESSION_HANDOFF_2026-08-09.md`
- 文档中文化，编码必须是 UTF-8。

## 11. 禁止事项

- 禁止一个人用一种技术栈、另一个人用另一种。
- 禁止直接在 `data/protocols/*.json` 手写未校验数据；必须走 AI 草稿 + 严格校验 + 保存。
- 禁止绕过 UI 让用户手动改配置文件/启动脚本。
- 禁止把 API Key 写进代码或提交到仓库。
