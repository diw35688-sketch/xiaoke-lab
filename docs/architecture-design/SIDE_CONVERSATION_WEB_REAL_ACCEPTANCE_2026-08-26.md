# Web 统一 Turn 链真实验收：侧边对话记录

- 日期：2026-08-26
- 范围：本侧边对话开始后，关于真实验收、浏览器 Network 检查，以及“方案步骤看不见”的排查
- 形式：整理式逐轮记录，保留原意、关键操作与证据；不包含工具内部输出
- 代码状态：本侧边对话只做解释和只读核查，没有修改项目代码

---

## 1. 真实验收通过后还要做什么

### 用户

> 真实验收通过后，下一步还有什么需要做？

### Codex

真实验收通过并不等于整个替换任务立即结束，后面还需要完成收尾：

1. 固化 `REAL_OK` 证据，记录验证过的设备、入口、场景、结果和失败恢复情况。
2. 删除旧公开生产入口：`/asr/transcribe`、`/record`、`/record/stream`、`/chat`、`/chat/stream`。
3. 保留内部 ASR 服务，以及 `/asr/status`、`/asr/warmup` 等运维接口。
4. 扫描前后端，确认没有旧接口调用和旧 producer 残留。
5. 在删除旧入口后重新执行完整自动回归，避免出现“新链验证通过，但删旧链时误伤”的问题。
6. 更新交接文档和真实验收记录。
7. 如需提交版本，再经用户授权创建明确的提交点。
8. 最后单独进入文字和语音提速任务。

可概括为：

```text
REAL_OK
→ 固化验收证据
→ 删除旧生产链
→ 删除后完整回归
→ 更新文档
→ 形成版本点
→ 单独开展提速
```

---

## 2. 统一链完成后实现了什么

### 用户

> 这样之后实现了什么功能？

### Codex

核心不是简单地“增加两个接口”，而是让所有用户输入进入同一条可追溯、可重试、可持久化的生产链。

实现目标包括：

- 文字、单次录音和连续通话都形成统一的 `TurnInput`。
- Chat、自由实验和方案实验是独立的业务模式，不再由输入方式决定业务行为。
- 语音请求保存 WAV、哈希和完整 `ASRResult`，能够沿同一个 `request_id` 追溯。
- 实验事实能够形成结构化实验记录，而不只是聊天文字。
- 实验中的澄清、控制、暂缓和确认能够进入统一处理流程。
- 明确的控制指令可以不调用 LLM，避免无意义等待。
- 同一个 `request_id` 可以识别重试、重放和内容冲突，避免重复保存。
- SQLite 提交成功后，才允许页面显示“已记录”并发送 `voice_delivery`。
- 前端统一接收 Turn/Block，而不是分别理解多套业务返回格式。
- 每个阶段都有计时，为后续文字和语音提速提供依据。

整体数据流是：

```text
文字 / 单录 / 连续通话
          ↓
       TurnInput
          ↓
 TurnApplicationService
      ↙           ↘
   Chat        Experiment
      ↘           ↙
 ConversationTurn / Blocks
          ↓
   SQLite 提交成功
          ↓
      SSE + 语音许可
```

---

## 3. 如何打开浏览器 Network 面板

### 用户

> Network 怎么打开？

### Codex

在 Microsoft Edge 中：

1. 保持实验助手页面处于打开状态。
2. 按 `F12`；部分笔记本需要按 `Fn + F12`。
3. 也可以点击右上角 `…` → “更多工具” → “开发人员工具”。
4. 在开发人员工具顶部或底部点击“网络（Network）”。
5. 确认左上角圆形录制按钮为红色，表示正在记录请求。
6. 回到页面发送一条新消息。
7. 点击新出现的请求，查看“标头（Headers）”“负载（Payload）”“响应（Response）”。

注意：截图或分享时不要暴露 API Key、Authorization 或 Cookie。

---

## 4. Network 已打开，但列表里什么都没有

### 用户

截图：

`C:\Users\dahli\AppData\Local\Temp\codex-clipboard-323fa0ed-7104-406e-9017-715258ea74d3.png`

### Codex

截图中 Network 已经成功打开。列表为空通常有两个原因：

- 开发人员工具是在请求发生之后才打开的；
- 筛选框中输入了 `turn`，不匹配的请求被隐藏。

操作方法：

1. 清空 Network 筛选框里的 `turn`。
2. 确认录制按钮为红色。
3. 回到页面重新发送一条安全测试消息。
4. 查看是否出现名称为 `text` 的请求。
5. 点击该请求，检查实际地址是否为 `/turn/text`。

---

## 5. 为什么看不到 `text`

### 用户

> 没有什么 text 啊。

### Codex

截图底部显示 `0 / 72`，含义不是浏览器没有请求，而是总共有 72 个请求，但当前筛选条件只显示 0 个。

应先点击筛选框右侧的 `×` 清空过滤内容，然后选择“全部”或 `Fetch/XHR`，再发送一条新消息。此时查找名称为 `text` 的最新请求。

---

## 6. `Fetch/XHR` 是什么

### 用户

> Fetch/XHR 是什么？

### Codex

`Fetch/XHR` 是浏览器 Network 面板中的请求类型筛选器。

- “文档”通常是网页本身。
- CSS、JS、字体和 Img 是页面资源。
- `Fetch/XHR` 是网页 JavaScript 在后台向服务器发送的数据请求。

这个项目中的 `/turn/text`、`/turn/audio`、会话查询等接口通常通过 `fetch(...)` 调用，所以会出现在 `Fetch/XHR` 分类下。

它只是查看请求的筛选按钮，不是项目中的业务模式或接口。

---

## 7. `Fetch/XHR` 标签在哪里

### 用户

> 哪有这个标签？

### Codex

它位于 Network 面板中筛选输入框的下方，与“全部、文档、CSS、JS、字体、Img”等按钮在同一行。在截图中，“全部”右边的第二个按钮就是 `Fetch/XHR`。

---

## 8. 发送消息后右边没有新增请求

### 用户

截图：

`C:\Users\dahli\AppData\Local\Temp\codex-clipboard-35947328-fe8a-479d-af05-f643a3575986.png`

> 右边没有新增。

### Codex

截图底部显示 `2 / 908`，说明实际上已经记录了 908 个请求，但当前只显示其中 2 个，仍然存在筛选。

建议：

1. 点击“全部”。
2. 清空筛选框。
3. 点击清除日志按钮，减少旧请求干扰。
4. 发送一条新的唯一消息，例如“请只回复：第三次网络测试”。
5. 在最新请求中寻找 `text`。

当时看到的 `tasks?...` 和 `updates?...` 是页面轮询请求，不是要验证的 Turn 提交请求。

---

## 9. 找到 `text` 请求

### 用户

截图：

`C:\Users\dahli\AppData\Local\Temp\codex-clipboard-f0775097-6079-46e5-ab4a-f9e33bad8289.png`

截图中出现：

- `text`，状态 `200`，类型 `fetch`；
- `stream`；
- `client-result`；
- 其他会话请求。

### Codex

目标请求已经找到，就是名称为 `text` 的那一行。

点击它后：

1. 在“标头（Headers）”中查看请求 URL，应以 `/turn/text` 结尾。
2. 查看请求方法，应为 `POST`。
3. 在“负载（Payload）”中检查业务模式字段。
4. 在“响应（Response）”中查看 SSE 事件，例如：
   - `turn_accepted`
   - `turn_status`
   - `turn_result`
   - 可选的 `voice_delivery`
   - `done`

`stream` 和 `client-result` 可能与语音合成或浏览器播放反馈有关，但不能只凭名称作最终判断。

---

## 10. 列表中又该点哪个

### 用户

截图：

`C:\Users\dahli\AppData\Local\Temp\codex-clipboard-3d19316a-c531-4557-b61e-8715833c656e.png`

> 这又该找哪个？

### Codex

目标仍然是前面出现过的 `text`。截图已经向下滚动到 `stream`、`event`、`settings`、`session` 等请求，因此没有显示 `text`。

最简单的方法是在 Network 筛选框中输入 `text`，然后重新发送一条消息。不要用 `stream`、`event`、`settings`、`session`、`tasks` 或 `updates` 代替 Turn 提交请求。

---

## 11. `POST /turn/text` 证明了什么

### 用户

> POST /turn/text

### Codex

如果 Headers 中显示请求方法为 `POST`，URL 为 `/turn/text`，说明桌面文字输入已经进入新的统一 Turn 入口。

不过，这只能证明“入口迁移”这一项。还需要检查响应事件顺序，以及实验数据是否正确保存，才能确认完整真实验收。

特别要确认：只有 `turn_result` 对应的 SQLite 提交完成后，才允许出现 `voice_delivery`。

---

## 12. 实验记录应该看哪一项

### 用户

> 不是，是实验记录的该看哪一项？

### Codex

文字实验记录仍然使用 `/turn/text`，不能根据请求名称区分 Chat 和实验。真正区分业务的是请求 Payload。

自由实验应看到：

```json
{
  "interaction_mode": "experiment",
  "experiment_context": "free",
  "lab_session_id": "非空"
}
```

方案实验应看到：

```json
{
  "interaction_mode": "experiment",
  "experiment_context": "protocol",
  "lab_session_id": "非空"
}
```

普通 Chat 应看到：

```json
{
  "interaction_mode": "chat",
  "experiment_context": "none",
  "lab_session_id": null
}
```

响应中还应检查实验业务引用和记录类 Block，例如 `record_card`。语音实验对应的是 `/turn/audio`，但业务模式仍由 metadata 中的同类字段决定。

---

## 13. 为什么列表里没有 `POST` 这一项

### 用户

> 没有 POST 这一项。

### Codex

`POST` 不是 Network 列表中的请求名称。列表里显示的是路径最后一段，因此 `/turn/text` 通常显示为 `text`。

操作路径：

```text
点击 text
→ 标头（Headers）
→ 常规（General）
→ 请求方法（Request Method）：POST
→ 请求 URL（Request URL）：.../turn/text
```

随后在“负载（Payload）”里检查 `interaction_mode` 和 `experiment_context`。

如果 Network 是在实验提交后才打开的，需要重新提交一条内容不同的新实验事实，才能产生新请求。

---

## 14. 怎么确认是 `experiment/protocol`

### 用户

> 业务模式是 `experiment/protocol`，怎么看？

### Codex

先在页面中进入“方案实验记录”，选择一个已保存的实验方案，再发送一条新的实验事实。然后：

1. 在 Network 中点击 `text`；语音提交则点击 `audio`。
2. 打开“负载（Payload）”。
3. 确认：

```json
{
  "interaction_mode": "experiment",
  "experiment_context": "protocol",
  "lab_session_id": "非空",
  "mode_version": 1
}
```

关键判断不是页面按钮看起来是否选中，而是服务器实际收到的 Payload 是否携带这些值。

---

## 15. 实验方案入口藏在哪里

### 用户

> 你把方案藏哪了？怎么看不到设计的是什么了？

### Codex

只读检查当时的前端代码后，确认存在两层概念：

1. “系统设计方案”记录在交接文档中；
2. “用户要执行的实验操作方案”在 Web 左侧栏的“实验方案”页面中。

当前操作入口是：

```text
展开左侧栏
→ 点击“实验方案”
→ 选择已有方案，或生成并保存方案
→ 返回主对话
→ 选择“方案实验记录”
```

但当时也指出了一个真实 UX 问题：当前主对话界面没有持续、醒目地展示“当前选了哪个方案、完整步骤是什么、现在应执行哪一步”。因此用户感觉方案被藏起来，并不是不会操作，而是界面信息层级设计不足。

---

## 16. 选择了方案，却不知道每一步做什么

### 用户

> 就是我新增都不知道选的这个方案每一步让我做什么。

### Codex

这不是一个单纯的使用说明问题，而是方案实验执行链的显示缺口。

当时的验收判断是：

- 方案创建和保存：可用；
- 方案选择：可用；
- 进入 `experiment/protocol` 模式：可能可用；
- 执行前查看完整步骤：不合格；
- 清楚知道当前步骤和下一步：不合格；
- 前后步骤导航：当前主界面不可见。

因此不能把“方案实验真实验收”标成 `REAL_OK`，应标成：

```text
experiment/protocol：REAL_FAIL
原因：方案步骤执行指引不可见或不足
```

需要补回的能力是：

1. 当前方案名称和摘要；
2. 完整步骤列表；
3. 当前步骤的详细操作、用量、条件和安全提示；
4. 上一步/下一步导航；
5. 已完成、当前、待执行状态；
6. 在用户行动之前显示指导，而不是提交事实之后才补一张步骤卡。

在这个问题修复并重新真实验收之前，不应删除旧接口，也不应开始提速阶段。

---

## 17. 以前是否可以显示方案步骤

### 用户

> 之前不是可以显示的吗？

### Codex

结论：可以。用户的记忆是正确的，这是一项功能回归，不是“原本就没有设计”。

只读代码和 Git 历史核查得到的证据：

- 当前 `conversation_block_view.js` 仍支持 `protocol_card` 和 `step_card`。
- 当前 `conversation_context_blocks.js` 仍会请求 `/protocols/session/steps`，并可在提交时插入方案、步骤和安全提示 Block。
- `step_cards.js` 中仍保留旧的横向步骤轨道实现，但结尾已将初始化禁用，并写明步骤时间线已合并到中间工作画布。
- `run_canvas.js` 仍包含完整步骤显示和上一步/下一步逻辑，但当前 `web/app.py` 已不再加载该脚本。
- 较早版本 `b9f4e46`、`305f497` 曾加载 `run_canvas.js`。
- C6 相关提交 `864cb6f` 在引入 Conversation Turn/Block 界面时移除了 `run_canvas.js` 的加载。

这意味着：

```text
方案数据和步骤 API 仍在
→ 原有步骤组件代码大部分仍在
→ 当前主页面装配时取消了旧工作画布
→ 新 Turn/Block 界面没有完整接回执行前步骤导航
→ 用户选择了方案，却看不到该做什么
```

不能直接把旧 `<script src="/static/run_canvas.js">` 加回来，因为旧脚本依赖的运行导航和页面结构也已经变化。正确修复方向是把以下能力重新接入当前单一对话工作台：

- 当前方案摘要；
- 完整步骤时间线；
- 当前步骤详情；
- 上一步/下一步；
- 步骤完成状态；
- 安全提示；
- 在提交实验事实之前就可见。

因此当时最终判断保持为：

```text
方案实验模式：REAL_FAIL
性质：已有功能在界面替换中发生回归
下一步：先恢复当前界面的方案步骤执行能力，再继续真实验收
```

---

## 本侧边对话形成的验收结论

### 已确认

- 浏览器能够捕获名称为 `text` 的请求。
- Headers 可验证文字入口为 `POST /turn/text`。
- Chat 与实验不能只看 URL 区分，必须查看 Payload 中的模式字段。
- 方案实验过去确实存在较完整的步骤显示和导航代码。

### 尚不能确认

- 不能仅凭 `POST /turn/text` 就宣布整个真实验收通过。
- 不能在方案步骤不可见时将 `experiment/protocol` 标记为 `REAL_OK`。
- 不能在真实验收未完成前删除旧入口或开始提速改造。

### 当前阻塞项

恢复方案实验在当前对话工作台中的执行前指导：让用户在操作前明确知道选中的方案、完整步骤、当前步骤、下一步和安全要求。
