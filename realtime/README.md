# Realtime Voice Engine

小科实验助手的实时语音引擎模块，基于 [QwenAudio/qwen-audio-agent](https://github.com/QwenAudio/qwen-audio-agent)（Apache-2.0）。

## 功能

- 全双工实时语音（DashScope Qwen Audio Realtime API）
- WebSocket 网关 + WebRTC 音频流
- MCP 工具桥接：自动注册 Python 后端的全部工具
- 实验助手适配层（`lab/` 目录）

## 结构

```
realtime/
├── lab/           实验助手适配层（本项目自研）
│   ├── start-lab-gateway.mjs      启动入口
│   ├── lab-assistant-backend.mjs   Python 后台 Adapter
│   ├── lab-mcp-server.mjs          MCP 工具桥
│   ├── ASSISTANT.md                小科人设
│   └── frontend-mcp.json           MCP 配置
├── server/        语音网关核心（基于 qwen-audio-agent）
├── shared/        共享类型与工具
├── web/           浏览器端语音 UI
└── config/        运行时配置
```

## 归属

语音网关核心代码（`server/`、`shared/`、`web/`）源自 [qwen-audio-agent](https://github.com/QwenAudio/qwen-audio-agent) 项目（Apache-2.0），在此致谢。原始许可证见 [LICENSE](LICENSE)。
