# 实验助手基础版

这个版本已经实现：文字聊天、浏览器端语音识别（ASR）、文本朗读（TTS）、模型工具调用、安全计算、SQLite 实验记录、仪器/时间冲突检查。

## 目录职责

- `app.py`：服务入口，只注册 API 和初始化数据库。
- `api/`：HTTP 接口。
- `agent/`：模型提示词、工具注册和工具调用循环。
- `tools/`：计算、创建实验、查实验等具体能力。
- `database/`：SQLite 连接、建表与读写。
- `planner/`：排程冲突规则；以后增加任务依赖、材料和日历。
- `knowledge/`、`memory/`、`frontend/`：为下一阶段保留。

## 启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，填入 API Key，然后运行：

```powershell
uvicorn app:app --reload
```

打开 `http://127.0.0.1:8000/docs` 进行测试。

建议依次测试：`GET /health`、`POST /experiments`、`GET /experiments`、`POST /chat`。

主页提供语音输入按钮和“自动朗读助手回复”开关。语音功能使用浏览器原生 Web Speech API，不会由本程序把录音文件保存到服务器。首次使用 ASR 时需要允许浏览器访问麦克风；建议使用新版 Edge 或 Chrome。浏览器原生语音识别的可用性和联网要求取决于浏览器及操作系统。

## 当前边界

- 检测到时间/仪器冲突时，接口会拒绝创建实验。
- 知识库尚未接入，助手不会伪造 SOP 或论文内容。
- 该程序不控制仪器，不替代人工安全确认和实验室 SOP。
