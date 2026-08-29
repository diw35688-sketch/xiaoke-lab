# 语音启动与流式 TTS：从“文字出来了却迟迟不说话”到可见启动进度

> 本文只整理本次对话区讨论和实现的内容：流式 TTS、启动预热、欢迎语、可见进度、时间与模式播报、语速传递、服务重启和验证方法。它不是整个语音模块的完整说明。

## 1. 先用一句白话讲清楚

原来的问题不是“句子太长”，而是系统要等云端把整段音频做完、下载完，浏览器才开始播放。把一句话切得再短，也仍可能在每句开头付一次网络和合成等待，所以会出现文字已经显示、语音却慢几秒，或者句间停顿很长。

这次采用的唯一正式方案是：

1. 网页打开时就并行准备云端 TTS、Silero 人声检测、麦克风和本地 ASR。
2. 云端 TTS 改为流式返回 PCM 音频，浏览器收到第一块音频就开始播放，不等整句话生成完。
3. 页面显示真实的 0/4 到 4/4 启动进度。
4. 欢迎语也必须经过正式 `voice_delivery` 授权，不能私下调用第二个播放器。
5. 浏览器只传本地小时、分钟和模式，欢迎文案由后端生成。
6. 语速作为单条语音的受控字段贯穿整条链路，而不是临时修改全局播放器。

## 2. 这次对话解决了哪些问题

### 2.1 文字为什么比语音先出来

文字和语音走的是两条不同耗时链：

```text
文字：模型结果 → 页面显示

语音：模型结果 → 语音授权 → 请求云 TTS → 云端合成 →
      音频传回浏览器 → 解码/排队 → 扬声器播放
```

因此“页面已有文字”只证明文字链路完成，不代表音频已经生成。

### 2.2 为什么把第一段切短也不够

切短只能减少“这一段需要合成多少字”，不能消除以下固定开销：

- 建立网络连接；
- 云端开始合成；
- 等到第一个可播放音频包；
- 浏览器创建并调度音频缓冲区。

如果每个短句都重新经历固定开销，句间反而更容易产生明显停顿。真正需要优化的是“多久拿到第一块音频”，专业上常称为 **Time To First Audio，首音频延迟**。

### 2.3 为什么流式 TTS 有效

非流式方式像“整桶水装满后再倒”；流式方式像“水一流出来就开始接”。

本项目采用：

```text
火山 WebSocket 流式 TTS
        ↓ PCM 小块
FastAPI /tts/stream
        ↓ HTTP 流
浏览器 ReadableStream
        ↓
Web Audio API 排队播放
```

音频格式为 `pcm_s16le`、24 kHz、单声道、16 位。PCM 不需要等待完整 MP3 文件封装后再播放，适合边收边播。

## 3. 总体专业设计

### 3.1 一条播放路径原则

本次最重要的架构约束是：**只有 `voice_delivery` 可以授权播放。**

页面上的文字、状态卡、后台任务结果都不能因为“看起来需要播报”就直接调用 `window.speak()` 或 `enqueueSpeech()`。否则会形成两条播放路径：一条受调度器管理，一条绕过调度器。两条路径会造成重复播放、抢话、无法正确打断和状态不同步。

正式路径如下：

```text
后端生产 VoiceDeliveryItem
        ↓
PlaybackScheduler 判断 READY / DEFERRED / DROP / PREEMPT
        ↓
voice_delivery 事件
        ↓
voice_delivery_client.js 校验授权和来源 Block
        ↓
local_tts.js 请求 /tts/stream
        ↓
Web Audio 播放
```

`source_block_id` 把语音绑定到一个已经可见的页面 Block。这样系统能够证明“这段声音是在朗读哪一条可见内容”，而不是播放无来源的声音。

### 3.2 启动任务并行，而不是串行等待

网页打开后同时启动四项工作：

| 启动项 | 白话解释 | 真实完成信号 |
|---|---|---|
| 云端语音 | 提前连上 TTS，减少第一次说话握手等待 | `tts_warmup` ready |
| Silero 资源 | 加载人声检测脚本、WASM 和 ONNX 模型 | `silero_assets` ready |
| 麦克风与检测实例 | 请求权限并创建 `MicVAD` | `microphone` ready |
| ASR | 加载 SenseVoice 识别模型 | `asr_warmup` ready |

并行意味着总时间接近最慢的那一项，而不是四项耗时相加。实测中 ASR 是最长项，曾约为 20.8 秒到 30.3 秒；但欢迎语和 TTS 不需要等 ASR 完成。

### 3.3 可见进度来自真实任务，不来自按钮动画

`call_silero_vad.js` 和 `phone_call.js` 在任务真正成功或失败时发送：

```javascript
new CustomEvent('lab:voice-startup-progress', {
  detail: { component: 'microphone', state: 'ready' }
})
```

`voice_startup_ui.js` 监听事件并更新状态卡，因此 3/4 的含义是确实有三项完成，不是预先写好的计时动画。

这也是为什么受限环境拒绝 ASR 运行库和云网络时，页面会诚实显示“部分功能异常”，而不是错误地显示 4/4。

## 4. 启动欢迎语的数据如何流动

### 4.1 浏览器传什么

浏览器读取用户电脑的本地时间，只传结构化数据：

```json
{
  "conversation_id": null,
  "source_block_id": "turn-startup-...:voice-startup",
  "local_hour": 20,
  "local_minute": 5,
  "mode": "free"
}
```

为什么不让前端直接传完整欢迎文案？因为如果前端可以传任意 `speech_text`，就等于把正式语音生产权交回前端，容易再次绕过业务约束。现在前端只报告事实，后端负责决定说什么。

### 4.2 后端怎样生成文案

`web/api/voice_runtime.py` 中的 `VoiceStartupRequest` 限制：

- 小时只能是 0–23；
- 分钟只能是 0–59；
- 模式只能是 `chat`、`free`、`protocol`。

`create_voice_startup()` 再生成类似文案：

```text
晚上好，现在是20点05分，当前为自由实验记录。
```

分钟使用两位格式，所以 5 分会读作 `05分`。随后后端创建 `VoiceDeliveryItem`，交给 `PlaybackScheduler` 授权，而不是直接合成声音。

### 4.3 当前代码与本次对话结论的差异

本次对话中最后一次决定是把欢迎语从 0.85 调回固定 1.0 倍。当前工作区后来又有演进：`create_voice_startup()` 现在使用：

```python
speech_rate=settings_store.current().tts_speed
```

也就是说，**当前代码实际行为是欢迎语跟随全局 TTS 语速设置**，不再固定写死为 1.0。阅读旧对话和新代码时，应以当前代码为准。

## 5. 语速参数如何穿过完整链路

语速不是只在页面播放器里乘一个数字。它经过以下层级：

```text
VoiceDeliveryItem.speech_rate
        ↓
PlaybackRequest.speech_rate
        ↓ 调度后仍保留
voice_delivery.items[].speech_rate
        ↓
voice_delivery_client.js → runtime.speechRate
        ↓
local_tts.js → POST /tts/stream { text, speed }
        ↓
TTSRequest.speed 校验 0.5–2.0
        ↓
VolcanoStreamConfig.speed
        ↓
火山请求 speed_ratio
```

这种设计的优点是：

- 单条语音可以有自己的语速；
- 调度器延后再播放时不会丢失语速；
- 后端会拒绝超出 0.5–2.0 的异常值；
- 不必临时修改全局设置，也不会影响队列里的其他语音。

## 6. 代码对照阅读路线

建议按数据流顺序阅读，而不是随机翻文件。

### 第一步：看启动页面怎样建立 0/4 状态

文件：`web/frontend/voice_startup_ui.js`

重点看：

- `states`：四项初始状态；
- `payload()`：计算完成数量和是否异常；
- `publish()`：写入 `system_status` Block；
- `lab:voice-startup-progress` 监听器；
- `POST /voice/runtime/startup` 的小时、分钟和模式字段；
- 返回后只调用 `consumeVoiceDelivery()`，不直接调用播放器。

### 第二步：看谁发出真实进度

文件：`web/frontend/call_silero_vad.js`

重点看：

- `progress()`：统一发送进度事件；
- `preloadSileroVad()`：加载本地 Silero 资源；
- `preloadVoiceStack()`：并行执行 ASR、Silero 和 TTS 预热；
- 页面加载后的 `setTimeout(...preloadVoiceStack...)`。

文件：`web/frontend/phone_call.js`

重点看：

- `prepareSileroCapture()`：创建带麦克风权限的 `MicVAD`；
- 成功和失败时发送 `microphone` 进度；
- `prepareOnPageLoad()`：网页打开就准备，不等用户点击连续通话。

### 第三步：看后端如何生产正式欢迎语

文件：`web/api/voice_runtime.py`

重点看：

- `VoiceStartupRequest`；
- `create_voice_startup()`；
- 时间段和模式映射；
- `VoiceDeliveryItem`；
- `web_playback_service.authorize()`。

### 第四步：看调度过程为何不丢字段

文件：`src/core/presentation_delivery.py`

`VoiceDeliveryItem` 是已经具备语音资格的内容合同。它验证文字、优先级、来源 Block 和 `speech_rate`。

文件：`src/core/playback_request.py`

`PlaybackRequest` 在内容合同上增加创建时间、有效期和替代关系等播放生命周期信息。`from_delivery_item()` 必须复制 `speech_rate`。

文件：`web/playback_runtime.py`

`WebPlaybackService.authorize()` 调用调度器；`_item_from_request()` 在调度结果重新转成网页事件时仍要复制 `speech_rate`。如果这里漏掉字段，语速会在“延后播放”或“重新序列化”时恢复默认值。

### 第五步：看浏览器怎样接受授权

文件：`web/frontend/voice_delivery_client.js`

重点看：

- 只接受 `READY` 或 `PREEMPT`；
- 校验 `source_block_id` 是否属于当前 Turn；
- `runtimeHooks()` 把 `speech_rate` 转成 `speechRate`；
- 按顺序上报 `tts_started`、`tts_finished`、`tts_stopped`、`tts_failed`。

### 第六步：看流式音频怎样边收边播

文件：`web/frontend/local_tts.js`

重点看：

- `streamAndPlay()` 请求 `/tts/stream`；
- 请求体带 `{text, speed}`；
- `response.body.getReader()` 逐块读取；
- `pcm16ToFloat32()` 把 16 位 PCM 转成 Web Audio 数据；
- `schedulePcm()` 连续排入音频时间线；
- `stopSpeech()` 中止请求并停止已排队音频，实现打断。

文件：`web/api/tts.py`

重点看：

- `TTSRequest.speed` 的 0.5–2.0 校验；
- `/tts/stream` 用单次请求速度覆盖配置副本；
- `StreamingResponse` 返回 PCM 格式头。

文件：`web/volcano_streaming_tts.py`

最终会把速度写入火山协议的 `speed_ratio`，并从 WebSocket 持续取得音频块。

## 7. 如何读启动计时数据

页面把启动时间保存在：

```javascript
window.__voiceStartupTimings
```

典型结果：

```json
{
  "silero_assets_ms": 571,
  "tts_warmup_ms": 1591,
  "silero_model_init_ms": 999,
  "silero_permission_init_ms": 1566,
  "asr_warmup_ms": 20823,
  "voice_stack_total_ms": 20825,
  "ready": true
}
```

解释：

- Silero 静态资源约 0.57 秒；
- TTS 预连接约 1.59 秒；
- 麦克风和 Silero 实例约 1.57 秒；
- ASR 最慢，约 20.8 秒；
- 总时间约 20.8 秒，证明任务是并行的，因为总时间基本等于最慢项。

点击连续通话时曾测得：

```json
{"call_click_to_ready_ms": 13}
```

这说明准备工作已在网页打开阶段完成，点击按钮不再重新等待模型加载。

### 播放延迟数据

流式播放样本保存在：

```javascript
window.__voiceTimingSamples
```

冷启动欢迎语曾测得：

```json
{
  "first_audio_chunk_ms": 1393,
  "first_chunk_to_play_ms": 31,
  "delivery_to_play_ms": 1522
}
```

这表示：

- 云端冷连接到第一块音频约 1.39 秒；
- 浏览器收到第一块后约 31 毫秒开始播放；
- 从正式授权到播放约 1.52 秒。

因此当时的主要等待在云端首块音频，不在浏览器播放调度。后续连接预热后，正式对话曾测得约 311–360 毫秒的授权到播放延迟。

## 8. 为什么修改代码后经常要重启服务

### 白话解释

Python 服务启动时会把代码加载进进程内存。磁盘文件虽然改了，已经运行的旧进程仍可能执行旧代码。重启是让新进程重新读取修改后的 Python 文件。

### 哪些改动需要什么操作

| 改动 | 通常需要 |
|---|---|
| Python 后端 | 重启 Uvicorn |
| JavaScript、CSS、HTML | 刷新网页 |
| 前端缓存仍是旧版 | 强制刷新或更新资源版本号 |
| 模型、依赖、环境变量 | 通常重启服务 |

### 本项目的安全手动重启思路

先确认谁占用 8000 端口：

```powershell
netstat -ano -p tcp | Select-String ':8000'
```

只停止已确认的旧进程：

```powershell
Stop-Process -Id <确认过的进程号> -Force
```

再从 `web` 目录启动当前代码：

```powershell
cd C:\Users\dahli\Documents\107\web
..\.runtime-python311\python.exe -m uvicorn app:app `
  --host 127.0.0.1 `
  --port 8000
```

开发时可使用 `--reload` 自动重载，但这个项目加载 ASR 模型较慢，每次 Python 文件变化都可能触发模型重新加载，所以本次采用“完成一批修改和测试后手动重启一次”。

## 9. 本次验证证据与边界

### 已证明

- `/voice/runtime/startup` 能返回正式 `READY` 授权；
- 欢迎语携带可追踪的 `source_block_id` 和语速；
- 页面真实显示 0/4 到 4/4；
- ASR、Silero、麦克风、TTS 在网页打开时并行准备；
- 全新 Edge 冷启动中获得了真实 PCM 播放计时；
- 受限环境失败时，页面能显示具体异常而不是假装成功；
- 相关阶段曾完成 43/45 项后端回归和多组前端语音测试。

### 没有被这些证据自动证明

- 每一种网络环境下都能低于 1 秒；
- 所有真实麦克风和声卡都没有兼容性问题；
- 云端 TTS 永远不会抖动；
- 自动化测试等同于人的主观听感。

用户实际试听后认为 0.85 倍偏慢，并选择 1.0，属于主观体验验收；这类结论不能只靠单元测试决定。

## 10. 常见故障如何判断

### `/tts/stream` 返回 404

通常说明浏览器访问的仍是未包含新路由的旧服务。先确认 8000 端口进程，再重启当前代码，不要只反复刷新网页。

### 页面显示 3/4

看状态卡里哪一项“未就绪”，再检查：

```javascript
window.__voiceStartupTimings
```

3/4 不是统一错误码，而是四个真实任务中有一项失败或未完成。

### 欢迎语没有声音

依次检查：

1. `/voice/runtime/startup` 是否返回 `voice_delivery`；
2. `authorization` 是否为 `READY` 或 `PREEMPT`；
3. `source_block_id` 是否对应当前可见 Block；
4. `/tts/stream` 是否成功返回；
5. `window.__voiceTimingSamples` 是否出现样本；
6. 控制台是否有 `PLAYBACK_DISABLED`、`REJECTED_PAYLOAD` 或云 TTS 错误。

### ASR 又要等待约半分钟

这是后端进程冷启动后首次导入运行库和加载模型的成本。网页预热把等待提前到了页面打开阶段，但如果 Python 服务刚重启，模型仍需要在新进程里重新加载。

## 11. 新手应该记住的五条工程原则

1. **先测阶段，不要只测总时间。** 文字显示、语音授权、请求发出、首块音频和真正播放必须分别计时。
2. **流式不是把文字切碎。** 真正的流式是音频生成多少就传多少、收到多少就播多少。
3. **状态必须来自真实生产者。** 进度条应由任务完成事件驱动，而不是按钮点击后假装前进。
4. **播放必须只有一个授权入口。** 欢迎语、聊天回复和实验反馈都应走同一个 `voice_delivery` 调度链。
5. **区分代码测试与真实体验。** 测试证明合同没有断；冷启动浏览器证明真实链路接通；最终语速是否舒服仍要靠人试听。

## 12. 最短复习路径

如果以后只用十分钟复习，按这个顺序：

1. `voice_startup_ui.js`：页面显示什么、发送什么。
2. `voice_runtime.py`：后端决定欢迎语并生产授权。
3. `presentation_delivery.py`：语音项合同。
4. `playback_runtime.py`：调度授权。
5. `voice_delivery_client.js`：浏览器只接受正式授权。
6. `local_tts.js`：请求流式音频并边收边播。
7. `tts.py` 与 `volcano_streaming_tts.py`：速度和云端协议。
8. `probe_voice_startup.py`：如何取得真实页面证据。

读代码时始终追问这一条链：

```text
事实由谁产生 → 谁转换 → 怎样传输 → 谁接收 → 写入什么状态 →
谁读取状态 → 用户最终看到或听到什么
```

只看到同名字段或测试通过，还不能证明整条链已经接通。
