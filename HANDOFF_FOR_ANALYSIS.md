# ai107 项目技术交接文档(供外部 AI 分析用)

> 生成时间:2026-08-12
> 用途:提供给其他 AI 做独立分析。本文档自包含,不依赖任何对话上下文。
> 仓库:https://github.com/diw35688-sketch/ai107 分支 `codex/asr-demo-unified-understanding`
> 本地路径:`D:\me\ai107`

---

# 一、项目是什么

## 1.1 产品定位

**高校实验语音智能体**(项目内部代号 `asr_demo`),参赛项目:中国科学技术大学「107杯」智能体开发大赛。

一句话:**让学生做实验时边操作边口述,系统自动形成结构化实验记录,并对缺失的关键信息主动追问。**

## 1.2 解决的真实痛点

学生做实验时**双手被占用**:
- 纸笔/电脑记录会打断操作
- 普通录音只能存声音,无法检索、无法生成报告
- **当场漏记的关键参数(温度、时长、浓度)事后永远补不回来**

## 1.3 与竞品的本质区别

市面录音转写工具是**被动**的。本项目的核心价值是两点:
1. **结构化** —— "加入五毫升缓冲液" → `{action:加入, object:缓冲液, amount_value:5, amount_unit:毫升}`
2. **主动追问** —— 发现关键信息缺失时当场反问

---

# 二、技术架构现状

## 2.1 完整数据流

```
sherpa-onnx KWS(唤醒词"小科小科")
    ↓
sherpa-onnx Silero VAD(端点检测 + 句首预缓冲)
    ↓
FunASR + SenseVoiceSmall(中文 ASR,ASRResult schema v2)
    ↓
统一理解层(DeepSeek LLM,严格 JSON 合同)
    ├─ experiment 分支 → 结构化实验事件
    ├─ control  分支 → 控制命令
    └─ uncertain 分支 → 弃权
    ↓
安全分派(风险分级 → 处置 → 目标 → 权限)
    ↓
ReplyCoordinator(待确认问题队列、追问、确认)
    ↓
JSONL 持久化(asr_segments / experiment_events / experiment_confirmations)
```

## 2.2 技术栈

| 层 | 技术 | 状态 |
|---|---|---|
| 唤醒 | sherpa-onnx KeywordSpotter,离线 | 已验证可运行 |
| 断句 | sherpa-onnx Silero VAD | 已验证可运行 |
| ASR | FunASR 1.4.1 + SenseVoiceSmall(iic/SenseVoiceSmall) | 已验证,实测转写准确 |
| LLM | DeepSeek(OpenAI 兼容接口) | 需 API key |
| 存储 | JSONL 追加写 | 已完成 |
| 运行环境 | Python 3.12.10 venv(项目文档记录为 3.11.9,存在环境漂移) | — |

## 2.3 代码规模

```
src/          11,941 行(含新增 protocol 层 627 行)
tests/        约 12,100 行(测试代码 ≈ 生产代码 1:1)
全量测试      518 项,全绿
```

## 2.4 已实现的核心能力(经真实验收)

- ASR 后端 Protocol + Factory 抽象,业务代码不绑定具体模型
- `ASRResult` schema v2:区分**模型原始文本 / 忠实转写 / 纠错候选**
- 统一理解严格三分支合同(experiment / control / uncertain)
- 安全分派:固定目标 + 最小权限,不直接产生副作用
- 影子模式:新链路与旧链路并行,**只观察不执行**,双开关授权
  (`UNIFIED_SHADOW_ENABLED` + `UNIFIED_SHADOW_EXECUTE_ENABLED`)
- 采用合同:`PREPARE_CREATE`/`PREPARE_UPDATE` 只表示准备,**没有 commit 方法**

## 2.5 关键枚举(领域建模)

**用户语音命令**(`InteractionCommandType`):
`NORMAL` / `END_SESSION` / `DEFER_CURRENT` / `REVIEW_PENDING` / `AFFIRM` / `DENY` / `TARGETED_ANSWER`

**实验事件类型**(`ExperimentEventType`):
`OPERATION` / `OBSERVATION` / `MEASUREMENT` / `ANOMALY` / `NOTE`

**实体字段**(`ExperimentEntities`,共 10 个):
`action` `object` `instrument` `amount_value` `amount_unit` `concentration` `temperature` `duration` `condition` `observation`

**分派目标**(`DispatchDestination`):
`experiment_pipeline` / `clarification_context` / `end_session_confirmation` / `end_session_execution` / `abstention` / `degraded_note`

**意图处置**(`IntentDisposition`):
`pass_to_experiment` / `execute` / `require_context` / `request_confirmation` / `do_not_execute`

**澄清动作**(`ClarificationAction`,7种)+ **权限等级**(4级):
动作 `create`/`review`/`defer`/`answer`/`confirm`/`reject_suggestion`/`no_action`
权限 `none`/`read_only`/`prepare_create`/`prepare_update`

## 2.6 Agent 类型判定(重要)

**这不是 ReAct / tool-calling Agent。全仓库搜索 `tool_calls`/`function_call`/`tools=` 结果为零。**

架构是:**LLM 只做理解并输出严格 JSON 提议,确定性程序裁决是否执行。**

| | 主流 ReAct Agent | 本项目 |
|---|---|---|
| LLM 角色 | 决策者,自选工具自执行 | 只做理解,输出 JSON 提议 |
| 谁决定做什么 | LLM | 确定性分派器(程序) |
| 出错后果 | 可能乱调 API/乱改数据 | LLM 说错也改不了任何东西 |

Agent 特征体现在:**主动性**(缺信息主动追问)、**有状态**(会话上下文/待确认队列/状态机)、**受控自主**(风险分级,高风险强制二次确认)。

## 2.7 尚未实现(仅存在于文档规划)

- TTS 语音回复(**当前追问只显示在终端,但用户双手在忙、眼睛盯着实验,看不见屏幕——这是最大的能力缺口**)
- GPT-SoVITS 个性化语音
- Live2D 形象展示("具身"部分尚不存在)
- 会话总结 / Markdown 报告导出
- 设备查询(需与队友 B 的服务对接)
- 专业术语热词纠错(已做评测,未接主链)

任务清单实况:`REAL_OK 65 / AUTO_OK 64 / TODO 68 / BLOCKED 3`

---

# 三、本次会话完成的工作

## 3.1 修复的既有缺陷

### P0:契约漏洞(回归 bug)

`src/core/unified_understanding.py` 中 `ControlUnderstanding(...)` 构造被移出 try 块(引入于 commit `d5dbf84`),导致裸 `ValueError` 泄漏,而非契约要求的 `UnifiedUnderstandingError`。

```python
# 修复
supplied = _parse_supplied_entities(raw_entities)
try:
    control = ControlUnderstanding(intent, supplied_entities=supplied)
except ValueError as error:
    raise UnifiedUnderstandingError(str(error)) from error
```

### P1:异常分层

`src/llm/unified_processor.py` 原本用 `except Exception` 一把抓,使**契约违规**和**程序缺陷**被压成同一种降级结果,导致 bug 不可观测。改为:

```python
except (LLMClientError, UnifiedUnderstandingError) as error:
    return self._degrade(request, generation, error)   # 预期内,安静降级
except Exception as error:
    print("[统一理解] 非契约异常，疑似代码缺陷：...")     # 预期外,降级但显式告警
    return self._degrade(request, generation, error)
```

### 编码损坏修复

某次 Codex agent 因 "model at capacity" 中断,导致 `protocol.py` 中 6 行中文被写成 `?`(含用户可见报错文案),已手工恢复。

## 3.2 新增:Protocol 层(本次会话核心)

### 设计动机

原系统**不知道用户在做什么实验**。`session_id` 只是时间戳,LLM 上下文中无任何实验信息。"缺哪些字段"由 LLM 猜测,规则写在提示词里。

**已发生的真实事故**:统一 Prompt 少了一行规则,`missing_fields` 从 `[temperature, duration]` 变成 `()`,追问能力静默消失。修法是"在提示词里补一行字"——说明**业务规则活在字符串里,不可测试、不可版本化**。

### 核心语义(经过一次重大修正)

**第一版设计是错的**:用单一 `required_fields`,缺了就追问。导致荒谬情况——方案第3步写着「加热到60℃保持10分钟」,学生说「将溶液加热」,系统追问「请问加热到多少度?」**等于让学生背诵方案**。

**修正后的正确模型**:

| | 方案规定值 `protocol_values` | 现场实测值 `must_record` |
|---|---|---|
| 例 | 加热到60℃、称取3.58g、用移液管 | 实际称了3.61g、滴定消耗24.7mL、观察到变浑浊 |
| 谁知道 | 方案作者已写死 | **只有现场才知道,作者不可能预知** |
| 系统行为 | **直接采用,永不追问** | **必须记录,缺失才追问** |

关键认知:**实验记录的价值恰恰在第二类**。「方案说称3.58g」在方案里躺着,记一百遍无意义;「实际称了3.61g」才是本次实验独有的事实。同一字段可同时出现在两边(目标 vs 事实),不矛盾。

### 数据结构

```python
@dataclass(frozen=True)
class ProtocolStep:
    step_number: int                      # 1起,同方案内严格连续
    title: str
    instruction: str
    protocol_values: Mapping[str, str]    # 方案已定 → 永不追问
    must_record: tuple[str, ...]          # 现场必测 → 缺失才追问
    terms: tuple[str, ...]                # 术语表(供将来ASR热词)
    hazard_note: str | None

@dataclass(frozen=True)
class ExperimentProtocol:
    protocol_id: str
    title: str
    source: str
    version: str
    steps: tuple[ProtocolStep, ...]
    schema_version: int
```

**校验规则**(全部有对应测试):
- `step_number` 从1严格连续,不重复不跳号
- 字段名白名单**从 `dataclasses.fields(ExperimentEntities)` 动态获取**,不硬编码(将来加实体字段自动生效)
- 字段名不重复;所有字符串非空白
- `int` 字段排除 `bool`(Python 中 `bool` 是 `int` 子类)
- `expected_values`/`protocol_values` 转 `MappingProxyType`(`frozen=True` 挡不住 dict 被改)
- 所有异常走 `ProtocolError(ValueError)`,子类 `ProtocolStoreError` / `ProtocolSelectionError` / `ProtocolStepCursorError`

### 值来源标记(provenance)

```python
class FieldValueSource(str, Enum):
    SPOKEN = "SPOKEN"                      # 学生亲口说的
    PROTOCOL_DEFAULT = "PROTOCOL_DEFAULT"  # 按方案自动填充
    DEVIATION = "DEVIATION"                # 学生说的与方案不一致

@dataclass(frozen=True)
class SourcedFieldValue:
    field_name: str
    value: str
    source: FieldValueSource
```

**硬性原则**:按方案填充的值**绝不能伪装成学生说过的话**。即使学生说的值恰好等于方案值,来源仍是 `SPOKEN` 而非 `PROTOCOL_DEFAULT`。

实测行为(方案规定 3.58 g):

| 学生说 | 记录值 | 来源 |
|---|---|---|
| 「我称了3.61克」 | 3.61 | `DEVIATION` + 产出偏差记录 |
| 「我称了3.58克」 | 3.58 | `SPOKEN` |
| (没提质量) | 3.58 | `PROTOCOL_DEFAULT` |

### 模块清单

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/core/protocol.py` | 190 | 方案/步骤契约、来源标记、`materialize_field_values` |
| `src/storage/protocol_store.py` | 181 | JSON 严格解析(未知字段拒绝、ID唯一、版本校验) |
| `src/core/protocol_selection.py` | 113 | 按序号/ID选择,**支持"不选方案"自由模式** |
| `src/core/protocol_missing_fields.py` | 49 | 纯函数,只对 `must_record` 做减法 |
| `src/core/protocol_deviations.py` | 40 | 纯函数偏差检测 |
| `src/core/protocol_cursor.py` | 54 | 不可变步骤游标(next/prev/jump_to) |
| `tests/test_protocol*.py` | 1127 | 9个测试文件,protocol 专项 91 项 |

### 步骤推进策略决策

采用 **A:用户显式推进**(`next` / `prev` / `jump_to`),**不做 LLM 步骤对齐**。

依据:专业 ELN(Benchling、LabArchives、SciNote)和制药 MES(Werum PAS-X)一律用显式推进 + 电子签名,因为 GxP/21 CFR Part 11 要求可审计。**LLM 对齐错误是静默的**——参数被记到错误步骤,记录看起来仍然合法,但事实已污染,比没有步骤跟踪更危险。

### 兼容层清除(重要教训)

第一版修正时为满足"501测试必须全绿"的约束,保留了 `required_fields` → `must_record` 的映射兼容层。**实测发现这个兼容层把刚修掉的 bug 原样保留了**:用旧写法构造仍会追问方案里写着的值。

已彻底删除,并把 28 处旧测试**逐个按新语义重写**(不是删除),新增关键测试:
`test_protocol_values_are_not_missing_even_when_unprovided`

**教训**:语义变更时,"保持所有旧测试全绿"是有害约束。编码了错误语义的测试应被改写,而非用兼容层保护。

---

# 四、Protocol 数据资产

## 4.1 自建种子方案(3份,中文)

`data/protocols/undergraduate_basic_protocols.json`,已按新语义(`protocol_values`/`must_record`)编写:
- 0.1 mol/L pH 7.4 磷酸缓冲液配制(5步)
- 氢氧化钠滴定盐酸(5步)
- 硫酸铜溶液分光光度测定(6步)

**注意**:AI 生成,化学内容未经实验教师复核,不应视为正式 SOP。

## 4.2 真实抓取方案(10份,来自 protocols.io)

`data/protocols/external/raw/*.json` + `LICENSE_LEDGER.md`

全部为 protocols.io 公开内容,**PDF 页面明确写明 Creative Commons Attribution License,但未注明版本号**(台账中保守标注为 "CC BY; version not stated in PDF export",未强行写成 CC BY 4.0)。

DOI 已验证可解析。台账记录:来源、URL、作者、标题、版本/DOI、许可证名称与链接、抓取时间、**源 PDF 的 SHA-256**(证据完整性)、页数。

清单:
1. 0.1xBWT buffer(缓冲液,Max Planck)
2. **Agarose Gel Electrophoresis (Instructor Protocol)** ← 教师写给学生的教学方案,原文含"学生常犯错误"清单,与本产品场景最契合
3. Cell Counting(细胞计数/分光光度)
4. Confocal Microscopy of DFP-Treated Cells
5. MIC determination against Sporothrix
6. DNA Extraction from Sterivex Filters
7. eDNA 12S Metabarcoding PCR
8. ELISAs for mouse IL-10/IL-6/IL-1β/TNF-α
9. Passaging Adherent Cancer Cell Lines
10. Pigment Content Quantification in NBS

**主动排除**:一份 protocols.io 上标记为 `Springer Nature Books` 的第三方书章内容,尽管页面显示开放许可,仍判定不属于平台公开用户内容而未纳入。

**数据形态限制**:`steps_raw` 是 **PDF 整页文本 dump**,混杂元数据、摘要、关键词、安全警告,**不是解析好的结构化步骤**。要转成 `ProtocolStep` 仍需 LLM 抽取 + 人工确认流程。

## 4.3 中文翻译(3份已完成)

对最适合教学的 3 份做了中文翻译,存于原 JSON 的 `translation_zh` 附加字段。

**翻译规则(已自动校验)**:
- **所有数字与单位原样保留,不翻译不换算**。校验结果 28/28 全部保留
- 试剂品牌名、试剂盒名、货号、基因名、菌株名保留英文
- 原文完整保留,译文仅为附加层,每条中文步骤带 `source_text` 英文原句,可逐句回溯
- 把握不足的术语保留英文并标 `[待确认]`,汇总在 `uncertain_terms`
- **CC BY 派生声明**:含原作者、原URL、DOI、许可证,并明确声明"本中文版为翻译改编版本,原作者未参与本翻译,亦不对本译本负责"
- 全部标记 `review_status: UNREVIEWED`,**未经具备实验背景人员复核,不得用于正式教学**

待复核术语:`LAB buffer`(推测 Lithium Acetate Borate)、`BWT`(原文未展开)、`TSB`(推测 Tryptic Soy Broth)、`run to red`(电泳方向口诀)

---

# 五、调研结论(protocol 来源与 OCR)

完整报告:`docs/PROTOCOL_SOURCING_RESEARCH.md`(477行,67个引用链接,9处主动标注"未验证")

## 5.1 版权红线(最重要)

| ❌ 不能抓取再分发 | ✅ 可作为种子数据 |
|---|---|
| Nature Protocols | protocols.io 公开内容(CC BY,有官方 API) |
| JoVE | Bio-protocol(**逐篇**确认许可) |
| Springer Protocols | PMC Open Access Subset(逐篇筛 CC0/CC BY) |
| 丁香园帖子 | MIT OpenCourseWare 等 CC 授权讲义 |
| 高校讲义/教材配套资源 | 团队自行编写 |

关键判断:**「机构能访问」≠「能打包进产品」**。Springer 的文本挖掘权限不等于内容再发布权。

## 5.2 OCR 选型

| 档位 | 方案 | 成本 | 磁盘 |
|---|---|---|---|
| 最省事(推荐) | 腾讯云 OCR | 0.15元/次,部分接口每月1000次免费 | ~0 |
| 断网兜底 | RapidOCR | 0 | 0.2-0.8 GB |
| 效果优先 | PaddleOCR PP-StructureV3 | 0 | 1.5-5 GB |

**不推荐本机部署**:PaddleOCR(1.5-5GB)、Qwen-VL(6-12GB)、GLM-4V(十几到二十GB)——**开发机 C 盘已满**(242G/242G,0字节可用)。

工程原则:**能直读就不 OCR**。电子PDF/DOCX 直接提取文本,只对扫描页 OCR。

## 5.3 上传+OCR 流程设计

```
上传讲义 → OCR → 原始文本(第1层:留痕,永不覆盖)
       → LLM 抽取 → 结构化草稿(第2层:标记"未确认")
       → 🚦人工确认(必须,不可跳过)
       → 正式 protocol 入库(第3层)
```

**为什么人工确认门不可省**:被 OCR 错认的方案(60℃认成80℃)会**静默污染之后所有实验记录**,而且用户不会发现——系统会拿着错误期望值去追问和预警,看起来一切正常。比不做还糟。

**安全**:上传的方案文本必须视为**不可信数据**,不能当系统指令(与 `unified_prompts.py` 现有防注入写法一致),否则塞一份"方案"就能劫持 Agent。

## 5.4 工作量估算

- 上传→解析→确认 闭环:5-8 人日
- 再加运行时步骤匹配 + 确定性追问:7-11 人日
- 若上 PaddleOCR + 本地视觉模型:再加 3-7 人日,显著增加部署风险

## 5.5 演示稳定性建议

预置 3-5 份已批准方案,现场不依赖 OCR 成功;现场上传只演示 1 份清晰讲义;准备断网模式;**把"人工确认"讲成产品安全设计,而非模型能力不足的补丁**。

---

# 六、用户(项目负责人)的核心要求与判断

## 6.1 明确提出的产品判断

1. **必须有 protocol** —— 「整个项目至少是有 protocol 的,用户选择了某一个实验,然后才开始做这个语音交互」

2. **追问逻辑的根本性纠正**(本次会话最重要的输入):
   > 「为什么要追问呢?你肯定作者写了什么,你就是什么。你不能作者也不知道是什么,然后你就去问啊」

   这一条直接推翻了第一版设计。系统不应让学生背诵方案里已写死的参数,只应追问方案不可能预知的现场实测值。已据此重构。

3. **Protocol 来源三条腿都要做**:搜索获取初始 protocol、用户上传自己的 protocol、OCR 识别制作 protocol,以及方案选择功能。

4. **英文方案译成中文**,而非从零自写。

## 6.2 明确的工作方式要求

- **重要代码交给 Codex 写**(通过 paseo 调度),Claude 负责规划、设计、验收把关
- **不要提交**(所有改动留在工作区待审)
- **启动要能看到效果**

## 6.3 全局工作原则(来自用户的 CLAUDE.md)

- **不看图**:读图极耗 token,一律数值化校验,产出物给路径让人看
- **产品分析必须走第一性原理 + 对抗性审查**,禁止用类比代替论证,只报好消息=交付不合格
- **Claude 出脑子和品味,Codex 出手干活,Claude 验收把关**
- 大文件下载不直接执行,写脚本交给用户

## 6.4 项目自身的铁律(来自项目 CLAUDE.md)

- 每轮只推进**一个可独立验证的能力**
- 先定义稳定数据结构和接口,再连接真实服务
- 分层测试:单元(Fake)→ 集成 → 真实服务 → 端到端
- 外部服务失败不能破坏已完成的核心工作
- **原始数据优先保存,模型推断不覆盖原始事实**(本次多处设计直接源于此)
- 入口文件只负责创建对象、连接依赖、控制主循环
- 密钥从环境变量或 `.env` 读取,不硬编码
- 用户是低年级本科生,需要讲清模块职责、数据流、设计取舍、失败边界和验收方法

---

# 七、已知问题与限制

## 7.1 代码层面

| 问题 | 说明 |
|---|---|
| `main.py` 过大 | 1150行,`run_experiment_session()` 单函数 474行,15个 `display_*` 展示函数塞在入口——**违反项目自己的 CLAUDE.md 规定** |
| 缺 README | 根目录无 README,他人 clone 后不知如何上手 |
| 依赖不锁版本 | `requirements.txt` 仅 6 个包名无版本约束(已标 `ENV-03` TODO) |
| 测试不自洽 | `unittest discover` 会收进 `src/**/test_*.py` 手动脚本;`tests/` 通过 `import src.main` 间接依赖 sounddevice/sherpa_onnx,非 hermetic |
| 环境漂移 | 文档记录 Python 3.11.9,实际 venv 为 3.12.10 |
| 文档自相矛盾 | 交接文档第2节称"已推送",第6节称"未提交未推送" |
| 硬编码个人路径 | 文档中出现 `C:\Users\dahli\Desktop\asr_demo` |

## 7.2 Protocol 层的已知限制

1. **偏差检测只做字符串比较**,不做单位归一化。`60℃` vs `60摄氏度`、`0.1 mol/L` vs `100 mmol/L` 会被误报为偏差。属有意保留的范围限制。
2. **一个 `amount_value` 只能承载一个值**。磷酸盐称量涉及两种盐、标准系列涉及多个浓度和吸光度,当前 `ExperimentEntities` 无法表达"多条测量记录",可能需要 `MeasurementRecord` 结构。
3. **跨步骤归属未定义**。滴定的实际体积与终点现象可能跨两个步骤,接入会话状态时需明确一次口述归入哪一步,以及如何避免同一字段被重复追问。
4. **来源值尚未接入 `ExperimentEvent` 持久化**。目前只是不可变数据合同。
5. **`ExperimentEntities` 的10个通用字段装不下专业参数**。波长、pH、转速、离心力等只能挤进 `condition` 字符串字段,导致追问可能变成"请补充 condition"这种无法回答的问题。
   **未采纳的建议**:在 `ProtocolStep` 增加 `field_prompts`,让方案作者为每个必测字段写追问话术(如"请问测量波长设置为多少纳米?"),这样不用 LLM 也能问出具体问题。**此项尚未实施,待决策。**

## 7.3 运行环境限制

- **开发机 C 盘 242G 已满,0 字节可用**(系统级问题,影响任何需要大依赖的方案)
- 依赖已装到 D 盘 venv:`D:\me\ai107\.venv`
- 模型缓存已重定向:`MODELSCOPE_CACHE=D:\me\.modelscope`
- 启动耗时约 47 秒,且首次需联网(`MODEL-LOAD-02` TODO:固定 FunASR 模型修订、关闭启动更新检查)

## 7.4 协作过程中的可靠性观察

本次会话中 Codex(gpt-5.6-sol / terra)出现 **5 次 "model at capacity" 错误**,且表现不一致:
- 一次中途崩溃,**留下编码损坏**(中文写成 `?`),但报告为 error
- 一次报 error 但**工作实际已完成**
- 一次完成 5/10 后崩溃,**产出的译文 100% 损坏**(中文字符数 0,问号 500+)

**结论:Agent 报告"完成"与实际完成不能划等号,必须逐字节独立验收。** 缓解措施:缩小批次、要求 agent 自检(读回文件并统计中文字符数)、原始数据与推断产物分层存放(本次因译文只写在附加层,损坏时删掉附加字段即可完全恢复)。

---

# 八、待决策事项

1. **下一步做什么?**
   - 选项 A(推荐):**接入主流程** —— 选方案 → 会话绑定 → 按方案追问 → 偏差预警。做完即可演示完整差异化闭环,**不需要 OCR、不需要联网、不花钱**
   - 选项 B:上传 + OCR + 人工确认(5-8人日,风险和工作量都在这里)

2. **是否增加 `field_prompts`(方案自带追问话术)?** 决定追问的最终体验质量。

3. **剩余 7 份 protocol 是否翻译?** 建议只翻 `Passaging Adherent Cancer Cell Lines` 和 `Pigment Content Quantification`,其余 5 份(eDNA宏条形码、小鼠ELISA、共聚焦显微镜、DNA提取、MIC测定)为纯科研级,对本科教学场景价值低。

4. **是否提交?** 当前全部改动堆在工作区未提交。

5. **中文种子方案是否需要实验教师复核?** 现有 3 份自建方案与 3 份译文均未经专业复核。

---

# 九、当前工作区状态(全部未提交)

```
 M LEARNING_REVIEW_FROM_DEVELOPMENT.md
 M docs/NEXT_SESSION_HANDOFF_2026-08-09.md
 M docs/PROJECT_TASK_CHECKLIST.md
 M src/core/unified_understanding.py          ← P0 修复
 M src/llm/unified_processor.py               ← P1 修复
?? data/protocols/undergraduate_basic_protocols.json
?? data/protocols/external/raw/*.json (10份) + LICENSE_LEDGER.md
?? docs/PROTOCOL_SOURCING_RESEARCH.md
?? scripts/demo_offline_session.py            ← 离线演示脚本
?? src/core/protocol.py
?? src/core/protocol_cursor.py
?? src/core/protocol_deviations.py
?? src/core/protocol_missing_fields.py
?? src/core/protocol_selection.py
?? src/storage/protocol_store.py
?? tests/test_protocol*.py (9个)
```

**全量测试:518 项,全绿。**

验证命令:
```powershell
cd D:\me\ai107
.\.venv\Scripts\python.exe -B -m unittest discover     # 518 tests OK
.\.venv\Scripts\python.exe -B -m src.main              # 启动主程序(需 .env 中 LLM_API_KEY)
```

---

# 十、希望外部 AI 分析的方向(建议)

1. **架构评估**:"LLM 提议 + 程序裁决"这条路线在实验记录场景是否正确?有无更好的范式?
2. **Protocol 建模**:`protocol_values` / `must_record` 二分是否充分?如何解决 7.2 中的多测量值、跨步骤归属、专业参数装不下三个问题?
3. **产品判断**:在没有 TTS 的情况下,"主动追问"的核心价值能否成立?优先级排序是否合理?
4. **比赛策略**:相对于其他"AI + 实验室"参赛项目,本项目的差异化是否足够?
5. **对抗性审查**:如果这个项目失败,最可能的单一原因是什么?哪条假设最脆弱?
