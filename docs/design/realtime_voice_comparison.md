# 实时语音交互对比：QwenAudio/qwen-audio-agent vs 本项目

## 参考代码位置

```text
D:\me\ai107\_qwen-audio-agent\web\src\useRealtimeVoice.js
D:\me\ai107\_qwen-audio-agent\web\src\microphone-capture.js
D:\me\ai107\_qwen-audio-agent\web\src\audio.js
D:\me\ai107\_qwen-audio-agent\web\src\playback-lifecycle.js
D:\me\ai107\_qwen-audio-agent\web\src\voice-defaults.js
D:\me\ai107\_qwen-audio-agent\shared\realtime-events.mjs
D:\me\ai107\_qwen-audio-agent\server\src\**（Gateway 实时语音后端）
```

---

## QwenAudio 方案

### 输入
```text
麦克风 → ScriptProcessor(2048)
      → 重采样到 16kHz
      → PCM 转 base64
      → WebSocket AUDIO_APPEND 持续上传
```

- 麦克风生命周期独立：设备切换、track ended/muted、自动重试
- 不是“说完一整段再识别”，而是**持续音频流**交给服务端 VAD/ASR
- 有手动输入（文字/图片）与语音的仲裁状态

### 输出
```text
服务端 AUDIO_DELTA（PCM base64）→ Web Audio 播放
AUDIO_DONE → 播放结束
```

- 有 `responseId` 级别的播放生命周期：
  - PLAYBACK_STARTED
  - PLAYBACK_ENDED
  - PLAYBACK_CANCELLED
- 说话打断（barge-in）：
  ```text
  VOICE_STATE=listening → stopPlayback('user_interruption')
  ```
- 多客户端语音所有权仲裁
- 重连、暂停/恢复、静音、唤醒词等状态机

---

## 我们现在的方案

```text
输入：浏览器 Silero VAD 检测端点 → 整段 WAV 发给服务端 SenseVoice
输出：TTS 流（HTTP/WebSocket）→ local_tts.js 播放
语音：phone_call.js 独立呼叫链路
```

- 输入是**整段式**：VAD 说“说完了一句话”再识别
- 输出播放有基础，但**没有 responseId 级别的完整生命周期**
- 缺少设备切换自动恢复、track ended/muted 重试
- 缺少多客户端麦克风所有权仲裁
- 缺少像 QwenAudio 这样完善的播放确认/取消/打断反馈

---

## 结论

### 不能整体直接复制的原因
QwenAudio 的 `useRealtimeVoice.js` 和它的 Gateway 协议、服务端实时语音后端强耦合：
```text
shared/realtime-events.mjs
shared/gateway-client-sdk.mjs
server/src/...（Gateway 实时后端）
```
我们后端是 FastAPI + 自己的 ASR/VAD/TTS，不可能是同一套协议。

### 可以复制/改写的部分

| 模块 | 动作 |
|---|---|
| `audio.js`（resample / pcmBase64 / decodePcm） | **直接复制**，纯前端无依赖 |
| `microphone-capture.js`（麦克风生命周期） | **改写成我们的前端**，几乎整体可复用 |
| `useRealtimeVoice.js` 播放生命周期 | **改写移植**：拿走 responseId、PLAYBACK_STARTED/ENDED/CANCELLED、barge-in |
| `useRealtimeVoice.js` 输入仲裁/所有权 | **参考状态机**，不直接搬 WebSocket 协议 |
| Gateway 后端 | **不复制**，只借鉴事件契约 |

---

## 建议落地顺序

1. 复制 `audio.js`
2. 改写 `microphone-capture.js` 到我们前端（设备切换/自动恢复）
3. 给我们的 TTS/语音播放增加：
   - responseId
   - PLAYBACK_STARTED / ENDED / CANCELLED
   - 说话时 interrupt 停止播放
4. 保留现有 Silero VAD + SenseVoice（整段识别），先不改成持续音频流
5. 如果后续要更低延迟，再考虑把输入改成 WebSocket AUDIO_APPEND 持续流
