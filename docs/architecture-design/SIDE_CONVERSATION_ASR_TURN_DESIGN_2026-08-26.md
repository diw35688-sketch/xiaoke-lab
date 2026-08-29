# 侧边对话完整记录：ASR、Turn 与六步泛化设计（2026-08-26）

> 导出范围：从本次侧边对话边界后的第一条有效用户问题开始，截止“把侧边聊天的记录完整的导出为markdown”这一请求。
>
> 仅收录用户与助手的对话正文；不收录内部推理、工具调用参数、命令输出和边界之前继承的主线程历史。为避免递归，本文件不包含生成完成后的助手交付回复。

---

## 对话 1

### 用户

> **选中文本：**
>
> 当前最合理的选择是：ASR、模型判断等不可变证据：可以继续使用 JSONLWeb 用户可见的实验记录和历史查询：继续使用现有 SQLite不让六步链和 /record 各自独立生成一份“最终实验记录”只有 SQLite 业务保存成功后，页面才显示“已记录”所以我们真正要改的是六步链的存储职责和适配方式，不是简单地把 JSON 文件改成 SQLite。

为什么凭什么说这是最合理的选择

### 助手

你质疑得对。“这是最合理的选择”说得太绝对了。根据当前代码，只能说它是一个“改动较小的候选方案”，还不能直接定为最合理。

真正需要比较的是三个方案。

| 方案 | 优点 | 主要问题 |
|---|---|---|
| 全部 JSONL | 简单、可直接查看、适合追加审计 | 查询、并发、幂等、删除、会话恢复都要自己实现 |
| 全部 SQLite，字段保存 JSON | 可以事务提交、唯一约束、查询和重试容易 | 需要给六步链增加 SQLite 存储适配 |
| JSONL + SQLite 双存储 | 保留审计文件，也保留 Web 查询能力 | 两者不能天然处于同一个事务，最容易发生状态不一致 |

## 当时为什么会偏向混合方案

主要依据是现状：

1. Web 已经使用 SQLite 管理用户可见记录。

   当前 `lab_record_store.py` 已经负责：

   - 恢复当前实验会话
   - 分配 `segment_id`
   - 防止段号冲突
   - 按会话查询历史
   - 删除会话记录
   - 页面刷新、服务重启后恢复

2. 终端六步链已经使用 JSONL 保存证据。

   `result_store.py` 适合保存不可变 ASR 证据，结构直观，也方便人工审查。

3. 保留两者看起来改动较少。

所以当时的推理其实是：

> Web 不推翻 SQLite，终端不推翻 JSONL，各自保留擅长的部分。

这属于“降低迁移范围”的判断，不等于架构上天然最优。

## 混合方案其实有一个严重缺点

JSONL 文件和 SQLite 无法放进同一个数据库事务。

例如：

```text
1. ASR JSONL 写成功
2. SQLite 实验记录写失败
```

此时证据文件里有记录，但页面里没有。

反过来：

```text
1. SQLite 写成功
2. JSONL 写失败
```

此时用户看到“已记录”，但完整 ASR 证据缺失。

另外，当前 JSONL `append()`：

- 没有 `request_id` 唯一约束
- 没有跨重启幂等
- 相同请求重试可能重复追加
- 无法与 SQLite 原子提交

因此，如果我们的第一优先级是：

> 一次实验提交必须完整、幂等、可查询，并且成功与失败边界清楚。

那么“JSONL + SQLite 双主存储”反而未必是最合理的。

## 当前更稳妥的建议

对于 Web 正式实验，我现在更倾向：

```text
SQLite
├─ asr_evidence
│   └─ 完整 ASRResult 作为 JSON 保存
├─ experiment_events
└─ lab_records
```

在同一个事务中完成：

```text
BEGIN
  保存 ASR 证据
  保存实验事件
  保存用户可见记录
COMMIT
```

只有 `COMMIT` 成功，页面才显示“已记录”。

这仍然是在保存 JSON，只不过 JSON 被放进 SQLite 容器中，以获得：

- 事务
- 唯一约束
- `request_id` 幂等
- 会话查询
- 失败回滚
- 跨重启重试识别

JSONL 可以继续用于：

- 终端模式
- 调试日志
- 审计导出
- 离线评测数据

但不再与 SQLite 同时充当 Web 正式业务的“主账”。

## 什么时候才应该坚持 JSONL 证据账

只有当我们明确要求：

> 即使 Web 业务数据库损坏、回滚或删除，也必须保留一份独立、只追加、不可修改的原始证据日志。

这时才值得采用双存储，并额外设计：

- outbox
- 幂等键
- 写入状态
- 失败补偿
- 对账工具
- JSONL 与 SQLite 的共同身份

当前项目还没有明确提出这种独立审计等级，因此没必要先承担这套复杂度。

所以更严谨的结论应该改成：

> 现有证据不足以断言“JSONL 保存证据、SQLite 保存业务”最合理。若以 Web 的事务一致性、幂等和查询为优先，完整 ASRResult 以 JSON 形式存入 SQLite，JSONL 只作终端存储或导出，可能是当前更低风险的方案。最终应在持久化设计阶段用失败与重试测试作决定，而不是凭存储格式偏好决定。

---

## 对话 2

### 用户

> **选中文本：**
>
> 普通 chat 听写仍可使用：纯文本语音 → /asr/transcribe → 文字 → /chat/stream

这样合理吗？会不会搞成两条路很乱？还是说就是应当分开，那六步泛化在泛化什么、

### 助手

你的担心是对的。把最终架构设计成：

```text
语音 Chat → /asr/transcribe → /chat/stream
语音实验 → /record/audio → 六步
```

虽然能工作，但确实会形成两套“语音提交编排”：

- Chat 由浏览器串联两次请求
- 实验由服务端一次完成
- 两边的 `request_id`、`turn_id`、模式快照、ASR 失败处理不同
- 以后改 ASR、重试、连续通话时容易分叉

所以它适合做过渡方案，不是最整洁的最终结构。

## 真正应该统一的是输入入口

更清晰的结构是：

```text
                     ┌─ 文字输入
                     │
                     ↓
              统一 TurnInput
                     ↑
                     │
语音输入 → 服务端 ASR → 完整 ASRResult
                     ↓
                 模式分派
              ┌──────┴──────┐
              ↓             ↓
         Chat 处理器     实验六步处理器
              ↓             ↓
              └──────┬──────┘
                     ↓
        ConversationTurn / Block
                     ↓
            统一显示与语音播放
```

这里会有不同的业务处理器，但不会有两套输入链。

## 分开和混乱不是一回事

Chat 和实验本来就有不同业务目的：

| 模式 | 要做什么 |
|---|---|
| Chat | 生成自然语言回答，不落实验记录 |
| 自由实验 | 提取实验事实、保存、必要时追问 |
| 方案实验 | 对照当前步骤、判断缺失和偏差 |
| Control | 查看、暂缓、回答、确认、结束 |

所以分成 `ChatProcessor` 和 `ExperimentProcessor` 是合理的。

真正会乱的是在分派前就各自处理一遍语音：

```text
Chat 自己录音、ASR、重试
实验又自己录音、ASR、重试
```

我们应该统一“输入采集和身份”，再按模式分派业务。

## `/asr/transcribe` 最终应该是什么定位

它可以保留，但只作为纯听写工具：

```text
录一段语音
→ 得到文字
→ 用户可以编辑
→ 尚未正式提交
```

例如：

- ASR 调试页面
- 输入框听写
- 用户想先看文字、修改后再发送
- ASR 模型测试

但如果用户按下的是“直接发送语音”，无论 Chat 还是实验，都不应由浏览器自己串联：

```text
/asr/transcribe → /chat/stream
```

而应该统一提交给服务端语音 Turn 入口：

```text
POST /turn/audio
  ↓
服务端 ASR
  ↓
构造统一 TurnInput
  ↓
根据提交时的模式分派
```

例如：

```text
/turn/audio
├─ interaction_mode=chat
│    → ChatProcessor
└─ interaction_mode=experiment
     ├─ experiment_context=free
     │    → 实验六步
     └─ experiment_context=protocol
          → 实验六步
```

文字输入对应：

```text
POST /turn/text
  ↓
同一个模式分派
```

也可以只有一个 `/turn`，但音频 multipart 和文字 JSON 放在同一个 HTTP 接口里往往比较别扭。两个采集接口、一个应用服务，比强行一个接口更清楚：

```text
/turn/text  ──┐
              ├→ TurnApplicationService → 模式分派
/turn/audio ──┘
```

这不是两条业务链，只是两种输入适配器。

## 那“六步泛化”到底在泛化什么

六步泛化的主要对象是输入来源，不是把 Chat 强行塞进实验业务。

当前六步基本假设：

```text
输入一定来自语音
输入一定有 ASRResult
处理内容一定读取 asr_result.asr_transcript
```

泛化后变成：

```text
输入有统一 raw_text
ASRResult 可以存在，也可以不存在
```

因此：

### 文字实验

```python
TurnInput(
    raw_text="加入五十毫升水",
    input_source="text",
    asr_result=None,
)
```

进入实验六步：

- 理解实验事实
- 保存实验事件
- 生成追问
- 不保存 ASR 证据

### 语音实验

```python
TurnInput(
    raw_text="加入五十毫升水",
    input_source="single_recording",
    asr_result=完整识别证据,
)
```

进入同一个实验六步：

- 保存 ASR 证据
- 理解实验事实
- 保存实验事件
- 生成追问

所以六步泛化的是：

```text
只支持语音实验
        ↓
同时支持文字实验和语音实验
```

它不是：

```text
所有 Chat 回答也必须经过实验实体提取和实验落库
```

## 最合理的分层

最终建议分成三层：

### 第一层：输入统一

```text
文字 → TurnInput
语音 → ASR → TurnInput
```

负责：

- `request_id`
- `turn_id`
- `conversation_id`
- 输入来源
- 模式快照
- 完整 ASR 证据

### 第二层：模式分派

```text
TurnInput
├─ chat → ChatProcessor
└─ experiment → ExperimentProcessor（六步）
```

### 第三层：输出统一

```text
各处理器结果
→ ConversationTurn / Block
→ 唯一 Store
→ 屏幕显示
→ voice_delivery
```

因此，更准确的结论是：

> Chat 和实验应当分开处理业务，但不应分开建设语音采集、ASR、Turn 身份和输出外壳。六步泛化只负责让实验处理器同时接受文字和语音；更外层的 Turn 应用服务负责统一所有模式的入口与分派。

---

## 对话 3

### 用户

怎么不最终把transcribe删掉

### 助手

可以最终删除，而且按照当前产品行为，我倾向于最终删除公开的 `/asr/transcribe`。

之前保留它，是因为考虑到“纯听写、先转文字再编辑”这种可能用途。但核对当前调用后，桌面单录、手机、VAD 和连续通话基本都是：

```text
录音
→ /asr/transcribe
→ 拿到文字
→ 立即自动提交
```

并没有一个明确、独立的“只听写、不提交”产品功能。因此完成统一语音入口后，它会成为容易误用的旧路。

## 最终结构

删除的是 HTTP 接口：

```text
POST /asr/transcribe
```

不删除内部 ASR 能力：

```text
ASRApplicationService
  ↓
ASRBackend
  ↓
SenseVoiceBackend
```

最终调用关系应当是：

```text
/turn/audio
  ↓
ASRApplicationService
  ↓
完整 ASRResult
  ↓
TurnInput
  ↓
模式分派
  ├─ ChatProcessor
  └─ ExperimentProcessor
```

这样浏览器无法再绕回旧的“两次请求”路径。

## 哪些 ASR 接口可以保留

可以继续保留：

```text
GET  /asr/status
POST /asr/warmup
```

因为它们分别负责：

- 查看模型是否可用
- 提前加载模型

它们不会制造第二条业务提交链。

最终变成：

```text
/asr/status       模型状态
/asr/warmup       模型预热
/turn/audio       正式语音提交
/turn/text        正式文字提交
```

## 如果以后真需要“听写后编辑”

那也不建议继续使用含糊的 `/asr/transcribe` 作为正式业务旁路，可以明确命名为：

```text
/dictation/transcribe
```

并规定：

- 只返回草稿文字
- 不创建 Turn
- 不保存实验记录
- 不携带正式提交身份
- 用户编辑后按文字输入重新提交
- 不得用于“直接发送语音”

这样“听写草稿”和“正式语音提交”在语义上不会混淆。

但当前没有明确的听写编辑需求，因此没必要提前保留。

## 删除顺序

不能现在直接删除，因为当前四个前端仍在调用它。正确顺序是：

1. 建立服务端共享 ASR 服务。
2. 建立 `/turn/audio`。
3. 迁移桌面单次录音。
4. 迁移手机页。
5. 迁移连续通话。
6. 迁移 VAD。
7. 全仓搜索确认没有 `/asr/transcribe` 调用。
8. 删除路由及旧合同测试。
9. 保留 `/asr/status`、`/asr/warmup`。
10. 跑自动回归和真实录音验收。

最终结论：

> 如果没有“只听写、不提交”的明确用户功能，`/asr/transcribe` 最终应当删除；保留它只会给旧的前端两段式链路留下复活入口。删除的是公开转写路由，不是 ASR 能力层。

---

## 对话 4

### 用户

哦，聊天和实验是不同的业务模式，文字和语音是不同的输入方式，有点正交的感觉

### 助手

对，正是这个关系。可以看成两个正交维度。

| 业务模式 ↓ / 输入方式 → | 文字 | 单次录音 | 连续通话 |
|---|---:|---:|---:|
| 自由聊天 | ✅ | ✅ | ✅ |
| 自由实验 | ✅ | ✅ | ✅ |
| 方案实验 | ✅ | ✅ | ✅ |

输入方式回答：

> 用户怎么把这句话交给系统？

```text
文字
单次录音
连续通话
```

业务模式回答：

> 系统拿到这句话以后要做什么？

```text
自由聊天 → 生成聊天回答，不落实验记录
自由实验 → 理解并记录实验事实
方案实验 → 对照步骤记录、追问、判断偏差
```

因此正确的数据流是：

```text
输入方式
├─ 文字 ────────────┐
├─ 单次录音 → ASR ──┤
└─ 连续通话 → VAD → ASR
                     ↓
             统一 TurnInput
                     ↓
                业务模式分派
          ┌──────────┼──────────┐
          ↓          ↓          ↓
        Chat       Free       Protocol
```

其中：

- VAD 只是决定连续语音在哪里切段。
- ASR 只是把语音变成可信文字证据。
- 它们不应该决定这是聊天还是实验。
- 模式应该来自用户提交这一 Turn 时的模式快照。

还有第三个容易混淆的正交维度：输出方式。

```text
输入：文字 / 单录 / 连续通话
业务：Chat / Free / Protocol
输出：屏幕显示 / TTS 播放
```

用户用语音输入，不代表系统一定要语音回答；用户用文字输入，也不代表系统不能播报。因此 TTS 同样不应该绑死在输入方式上。

这也解释了“六步泛化”：

> 六步泛化的是输入方式——实验六步不再假设一定有 ASR，而不是把 Chat 和实验合成同一种业务。

最终边界就是：

```text
输入层统一来源
业务层按模式分派
输出层统一 Turn/Block 和播放授权
```

这个正交关系一旦固定，接口和代码职责都会清楚很多。

---

## 对话 5

### 用户

是的，那我们的ASR和六步泛化应该如何设计

### 助手

可以按“输入标准化 → 模式分派 → 业务处理”三层设计。关键是：ASR 只负责输入，六步只负责实验业务，两者通过一个稳定的 Turn 输入合同连接。

## 一、目标结构

```text
/turn/text
  ↓
构造 TurnInput
  ┐
  │
  ├→ TurnApplicationService
  │        ↓
  │    按模式分派
  │   ┌────┴─────────┐
  │   ↓              ↓
  │ ChatProcessor  ExperimentProcessor
  │                  ↓
  │               泛化六步
  │
/turn/audio
  ↓
保存/准备音频
  ↓
ASRApplicationService
  ↓
完整 ASRResult
  ↓
构造 TurnInput
```

模式分派必须读取用户提交时的模式快照，不让 ASR 或 LLM猜测模式。

## 二、统一输入合同

现有 `ExperimentTurnInput` 已经表达了大部分规则，但它只允许实验模式。外层最好再有一个适用于所有业务模式的合同，例如：

```python
@dataclass(frozen=True)
class TurnInput:
    conversation_id: str
    request_id: str
    turn_id: str

    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    mode_version: int

    input_source: InputSource
    raw_text: str
    asr_result: ASRResult | None
```

它只描述：

> 用户这一次提交了什么，以及这段输入来自哪里。

不包含：

- 实体提取结果
- 实验事件
- control 判断
- 聊天回答
- 保存结果
- TTS 指令

### 输入约束

文字：

```python
input_source == TEXT
asr_result is None
raw_text 非空
```

语音：

```python
input_source in {
    SINGLE_RECORDING,
    CONTINUOUS_CALL,
}
asr_result is not None
asr_result.is_final is True
raw_text == asr_result.asr_transcript
```

模式约束：

```text
chat       → experiment_context=none
experiment → experiment_context=free 或 protocol
```

这样任何下游收到 `TurnInput` 后，都不用再猜：

- 这是文字还是语音
- 文字是否伪造了 ASR
- 转写是否属于这句话
- 用户提交时处于什么模式

## 三、ASR 应该如何设计

保留现有三层中的两层，再增加一个薄应用层。

### 1. `ASRBackend`

现有设计可以继续：

```python
class ASRBackend(Protocol):
    def recognize(
        self,
        audio_path: Path,
        *,
        language: str = "zh",
    ) -> ASRResult:
        ...
```

它解决模型替换：

```text
SenseVoice
未来其他模型
测试 Fake
```

不负责：

- HTTP
- 模式
- 会话
- 实验保存
- 六步
- TTS

### 2. `ASRApplicationService`

新增一个共享服务，负责一次完整识别操作：

```python
class ASRApplicationService:
    def transcribe(
        self,
        audio: AudioArtifact,
        *,
        language: str = "zh",
    ) -> ASRResult:
        ...
```

负责：

- 获取并复用 backend
- 预热模型
- 校验音频
- 调用 backend
- 保证结果是最终结果
- 返回完整 `ASRResult`
- 记录识别耗时
- 明确临时音频或持久音频的所有权

不负责：

- 判断 chat 或实验
- 调 LLM
- 保存实验记录
- 生成追问
- 显示“已记录”

### 3. 音频所有权

需要明确区分：

```text
临时音频：请求结束后可删除
正式证据音频：先持久化，再识别
```

建议正式实验录音：

```text
接收音频
→ 分配 request_id/segment_id 对应的稳定音频引用
→ 写入稳定位置
→ ASR 识别
→ ASRResult.audio_path 指向稳定音频
```

Chat 是否长期保留音频可以由隐私和产品策略决定；它不影响 Turn 输入合同，只影响存储策略。

## 四、Turn 应用服务负责模式分派

新增外层编排：

```python
class TurnApplicationService:
    def submit(self, turn: TurnInput) -> TurnResult:
        if turn.interaction_mode == InteractionMode.CHAT:
            return self._chat_processor.process(turn)

        if turn.interaction_mode == InteractionMode.EXPERIMENT:
            return self._experiment_processor.process(turn)

        raise ValueError("不支持的模式")
```

这里的分派是确定性的：

```text
interaction_mode=chat
→ ChatProcessor

interaction_mode=experiment
→ ExperimentProcessor
```

不让统一理解 LLM 判断用户当前处于哪个产品模式。

但进入实验处理器后，LLM 可以判断这句话属于：

```text
experiment
control
uncertain
```

这是句子含义，不是产品模式。

## 五、六步具体泛化什么

当前六步的问题不是“只支持实验”，而是“只支持带 `ASRResult` 的语音实验”。

需要把：

```python
SegmentJob(
    segment_id=...,
    asr_result=...
)
```

改成类似：

```python
ExperimentTurnJob(
    segment_id=...,
    turn=TurnInput,
)
```

然后所有文字来源统一改为：

```python
text = job.turn.raw_text
```

不再到处直接读取：

```python
job.asr_result.asr_transcript
```

### 泛化后的六步

#### 第一步：验证输入并读取会话上下文

```text
验证 Turn 身份
验证模式快照
验证输入来源
读取 ReplyCoordinator 和 SessionContext
```

#### 第二步：统一观察与分派

统一理解只接收可信原文：

```python
observer.observe(
    raw_text=turn.raw_text,
    asr_evidence=turn.asr_result,
    ...
)
```

其中：

- `raw_text` 用于理解
- `asr_result` 只作为可选来源证据
- LLM 不读取模型标签文本来替代忠实转写

输出语义分支：

```text
experiment
control
uncertain
```

#### 第三步：生成待保存结果

只生成计划，不立即到处写文件：

```python
ExperimentCommitPlan(
    input_evidence=...,
    accepted_events=...,
    clarification_action=...,
    business_record=...,
)
```

文字输入：

```text
input_evidence.asr_result = None
```

语音输入：

```text
input_evidence.asr_result = 完整 ASRResult
```

#### 第四步：持久化

由运行环境提供适配器：

```text
终端 → JSONLCommitter
Web  → SQLiteCommitter
```

Web 侧尽量在一个 SQLite 事务中保存：

- Turn 身份
- 完整 ASRResult JSON（语音才有）
- 采用的实验事件
- 最终 `lab_record`
- control/澄清状态事件

文字输入跳过 ASR 证据记录，但其余业务步骤不变。

#### 第五步：更新会话状态

保存成功后应用：

- 新建追问
- 暂缓问题
- 回答问题
- 确认或否定
- 更新 `SessionContext`

最好让这些状态可以从持久化事件重建，避免内存状态成为唯一事实。

#### 第六步：生成统一输出

保存成功后才生成：

```text
ConversationTurn
├─ user_text
├─ assistant_text
├─ experiment_record
├─ clarification
├─ system_status
└─ voice
```

然后交给统一 Store、页面和 `voice_delivery`。

保存失败时只能输出错误状态，不能生成“已记录”。

## 六、Chat 不进入实验六步

ChatProcessor 可以更简单：

```text
读取 TurnInput.raw_text
→ 调聊天模型
→ 生成 assistant_text Block
→ 保存聊天消息
→ 必要时生成 voice_delivery
```

它不会：

- 提取实验实体
- 写 `lab_records`
- 创建实验追问
- 修改实验方案步骤

但它和实验六步共用：

- `TurnInput`
- `request_id`
- `turn_id`
- 模式快照
- ConversationTurn/Block
- 页面 Store
- 播放授权

所以是“输入和输出统一，业务处理分开”。

## 七、HTTP 接口建议

最终保留：

```text
POST /turn/text
POST /turn/audio
GET  /asr/status
POST /asr/warmup
```

删除：

```text
POST /asr/transcribe
POST /record
POST /record/audio
```

或者在兼容期保留旧接口，但让它们只是薄适配器：

```text
旧 /record
→ 转成 TurnInput
→ TurnApplicationService
```

最终前端只需要知道：

```text
文字发送 → /turn/text
语音发送 → /turn/audio
```

模式放在同一请求中：

```json
{
  "interaction_mode": "experiment",
  "experiment_context": "free",
  "mode_version": 3,
  "input_source": "single_recording"
}
```

## 八、推荐实施顺序

1. 抽取 `ASRApplicationService`，现有行为不变。
2. 建立通用 `TurnInput` 合同，不接生产。
3. 让实验观察器读取 `raw_text + optional ASRResult`。
4. 让 `SegmentJob` 携带完整 Turn，而不是单独携带 ASR。
5. 增加文字/语音实验对照测试。
6. 定义 `ExperimentCommitPlan`，把判断与存储解耦。
7. 实现 Web SQLite committer。
8. 实现 `TurnApplicationService` 模式分派。
9. 增加 `/turn/text`。
10. 增加 `/turn/audio`。
11. 先迁移桌面单次录音，再迁移手机、连续通话和 VAD。
12. 确认无调用后删除 `/asr/transcribe` 和旧 `/record`。
13. 分别完成自动测试与真实浏览器、麦克风、LLM、持久化验收。

最核心的设计可以压缩成一句话：

> ASR 把语音变成带证据的 `TurnInput`；六步把实验模式的 `TurnInput` 变成可提交的实验结果；外层 Turn 服务根据模式决定走 Chat 还是实验六步。

---

## 对话 6

### 用户

最后是不是又都落在一起？

### 助手

是的，最后会“汇合”，但不是从头到尾全部塞进同一个处理函数。

更准确的形状是一个沙漏：

```text
文字 ──────────────┐
单次录音 → ASR ────┼→ 统一 TurnInput
连续通话 → VAD → ASR┘
                         ↓
                    按业务模式分开
                  ┌──────┴──────┐
                  ↓             ↓
             ChatProcessor   实验六步
                  ↓             ↓
                  └──────┬──────┘
                         ↓
             统一 TurnResult / Block
                         ↓
              SQLite、页面、TTS
```

所以是：

> 输入先汇合，中间按业务分开，输出再汇合。

## 第一次汇合：统一输入

无论文字还是语音，最后都形成：

```python
TurnInput(
    conversation_id=...,
    request_id=...,
    turn_id=...,
    interaction_mode=...,
    experiment_context=...,
    input_source=...,
    raw_text=...,
    asr_result=...,
)
```

区别只在：

```text
文字：asr_result=None
语音：asr_result=完整证据
```

## 中间必须分开

根据模式进入不同处理器：

```text
chat
→ ChatProcessor
→ 生成聊天回答

experiment/free
→ 实验六步
→ 提取并保存实验事实

experiment/protocol
→ 实验六步
→ 对照步骤、追问、判断偏差
```

不能为了“统一”把 Chat 也拿去提取实验实体，更不能让实验输入只得到普通聊天回答。

## 第二次汇合：统一输出

不同处理器最后都返回统一的 Turn 结果：

```python
TurnResult(
    turn_id=...,
    blocks=(...),
    voice_items=(...),
    persistence_status=...,
)
```

Block 类型可以不同：

```text
Chat
├─ user_text
└─ assistant_text

实验
├─ user_text
├─ experiment_record
├─ clarification
└─ system_status
```

但都进入同一个：

- `ConversationTurnStore`
- 聊天时间线
- `voice_delivery`
- 播放调度器

## 存储也是“同库但不混数据”

可以都落在 SQLite，但不代表全部塞进同一张表：

```text
SQLite
├─ turns                 所有 Turn 的共同身份和模式快照
├─ messages              Chat 消息
├─ asr_evidence          语音输入证据
├─ experiment_events     实验理解结果
├─ lab_records           用户可见实验记录
└─ clarification_events  追问和回答状态
```

通过共同身份关联：

```text
turn_id
request_id
conversation_id
session_id
```

这样既能查到一次 Turn 的完整因果链，又不会把聊天消息和实验记录混成一种东西。

所以最终不是“一条从头到尾完全相同的流水线”，而是：

```text
统一输入合同
→ 模式专属业务处理
→ 统一结果合同
→ 统一界面和存储身份
```

这正是正交设计应有的样子：共同部分只实现一次，不同业务明确分支，处理完成后再汇合。

---

## 对话 7

### 用户

把最近这两个回复固定记录，我目前感觉这个设计可行

### 助手

已固定记录到交接文档的“当前认可的候选设计”章节，包括：

- 输入、业务模式、输出三个正交维度
- “输入汇合—业务分支—输出再汇合”的沙漏结构
- ASR 服务层职责和 `/asr/transcribe` 的最终去留
- 六步泛化的准确范围
- `/turn/text`、`/turn/audio` 汇入 `TurnApplicationService` 的接口方向

已标注为“当前认可的候选设计”，不冒充代码已完成或真实验收已通过。

本次仅修改文档，没有改代码、运行测试或提交 Git。该交接文档原本就是未跟踪文件，目前仍为未跟踪状态。

---

## 对话 8

### 用户

我们现在做的能从哪方面提升用户体验，或者说更好地达到工程性、鲁棒性需要？

### 助手

这套设计最大的价值，不是“多了一个功能”，而是让用户无论用文字、单次录音还是连续通话，都得到一致、可解释、可恢复的行为。

## 对用户体验的直接提升

| 设计变化 | 用户感受到的改善 |
|---|---|
| 正式语音一次提交 | 不再经历“ASR 成功但第二次 `/record` 请求失败”的割裂 |
| 文字和语音统一为 `TurnInput` | 同一句话不会因为输入方式不同而产生不同理解结果 |
| 提交时冻结模式 | 录音过程中切换页面或模式，不会把实验内容误发成 Chat，或把 Chat 错存为实验 |
| Chat 与实验处理器明确分开 | 自由聊天不会误落实验记录，实验内容不会只得到普通闲聊回答 |
| `request_id` 幂等 | 网络重试、重复点击不会生成两条实验记录 |
| 保存成功后才显示“已记录” | 用户看到成功时，记录确实已经落盘 |
| control 进入同一实验处理链 | “查看问题、暂缓、回答、确认”在文字和语音下表现一致 |
| 统一 Turn/Block 输出 | Chat、记录卡片、追问和状态都在同一时间线，不会各显示一份 |
| 语音统一走服务端 ASR | 浏览器不会丢掉完整 ASR 证据，出错后更容易说明“听错了”还是“理解错了” |

## 最重要的体验提升：失败变得可理解

现在的两段式流程可能发生：

```text
录音成功
→ ASR 成功
→ 前端拿到文字
→ /record 失败
```

用户往往只感觉“我明明说了，为什么没记录”。

新流程可以明确区分：

```text
正在上传音频
→ 正在识别
→ 正在理解
→ 正在保存
→ 已记录
```

失败也能准确提示：

```text
没听清
识别服务不可用
理解服务暂时失败
实验记录保存失败
重复请求已复用原结果
模式已经变化，请重新提交
```

但要特别注意：合并成一次请求后，等待时间可能变长。因此 `/turn/audio` 必须保留流式进度事件，不能让用户面对一个长时间没有反馈的按钮。

建议至少提供：

```text
audio_received
asr_processing
asr_completed
understanding
saving
completed / failed
```

## 工程性提升

### 1. 正交关系进入代码合同

我们已经明确：

```text
输入方式：text / single_recording / continuous_call
业务模式：chat / free / protocol
输出方式：screen / voice
```

它们不会再通过“录音按钮对应 `/record`”这样的隐式关系绑死。

以后新增输入方式，例如上传录音文件，只需增加输入适配器：

```text
上传文件 → ASR → TurnInput
```

不需要重写 Chat 和实验处理器。

以后新增 ASR 模型，只需实现 `ASRBackend`，业务层不用改。

### 2. 职责边界更清楚

```text
ASRApplicationService
只负责音频 → ASRResult

TurnApplicationService
只负责身份、模式快照和分派

ChatProcessor
只负责聊天

ExperimentProcessor
只负责实验六步

Committer
只负责持久化

Turn/Block
只负责统一输出
```

这种边界让单元测试可以分别证明每层，而不是必须启动浏览器、麦克风、模型和数据库才能定位一个错误。

### 3. 减少重复实现

当前桌面单录、手机、VAD 和连续通话都各自包含一部分：

```text
构造 WAV
调用 /asr/transcribe
读取 transcript
再决定提交到哪里
处理错误
```

迁移后，它们只负责采集音频和提交模式快照。ASR、身份、重试和模式分派由服务端统一实现，减少四套代码逐渐偏离。

### 4. 存储身份可以贯穿全链

一次 Turn 可以通过共同身份串起来：

```text
request_id
turn_id
conversation_id
session_id
segment_id
```

以后能够回答：

- 这条页面记录来自哪次请求？
- 对应哪段 ASR？
- LLM 当时采用了什么结果？
- 为什么生成这条追问？
- 是第一次提交还是网络重试？
- 最终有没有真正保存成功？

这对调试、回归和实验审计都很重要。

## 鲁棒性提升

### 1. 服务端掌握权威证据

旧流程中，服务端 ASR 完成后只把少量字段给浏览器，浏览器再把文字送回来。服务端无法可靠证明第二次提交的文字仍对应原音频。

新流程由服务端内部完成：

```text
音频
→ 完整 ASRResult
→ TurnInput
→ 业务处理
```

可以防止：

- 转写和音频串段
- 前端丢字段
- `is_final` 丢失
- 模式快照变化
- 重试对应错误请求
- 客户端伪造 ASR 证据

### 2. 幂等和并发更容易控制

以 `request_id` 为幂等键后：

```text
同一 request_id + 相同内容
→ 返回第一次结果

同一 request_id + 不同内容
→ 拒绝冲突
```

同一实验会话仍按顺序处理，不同会话可以并行，避免：

- 两句话颠倒
- 两个请求同时领取同一个段号
- 同一个追问被回答两次
- 重复保存

### 3. 失败隔离更明确

不同故障停在不同层：

```text
ASR 失败
→ 不调用 LLM、不保存实验事件

理解失败
→ 保留输入证据，但不冒充成功理解

SQLite 保存失败
→ 不显示“已记录”

TTS 失败
→ 屏幕结果仍保留，不影响业务保存
```

这样单个外围能力失败不会把整个结果一起吞掉。

### 4. 测试矩阵变得系统化

正交设计可以直接形成测试矩阵：

| 模式 / 输入 | 文字 | 单次录音 | 连续通话 |
|---|---:|---:|---:|
| Chat | 测 | 测 | 测 |
| 自由实验 | 测 | 测 | 测 |
| 方案实验 | 测 | 测 | 测 |

再叠加故障矩阵：

- ASR 失败
- LLM 失败或降级
- SQLite 失败
- 重复请求
- 内容冲突
- 模式切换
- 服务重启
- TTS 失败

相比为每个页面临时补测试，这更容易发现跨入口不一致。

## 它不会自动解决什么

这次架构调整本身不能证明：

- ASR 识别更准确
- LLM 实验理解更准确
- 方案实验累计字段问题已经解决
- 无关输入判断已经解决
- 播放不会抢话或自激
- 手机网络下等待时间可接受
- 真实用户觉得交互自然

它主要提高的是：

> 一致性、可追溯性、失败边界和后续扩展能力。

ASR 准确率、LLM 判断、延迟和播放体验仍需要分别做真实验收。

## 应当用哪些指标证明提升

不能只以“代码更整齐”作为完成标准。至少应验证：

- 同一句文字和语音进入实验后，业务结果一致。
- 重复提交不会增加记录数量。
- 模式切换不会改变已经开始录制的 Turn。
- ASR 失败时 LLM 调用次数为 0。
- SQLite 失败时页面不出现“已记录”。
- Chat 永远不会写 `lab_records`。
- 实验输入不会误走普通 Chat 保存逻辑。
- 每条实验记录都能追到对应 `request_id` 和输入证据。
- 桌面、手机、VAD、连续通话四个入口行为一致。
- 用户全程能看到上传、识别、理解、保存进度。
- 自动测试与真实浏览器、麦克风、LLM、数据库、扬声器验收严格区分。

整体而言，这套设计对用户最大的意义是“无论怎么输入，系统都做对同一件事；失败时明确告诉我失败在哪里”；对工程最大的意义是“共同能力只实现一次，业务差异明确分支，任何结果都可以沿身份链追溯”。

---

## 对话 9

### 用户

> **选中文本：**
>
> 已确认并补齐：所有当前 DeepSeek Chat Completions 调用都显式传递：JSON"thinking": {"type": "disabled"}

这是具体是怎么做到的

### 助手

具体做法是：在每次发给 DeepSeek 的 HTTP JSON 请求体顶层加入：

```json
"thinking": {
  "type": "disabled"
}
```

但项目里有两种调用方式，所以实现方法不同。

## Web 使用 OpenAI SDK

Web 侧不是自己拼 HTTP，而是调用兼容 OpenAI 的 SDK：

```python
client.chat.completions.create(
    model=...,
    messages=...,
    extra_body={
        "thinking": {
            "type": "disabled",
        },
    },
)
```

之所以使用 `extra_body`，是因为：

- `model`、`messages`、`stream` 是 OpenAI SDK 认识的标准参数。
- `thinking` 是 DeepSeek 扩展参数。
- 如果直接写：

```python
client.chat.completions.create(
    ...,
    thinking={"type": "disabled"},
)
```

SDK 可能会认为这是不支持的关键字参数并报错。

`extra_body` 的作用是告诉 SDK：

> 把这个非标准字段合并进最终 HTTP 请求 JSON。

最终发出去的不是：

```json
{
  "extra_body": {
    "thinking": {
      "type": "disabled"
    }
  }
}
```

而是：

```json
{
  "model": "deepseek-v4-pro",
  "messages": [],
  "thinking": {
    "type": "disabled"
  }
}
```

DeepSeek 最终看到的是顶层 `thinking`。

## 当前 Web 调用点

现在代码中不止原记录里的三处；后来增加了 Chat 答案精炼调用。目前源码检查能看到四处 SDK 调用都显式传了参数。

### Chat 超长回答精炼

`web/agent/core.py:110`

```python
response = client.chat.completions.create(
    model=...,
    messages=...,
    extra_body={"thinking": {"type": "disabled"}},
)
```

### Chat 非流式调用

`web/agent/core.py:158`

```python
response = client.chat.completions.create(
    model=...,
    messages=messages,
    tools=...,
    extra_body={"thinking": {"type": "disabled"}},
)
```

### Chat 流式调用

`web/agent/core.py:197`

```python
stream = client.chat.completions.create(
    model=...,
    messages=messages,
    tools=...,
    stream=True,
    extra_body={"thinking": {"type": "disabled"}},
)
```

### 实验统一理解

`web/llm_bridge.py:65`

```python
response = client.chat.completions.create(
    ...,
    response_format={"type": "json_object"},
    temperature=0,
    extra_body={"thinking": {"type": "disabled"}},
)
```

所以 Chat、流式 Chat、回答精炼和实验理解都关掉了思考模式。

## 终端版不使用 OpenAI SDK

终端的 `src/llm/client.py:282` 自己拼完整请求 JSON：

```python
payload = {
    "model": self.model,
    "thinking": {
        "type": "disabled",
    },
    "temperature": 0,
    "messages": [...],
}
```

随后直接：

```python
json.dumps(payload)
```

发给 `/chat/completions`。

因为它自己掌握整个 JSON，所以不需要 `extra_body`。

## 设置页连接测试

连接测试同样直接使用 `httpx.post(json=...)`，因此直接把字段放进 JSON：

`web/settings_store.py:209`

```python
json={
    "model": settings.model_name,
    "thinking": {"type": "disabled"},
    "messages": [...],
}
```

这样“测试连接”和真实业务请求的模型模式保持一致。

## 流式界面为什么不再出现思考块

流式代码仍保留：

```python
reasoning = getattr(delta, "reasoning_content", None)
if reasoning:
    yield "[[LABTHINK]]" + reasoning
```

关闭思考模式后，DeepSeek 正常情况下不再返回 `reasoning_content`，因此这个分支自然不会触发，前端也不会显示 `[[LABTHINK]]` 折叠内容。

保留这段兼容代码的意义是：如果未来重新开启推理模型，前端仍然能够区分思考内容和正式回答。

## 测试实际证明了什么

终端客户端有一个明确的请求体测试：

`tests/test_llm_client_retry.py:376`

它截获发出的 HTTP Request，解析 JSON 后断言：

```python
payload["thinking"] == {
    "type": "disabled",
}
```

这能明确证明终端请求体确实包含该字段。

Web 侧目前主要是源码接线和既有调用回归证据；我没有看到一个专门遍历四个 SDK 调用并断言 `extra_body` 的集中测试。因此“当前调用点源码都显式传了”是成立的，但“以后新增调用绝不会漏传”还没有由统一机制保证。

更稳健的后续做法是把公共参数集中起来，例如：

```python
DEEPSEEK_EXTRA_BODY = {
    "thinking": {
        "type": "disabled",
    },
}
```

或者进一步封装唯一的 DeepSeek client gateway。否则每新增一个 `chat.completions.create()`，开发者仍可能忘记补这一行。

---

## 对话 10

### 用户

把侧边聊天的记录完整的导出为markdown
