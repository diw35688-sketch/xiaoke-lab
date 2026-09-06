# 小科 Demo — AI 生成视频完整制作手册

> 共需产出 **14 个镜头**，总时长约 **90 秒**，覆盖第一幕（痛点开场）和第七幕（收尾升华）。

---

## 〇、全局规格

| 项目 | 规格 |
|------|------|
| **画幅** | 16:9 横版（1920×1080），与录屏/实拍统一 |
| **帧率** | 30fps（与实拍素材一致，方便混剪） |
| **单镜头时长** | 每个 5–10 秒（可灵/Runway 标准长度） |
| **配色阶段** | 第一幕：冷蓝灰低饱和 → 第七幕：暖金高饱和 |
| **后期字幕** | 统一在剪辑软件（剪映/PR）里加，不在 AI 视频里烧字 |

### 推荐工具分配

| 镜头类型 | 首选工具 | 原因 |
|----------|---------|------|
| 写实实验室场景 | **可灵 AI（Kling）** | 中文 prompt 精准，写实风格好，国内访问方便 |
| 运镜复杂的镜头 | **Runway Gen-3** | 运动控制强（推拉摇移、景深变化） |
| 意象/氛围镜头 | **可灵 或 海螺(MiniMax)** | 氛围渲染好，性价比高 |
| 文字动画/logo | **剪映/After Effects** | AI 不擅长精确文字，后期做 |

### 万能负面提示词（所有镜头通用）

```
负向提示词 / Negative Prompt:
cartoon, anime, 3d render, low quality, blurry, distorted, deformed hands,
extra fingers, watermark, text, logo, oversaturated, plastic skin,
uncanny valley, CGI, video game, painting, illustration
```

---

## 第一幕：痛点开场（0:00 – 0:35）

> **情绪**：压抑、焦躁、手忙脚乱
> **色调**：冷蓝灰，低饱和度，略欠曝
> **节奏**：快剪，每个镜头 3–5 秒，制造紧迫感

---

### 镜头 A1 — 戴手套的手触碰手机屏幕（0:00 – 0:05）

**分镜**：特写。一双戴着蓝色乳胶手套的手，指尖沾着液体，正在戳手机屏幕，屏幕上留下湿漉漉的指纹印记。手套和屏幕的接触面有微微变形。

**运镜**：固定机位，微距特写，极浅景深。

**可灵 Prompt**：
```
电影级微距特写，一双戴着蓝色乳胶实验手套的手，指尖有透明液滴，正在触碰黑色手机屏幕。
手指按压屏幕时留下湿润的指纹痕迹。画面冷色调，偏蓝灰，实验室背景虚化。
浅景深，只有指尖和屏幕接触点清晰。写实风格，35mm镜头质感。
```

**Runway Prompt**：
```
Extreme close-up macro shot: blue latex-gloved fingers with transparent liquid
droplets touching a black smartphone screen, leaving wet fingerprint smudges.
Cold blue-grey color grading, shallow depth of field, laboratory background
blurred. Photorealistic, cinematic, 35mm lens, 4K.
```

**时长**：5 秒

---

### 镜头 A2 — 凌乱实验台俯拍（0:05 – 0:10）

**分镜**：俯拍/上帝视角。实验台上摊开着：翻开的手写实验记录本（字迹潦草）、计算器、几个 Eppendorf 离心管、一支记号笔、手机（开着计时器页面）、一本翻开的试剂手册。光线阴冷。

**运镜**：缓慢垂直下推（top-down slow push-in），从 1.5 米高度推到 0.5 米。

**可灵 Prompt**：
```
俯拍镜头，从正上方缓慢下降。一张不锈钢实验台上非常凌乱：翻开的纸质实验记录本
（手写字迹潦草）、科学计算器、散落的微量离心管、记号笔、一部显示计时器的手机、
一本翻开的试剂配方手册。冷白色日光灯照明，色调偏冷蓝灰。写实风格，
镜头从高处垂直缓慢推近。
```

**Runway Prompt**：
```
Top-down bird's eye view, slowly pushing in. A cluttered stainless steel lab
bench: open handwritten lab notebook with messy writing, scientific calculator,
scattered microcentrifuge tubes, marker pen, smartphone showing timer,
open reagent recipe book. Cold white fluorescent lighting, blue-grey tone.
Photorealistic, slow vertical descent from 1.5m to 0.5m height.
```

**时长**：5 秒

---

### 镜头 A3 — 快速翻笔记本找不到配方（0:10 – 0:14）

**分镜**：过肩镜头。一个人快速翻动一本厚厚的实验记录本，纸页飞速翻过，找不到想要的那一页。手戴手套，动作急躁。

**运镜**：过肩固定，浅景深，只有翻动的纸页清晰。

**可灵 Prompt**：
```
过肩镜头，浅景深。一个人戴着手套的手快速翻动一本厚厚的实验记录本，
纸页快速翻动产生动态模糊。找不到目标页面的焦躁感。
冷色调实验室环境，背景虚化。写实电影风格。
```

**Runway Prompt**：
```
Over-the-shoulder shot, shallow depth of field. A gloved hand rapidly flipping
through pages of a thick lab notebook, pages creating motion blur, sense of
frustration and urgency. Cold-toned laboratory environment, background blurred.
Cinematic realism.
```

**时长**：4 秒

---

### 镜头 A4 — 手套碰脏键盘特写（0:14 – 0:18）

**分镜**：特写。戴着手套的手指（指尖有粉末或液体残留）悬在电脑键盘上方，犹豫了一下然后按下一个键，键帽上留下污渍。

**运镜**：固定特写，焦点在指尖和键帽之间切换（rack focus）。

**可灵 Prompt**：
```
特写镜头，焦点转换。戴着沾有白色粉末的蓝色实验手套的手指，
悬停在电脑键盘上方，犹豫后按下一个键，白色键帽上留下粉末污渍。
冷色调，实验室环境。写实风格，焦点从手指切换到键盘。
```

**Runway Prompt**：
```
Close-up shot with rack focus. Blue latex gloved fingers with white powder
residue hovering over a computer keyboard, hesitating, then pressing a key,
leaving powder smudge on white keycap. Cold color grading, lab setting.
Photorealistic, focus shifts from fingers to keyboard.
```

**时长**：4 秒

---

### 镜头 A5 — 画面定格 + 问号浮现（0:18 – 0:22）

**分镜**：镜头 A4 的最后帧定格（freeze frame），画面整体微微褪色，一个半透明的问号（?）从中心缓缓浮现并放大。这一帧在后期剪辑时加文字动画即可，不需要 AI 生成问号。

**制作方式**：
- 取 A4 最后一帧截图
- 在剪映/PR 中定格 3 秒
- 叠加半透明白色"?"文字动画（淡入+缓慢放大+轻微浮动）
- 同时画面饱和度逐渐降低到接近黑白

**时长**：4 秒（后期制作，不需要 AI 生成）

---

### 镜头 A6 — 画面从冷色变暖色 + 光芒涌入（0:22 – 0:26）

**分镜**：画面从冷灰蓝逐渐变暖，一道温暖的金色光线从画面左侧涌入，像清晨阳光照进实验室。色调从压抑变为充满希望。

**运镜**：光线移动方向：从左上角向右下角扫过。

**可灵 Prompt**：
```
实验室内部，画面色调从冷蓝灰缓慢过渡到温暖金色。一道清晨的阳光从左侧窗户
照射进来，光线中有微尘飞舞，照亮了不锈钢台面和玻璃器皿，产生温暖的光晕。
镜头固定，光线和色调变化驱动情绪转变。电影级光影质感，写实风格。
```

**Runway Prompt**：
```
Interior laboratory, color temperature slowly transitioning from cold blue-grey
to warm golden. A beam of morning sunlight enters from the left window,
dust particles dancing in the light ray, illuminating stainless steel surfaces
and glassware, creating warm lens flare. Fixed camera, light and color shift
drives emotional transition. Cinematic lighting, photorealistic.
```

**时长**：4 秒

---

### 镜头 A7 — Logo + 标题动画（0:26 – 0:35）

**分镜**：纯色/渐变背景上，"小科"Logo 和标题文字逐行浮现。这一帧在后期制作。

**制作方式**（剪映/PR/AE）：
- 背景：深蓝到金色的渐变（承接 A6 的暖色基调）
- 0:26–0:28："小科" Logo 淡入 + 轻微缩放动画
- 0:28–0:31：副标题浮现："你的全天候实验 AI 搭档"
- 0:31–0:35：三个关键词逐个弹出："主动 · 懂你 · 全天候"
- 字体：思源黑体 / 思源宋体，白色，带轻微发光

**时长**：9 秒（后期制作，不需要 AI 生成）

---

## 过渡镜头（穿插在各幕之间）

### 镜头 T1 — 实验室门推开（用于第二幕前 ~1s）

**分镜**：手持跟拍视角，推开实验室的玻璃门，门上贴着"分子生物学实验室"标牌。门开的一瞬间，里面的实验台和仪器映入眼帘。

**可灵 Prompt**：
```
第一人称视角，手推开实验室的磨砂玻璃门，门上贴着"分子生物学实验室"标识。
门打开的一瞬间，明亮的实验室内景展现：不锈钢台面、移液器架、离心机。
自然光线，写实风格，轻微手持晃动感。
```

**Runway Prompt**：
```
First-person POV, hand pushing open a frosted glass lab door labeled
"Molecular Biology Lab". As the door opens, the bright lab interior is revealed:
stainless steel benches, pipette racks, centrifuge machines. Natural lighting,
photorealistic, slight handheld camera shake.
```

**时长**：3 秒

---

### 镜头 T2 — 窗外天色变暗（用于第六幕过渡 ~1s）

**分镜**：实验室窗户，窗外天空从傍晚橙色渐变到夜幕深蓝。窗台上有一个用过的离心管。

**可灵 Prompt**：
```
实验室窗户特写，窗外天空从傍晚的橙红色缓慢过渡到夜幕的深蓝色。
窗台上放着一个透明的微量离心管。暖冷色调交替，宁静的傍晚氛围。
固定机位，写实电影风格。
```

**时长**：3 秒

---

## 第七幕：收尾升华（4:15 – 5:00）

> **情绪**：温暖、从容、充满希望
> **色调**：暖金色调，高饱和度，柔和光线
> **节奏**：舒缓，每个镜头 5–8 秒，留白呼吸

---

### 镜头 E1 — 清晨阳光照进空实验室（4:15 – 4:22）

**分镜**：广角镜头。清晨的实验室，空无一人。阳光从百叶窗缝隙射入，在地面和台面上形成漂亮的光栅条纹。台面上干净整洁，移液器整齐挂在架上，试剂瓶排列有序。空气中微尘飞舞。

**运镜**：缓慢横移（slow pan from right to left），展现整个实验室的宁静。

**可灵 Prompt**：
```
广角镜头，清晨空旷的分子生物学实验室。阳光透过百叶窗射入，
在不锈钢台面和地面上形成漂亮的光栅条纹。实验台整洁有序，
移液器整齐排列在架上，试剂瓶有序摆放。空气中有金色微尘飞舞。
镜头从右向左缓慢横移。温暖金色色调，电影级光影，写实风格。
宁静、充满希望的氛围。
```

**Runway Prompt**：
```
Wide-angle shot, empty molecular biology lab at dawn. Sunlight streaming
through venetian blinds, creating beautiful light grid patterns on stainless
steel surfaces and floor. Clean organized benches, pipettes neatly racked,
reagent bottles in order. Golden dust particles floating in the air.
Slow pan from right to left. Warm golden color grading, cinematic lighting,
photorealistic. Serene and hopeful atmosphere.
```

**时长**：7 秒

---

### 镜头 E2 — 实验员从容走进实验室（4:22 – 4:28）

**分镜**：中景偏远景。一个人从实验室门口走入，穿着白色实验服，手里拿着手机（或端着咖啡），步伐从容不迫。阳光照在身上，暖色调。他/她走向实验台，看了一眼手机上的内容（小科界面），微微点头。

**运镜**：固定机位，人物从画面深处走向镜头前方。

**可灵 Prompt**：
```
中远景，一个穿着白色实验服的年轻科研人员，从实验室门口从容走进来，
手里拿着手机。清晨温暖阳光照在身上。他走到实验台前，看了一眼手机屏幕，
微微点头露出满意的神情。暖金色调，柔和光影，写实电影风格。
画面宁静从容，充满信心和准备就绪的感觉。
```

**Runway Prompt**：
```
Medium-long shot, a young researcher in a white lab coat walks calmly through
the lab doorway, holding a smartphone. Warm morning sunlight illuminates
them. They approach the lab bench, glance at the phone screen, and nod
slightly with a satisfied expression. Warm golden tones, soft lighting,
cinematic realism. Calm and confident, everything-is-ready feeling.
```

**时长**：6 秒

---

### 镜头 E3 — 关键画面快闪混剪（4:28 – 4:38）

**分镜**：这一段不需要 AI 生成新素材——使用前面几幕的实拍/录屏画面的精华帧做快速混剪（flash montage），每帧 0.5–0.8 秒，配合鼓点节奏。

**制作方式**（纯剪辑）：

| 帧序 | 画面来源 | 时长 |
|------|---------|------|
| 1 | 第二幕：手机心跳通知弹出 | 0.6s |
| 2 | 第二幕：AI 排程动画完成 | 0.6s |
| 3 | 第三幕：实验员说语音指令的侧脸 | 0.6s |
| 4 | 第三幕：手机界面记录自动更新 | 0.6s |
| 5 | 第四幕：分子量计算结果 1.024g | 0.6s |
| 6 | 第五幕：引物搜索结果弹出 | 0.6s |
| 7 | 第六幕：晚间复盘通知 | 0.6s |

> 配合旁白"主动规划、语音执行、智能计算、知识检索、自动复盘"——每说一个词，切一帧。

**时长**：6 秒（纯剪辑，不需 AI 生成）

---

### 镜头 E4 — 时间轴从早到晚的延时意象（4:38 – 4:48）

**分镜**：固定机位拍实验室窗户（或用 AI 生成）。画面用延时摄影效果展现从清晨到夜晚的光线变化——日出金色 → 正午白色 → 傍晚橙色 → 夜晚深蓝。窗台上的一个小植物或试剂瓶在不同光线下呈现不同色调。

**可灵 Prompt**：
```
固定机位延时摄影效果。实验室窗户视角，展现从清晨到夜晚的完整光线变化：
日出时的金色暖光、正午的明亮白光、傍晚的橙红色夕阳、夜晚的深蓝色月光。
窗台上有一盆小绿植和几个透明试剂瓶，在不同光线下呈现不同的色彩。
时间飞速流逝的感觉，温暖而宁静。电影级光影，延时摄影质感。
```

**Runway Prompt**：
```
Time-lapse effect, fixed camera position. Laboratory window view showing
complete light changes from dawn to night: golden sunrise light, bright
midday sunlight, orange sunset, deep blue moonlight. A small potted plant
and clear reagent bottles on the windowsill shift colors under different
light. Sense of time flowing rapidly, warm and serene. Cinematic lighting,
time-lapse photography aesthetic.
```

**时长**：8 秒

---

### 镜头 E5 — 金句定格 + Logo 收尾（4:48 – 5:00）

**分镜**：纯背景上的文字动画，后期制作。

**制作方式**（剪映/PR/AE）：

| 时间 | 画面 |
|------|------|
| 4:48–4:52 | 暖色渐变背景上，金句逐字浮现：**"做实验时少停一次手，实验结束后少依赖一分回忆。"** 字体：思源宋体，白色，轻微发光 |
| 4:52–4:56 | 金句淡出，"小科"Logo 出现 + "中国科学技术大学 · 107 杯" |
| 4:56–5:00 | 底部小字淡入："55 个 AI 工具 · 170+ API · 双端覆盖 · 端侧语音推理" → 全部淡出黑屏 |

**时长**：12 秒（后期制作，不需要 AI 生成）

---

## 制作流程

### 第一步：生成原始素材（预计 2–3 小时）

```
需要 AI 生成的镜头（9个）：
  □ A1  戴手套碰手机      → 可灵（中文prompt）
  □ A2  凌乱实验台俯拍    → 可灵
  □ A3  翻笔记本找不到    → 可灵
  □ A4  手套碰脏键盘      → 可灵
  □ A6  冷色变暖色光芒    → Runway（光影过渡更强）
  □ T1  推门进实验室      → 可灵
  □ T2  窗外天色变暗      → 可灵
  □ E1  清晨空实验室      → 可灵（最重要！整个收尾的灵魂镜头）
  □ E2  实验员从容走进    → 可灵
  □ E4  延时光线变化      → Runway（延时效果更好）

后期制作的镜头（4个，不需AI）：
  □ A5  定格+问号         → 剪映/PR
  □ A7  Logo标题动画      → 剪映/PR/AE
  □ E3  快闪混剪          → 剪映/PR（用已有素材）
  □ E5  金句+Logo收尾     → 剪映/PR/AE
```

### 第二步：筛选和微调（预计 1 小时）

每个镜头生成 3–4 个变体，挑选最佳：
- 可灵：同一 prompt 生成 4 条选 1
- Runway：调运镜参数（Camera Motion）生成 2–3 条选 1
- 重点检查：手部是否变形（AI 常见问题）、实验器材是否真实

### 第三步：后期合成（预计 2–3 小时）

```
□ 导入全部素材到剪映/PR
□ 按 timeline 排列
□ 加入旁白配音
□ 加入配乐（推荐：Artlist 或 B站免费商用BGM）
□ 加入字幕（第一幕和第七幕的旁白文字）
□ 加入文字动画（A5问号、A7标题、E5金句）
□ 调色：第一幕压低饱和+偏蓝，第七幕提亮+偏暖金
□ 加转场：硬切（快剪段落）+ 交叉溶解（情绪转换段落）
```

---

## 配乐建议

| 段落 | 情绪 | 风格参考 |
|------|------|---------|
| 第一幕 0:00–0:18 | 紧张、焦躁 | 极简电子，低频脉冲，类似悬念片配乐 |
| 第一幕 0:18–0:35 | 转折、希望 | 钢琴单音渐入，弦乐渐起 |
| 第七幕 4:15–4:38 | 温暖、从容 | 钢琴 + 弦乐，柔和旋律，节奏舒缓 |
| 第七幕 4:38–5:00 | 升华、收束 | 弦乐渐强到最高点，金句处停顿，最后余音收尾 |

> 推荐搜索关键词（Artlist / B站 / 淘宝）：`cinematic piano inspiring`、`technology innovation uplifting`、`emotional corporate background`

---

## 可灵生成参数建议

| 参数 | 推荐值 |
|------|--------|
| 模式 | 专业模式 |
| 画面比例 | 16:9 |
| 时长 | 5 秒（标准）/ 10 秒（E1、E4 等长镜头） |
| 生成数量 | 每个镜头生成 4 条，选最佳 |
| 创意度 | 0.5–0.7（太低太死板，太高易变形） |
| 运动幅度 | 第一幕镜头用"大幅"，第七幕用"小幅" |

---

## 常见问题排查

| 问题 | 解决 |
|------|------|
| AI 生成的手部畸形/多指 | 重新生成，prompt 中强调"natural hands, five fingers"；实在不行用剪裁/遮罩规避 |
| 实验器材不像真的 | prompt 里加具体品牌名（如"Eppendorf离心管"、"Gilson移液器"）增强真实感 |
| 色调不对 | 可灵生成后用剪映调色；或在 prompt 里强化色彩描述 |
| 人物面孔不自然 | E2 可以生成背影或侧面，规避正脸；或用实拍替代 |
| 阳光光线不自然 | 用 Runway 的 Camera Motion 控制"Lighting Change"参数 |
