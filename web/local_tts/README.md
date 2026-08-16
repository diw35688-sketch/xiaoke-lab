# 本地 Qwen TTS 模块

- `engine.py`：加载 Qwen3-TTS 模型、参考音频与克隆提示。
- `.env`：本机模型路径与参考音频逐字稿；不要提交或分享。
- `.env.example`：配置模板。
- `requirements.txt`：运行本地声音服务所需依赖。

参考音频固定放在项目根目录的 `voice/reference.wav`，生成音频固定保存到 `voice/outputs/`。
启动服务请在项目根目录执行：

```cmd
uvicorn tts_server:app --host 127.0.0.1 --port 8001
```
