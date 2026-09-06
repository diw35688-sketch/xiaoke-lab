import json
import logging
_logger = logging.getLogger("agent_core")
if not _logger.handlers:
    _h = logging.FileHandler(r"D:\me\ai107\agent_tool.log", encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)
import httpx
import threading
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
import compaction
import settings_store
from database.crud import list_memories
from harness_context import build_harness_context
from tools.calculator import calculate
from tools.experiment_tools import check_experiment_conflicts, confirm_pending_experiment, list_current_experiments, propose_experiment
from tools.memory_tools import confirm_pending_memory, propose_memory
import lab_tools
import tool_router
from tool_presentation import (
    ToolVoiceDeliveryBatch,
    merge_tool_plans,
    tool_reply_text,
)

INSTRUCTIONS = """你是「小科」，实验室科研助手。陪伴研究人员完成实验全流程：查方案、配试剂、做实验、记数据、管库存。

你是搭档，不是客服——说话像同事：惜字如金，只说有用的。

输出纪律（最重要）：
- 回答尽量一两句话说完，最多不超过三句。不展开、不罗列、不复述工具返回的内容。
- 工具卡片已经展示的数据不要在正文重复；正文只说结论或关键提醒。
- 不用 Markdown、不加粗、不列表、不编号。不暴露内部字段名。用自然口语说出来，不要写成清单。
- 始终用中文回答，不夹杂英文句子。
- 用户问"怎么做"时只说当前这一步的关键操作，不要预告后面所有步骤。
- 用户问配方/库存/方案时，工具返回什么就简洁说什么。不要追问"你是要A还是B？"——直接给最可能的答案，用户不满意会自己说。

核心原则：
- 涉及具体数值、配方、步骤时先调工具再回答，不凭记忆给数字。
- 能从工具查到的信息直接查，不让用户复述。
- 确实缺关键参数时一次只问一项，不把对话变填表。

实验准备流程（用户选择实验后走这个流程）：
1. 选方案：用户说"我要做XXX"/"做个XXX"时，调 search_protocols(keyword="XXX") 搜索。根据返回结果处理：
   - auto_select=true：只有一个匹配或偏好命中，立即调 select_protocol(protocol_id=..., search_keyword="XXX") 选定，不用问用户。
   - need_choice=true：有多个匹配，把候选展示给用户选——一句话列出每个方案的标题和步数，说"你要哪个？说A或B"。用户选完立即调 select_protocol(protocol_id=..., search_keyword="XXX") 选定。选定后系统会记住偏好，下次同样的关键词自动选定。
   - 没有匹配：说"没找到匹配方案"，问用户要不要自由记录。
   选完后调 get_protocol_prep_requirements 出准备清单。不要用 list_protocols 翻全部方案。
2. 盘点：用户说"我有什么"时调 list_storage_items。用户口头说"我有NaOH、Tris"时，立即逐个调 add_storage_item 入库（名称用用户说的名字，数量等留空），不要问"要不要记"。入库后才算标记完成。
3. 缺项处理：清单里标"可配"的缺项，说明配方库里有现成配方，问用户"帮你配？"，同意后调 start_reagent_prep_flow。标"缺"但没有配方的，调 search_community 搜社区，搜到问"帮你导入？"。
4. 开始：用户说"准备好了/开始吧"时，确认清单无遗漏，然后开始第一步。

注意：Harness 里显示的试剂配置流程是背景信息。除非用户主动问配制进度，否则以当前实验方案的准备清单为主线推进。

计算规则：分子量、浓度、稀释、称量等问题必须先调计算工具，禁止凭记忆估算，只引用工具返回的数值。

体积换算规则（重要）：方案步骤中出现"等体积""70%""两倍体积""一半体积"等相对量时，必须查 Harness 上下文中本实验已记录的数据（如上清液体积、样品体积），算出具体数值后告诉用户。例如上一步记录了上清液 500µl，本步说"加等体积异丙醇"，你要说"加 500µl 异丙醇"而不是重复"加等体积"。同理"70%"要算出 350µl 说出来。只有无法从已有数据推算时才说相对量并告知用户需要知道当前体积。

配液与配方规则：先查本地配方库（get_reagent_prep / list_reagent_preps）。本地没有时，调 search_community 搜社区模板库——配方和方案的权威来源是社区，不要凭记忆编配方。搜到后问一句"帮你导入？"，用户同意再调 import_community_entry。高风险试剂给一句安全提醒。

时间规划：用户问"要多久""帮我安排"时调 generate_schedule。用户问"几点能做完""午饭前来得及吗""我9点开始"时调 plan_clock_schedule（传入开始时间等参数）。用户做到一半问"还有多久"时调 get_remaining_schedule。用户说"今天要做A和B"时调 plan_multi_protocols。接到结果后只说关键结论和卡点（跨午饭、下班、过夜），不要逐条复述。器材情况不确定（离心机几个、温度多少），不要给确定性的器材建议，让用户自己判断。
用户到达被动等待步骤（离心、孵育、电泳、煮沸等）时，主动调 start_step_timer 启动计时器，并提一句等待期间可以做什么。

创建/修改方案规则（重要）：
- 用户说"新建方案"/"做个XXX方案"/"帮我做一个XXX实验"时，立即调 create_protocol_from_text(description=...)。description 写清实验名称、目的、关键参数（体系体积、温度、循环数等）即可，不需要用户提供逐步文字——AI 会自动补齐标准步骤。一轮调完，不要先问用户"你要哪几步"。
- 用户说"和现有方案一样，只是XXX不同"时：先 search_protocols 或 list_protocols 找到原方案 protocol_id，再 get_protocol_detail(protocol_id=...) 读出完整步骤，然后把"原方案步骤+用户要改的部分"拼成一段 description，直接调 create_protocol_from_text。不要把步骤拆开来逐条问用户，不要要求用户复述步骤。
- 创建方案和配方不需要两步确认。用户说"确定"/"新建"/"做"/"是的"就是执行指令，立即调工具，不要再问"要不要现在创建"。

创建实验：必须两步确认——先 check_conflicts 再 propose_experiment，用户明确确认后才 confirm_create_experiment。

长期记忆：用户说出稳定有用信息时先 propose_memory 暂存，询问确认后再 confirm_save_memory。临时数据不是记忆，储存库操作用 storage 工具。

扩展工具：你看到的工具列表是按需加载的。如果用户要做储存库操作、方案编辑、配方编辑、时间规划或实验安排但你没看到对应工具，调 activate_skill(skill名称) 解锁那组工具，然后在下一轮就能用了。

软件控制：用户要打开页面时调 navigate_view，查方案调 get_protocol_detail，创建/修改方案和配方调对应工具。不要只口头说"已修改"而不调工具。

知识库检索（优先级最高）：
- 用户说"知识库""引物表""查一下引物""我们的引物""ABC的引物""查一下记录"时，立即调 search_knowledge_base(query=关键词)。禁止用 web_search 联网搜索引物——实验室自己上传的引物表才是权威来源。
- 不要用 list_experiment_memory 查引物——记忆和知识库是两个不同的东西。
- 查到了直接告诉用户结果（引物名称、序列、靶基因等），查不到再说"知识库里没有匹配记录"。

禁止重复追问（最重要）：
- 用户在同一话题上已经回答过的问题，后续轮次绝对不要再问。如果连续两轮你都在追问而没有调用任何工具，立即停止追问——要么用已有信息直接调工具执行，要么坦白说"我现在没法自动完成这个，帮你手动记一下"。
- 用户说"确定"/"是的"/"都一样"/"你自己查"都是明确的执行指令，不是在跟你讨论。收到后立即行动。
- 能用工具查到的信息（方案步骤、protocol_id、配方详情）一律自己查，禁止要求用户复述。

安全边界：危险试剂和关键操作只给建议，提醒按实验室 SOP 确认。不要假装查过论文、PDF 或实验记录。"""

CHAT_REFINEMENT_POLICY = """把下面的助手回答重新生成成一句自然、完整、可独立理解的中文短回复。最多{max_chars}个字符（标点也计数），不得使用Markdown、标题、列表、链接、表情或称呼前缀；保留原意和关键结论，不得只截取前半句，不得解释你的改写过程。只输出改写后的正文：\n\n{answer}"""

EXPERIMENT_RECORD_POLICY = """当前请求属于实验记录。以自然对话回应为主：不要要求用户使用内部字段名或固定口令。用户描述刚完成的操作或实测事实时，立即调用 record_observation 并传递原始 transcript；只有工具返回成功后才能声称已记录。全局没有必填字段：用户说了什么就记什么，没说的字段一律留空，不要追问缺失信息，不要问"要不要记/要不要保存"——直接记。用户只是提问、闲聊、询问你是谁时，直接正常回答，不要强行要求记录。

步骤推进与回退规则（重要）：
- 用户说"做完了"、"完成了"、"下一步"、"继续"、"好了"等表示要推进时，调用 move_step(action="next") 推进步骤。如果本轮用户还说了新数据（数值、观察结果），先调 record_observation 记录，再调 move_step 推进。如果没有新数据，直接调 move_step。
- 用户说"回到上一步"、"搞错了"、"退回去"、"撤回"等表示要回退时，调用 move_step(action="prev") 回退。回退后告诉用户当前是哪一步，等用户重新操作或修改记录。
- 推进后要基于方案步骤说明（instruction）告诉用户下一步怎么做：方案写了加多少就告诉用户加多少，方案写了什么条件就告诉用户什么条件。用户是来跟着方案做实验的，不是来被追问的。例如步骤说明里有"加入 200µl 溶液 I"，你就要说"根据方案，需要加入 200µl 溶液 I"，而不是问"你加了多少？"。方案里没有指定的数值，才问用户。末尾加一句"需要改的话说'回到上一步'"。
- 不要追问"要不要继续/下一步继续吗"。用户说"做完了"就是明确的推进信号。
- 推进是乐观操作：宁可推快了让用户回退，也不要反复确认拖慢节奏。"""

EXPERIMENT_CONVERSATION_POLICY = """当前是在进行中的实验里对话。结合 Harness 注入的方案和步骤上下文回答，像一个了解当前进展的搭档。正文最多两三句，不展开列举。卡片已展示的数据不在正文重复；用户问"怎么做"时只说当前一步的关键操作，不要预告后续所有步骤。不要要求内部字段名或固定口令。用户只是问候、提问或说"然后呢/怎么做"时正常回答，不要误当成实验记录。用户没明确说"下一步/继续"时不要问"要进入下一步吗"，也不要擅自推进。"""


_latest_experiment_timer: dict[tuple[str, str], str] = {}
_latest_experiment_timer_lock = threading.Lock()

TOOLS = [
    {"type":"function","function":{"name":"calculate","description":"执行基础数学计算。","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"list_experiments","description":"列出当前未完成实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"check_conflicts","description":"检查时间或仪器冲突。","parameters":{"type":"object","properties":{"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"}},"required":["start_at","end_at","equipment"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_experiment","description":"保存待确认的实验提案，不会创建实验。","parameters":{"type":"object","properties":{"name":{"type":"string"},"goal":{"type":"string"},"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"},"notes":{"type":"string"}},"required":["name","goal","start_at","end_at","equipment","notes"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_create_experiment","description":"仅在用户明确确认后创建此前待确认的实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_memory","description":"暂存一条待用户确认的长期记忆，不会保存。","parameters":{"type":"object","properties":{"content":{"type":"string"},"category":{"type":"string","enum":["equipment","rule","preference","general"]}},"required":["content","category"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_save_memory","description":"仅在用户明确确认保存长期记忆后调用。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
] + lab_tools.openai_tools()


DEFAULT_MAX_TOOL_TURNS = 12
MAX_MEMORY_CONTEXT_ITEMS = 20
MAX_MEMORY_CONTEXT_CHARS = 3000


class ModelServiceError(Exception):
    def __init__(self, detail, status_code):
        self.detail, self.status_code = detail, status_code
        super().__init__(detail)


def run_tool(name, args, conversation_id):
    result, _ = _run_tool_with_presentation(name, args, conversation_id)
    return result


def _run_tool_with_presentation(name, args, conversation_id, interaction_mode=None):
    """Execute a tool and retain any backend-owned presentation plan."""

    if tool_router.is_activate_skill_call(name):
        return tool_router.handle_activate_skill(args, conversation_id), None

    handlers = {
        "calculate": lambda: calculate(args["expression"]),
        "list_experiments": list_current_experiments,
        "check_conflicts": lambda: check_experiment_conflicts(**args),
        "propose_experiment": lambda: propose_experiment(conversation_id, **args),
        "confirm_create_experiment": lambda: confirm_pending_experiment(conversation_id),
        "propose_memory": lambda: propose_memory(conversation_id, **args),
        "confirm_save_memory": lambda: confirm_pending_memory(conversation_id),
    }
    if name in handlers:
        return handlers[name](), None
    if name in lab_tools.names():
        outcome = lab_tools.call(name, args)
        if not outcome["ok"]:
            return {"error": outcome["error"]}, None
        return outcome["result"], outcome.get("presentation_plan")
    raise ValueError(f"不支持的工具：{name}")


def _memory_context():
    memories = list_memories()
    if not memories:
        return "当前没有已确认的长期记忆。"
    # 只取最近且数量受限的条目，避免长期记忆把上下文塞爆。
    selected = memories[-MAX_MEMORY_CONTEXT_ITEMS:]
    lines = [f"已确认的长期记忆（最近{len(selected)}条，完整内容见记忆库）："]
    current_length = 0
    for item in selected:
        line = f"- [{item['category']}] {item['content']}"
        current_length += len(line)
        if current_length > MAX_MEMORY_CONTEXT_CHARS:
            lines.append("- …（更多长期记忆已省略）")
            break
        lines.append(line)
    return "\n".join(lines)


def _client():
    s = settings_store.current()
    if not s.api_key:
        raise ValueError("尚未配置模型密钥。请点击界面右上角「设置」填写。")
    return OpenAI(
        api_key=s.api_key,
        base_url=s.base_url,
        timeout=httpx.Timeout(60, connect=10),
        max_retries=3,
        http_client=httpx.Client(trust_env=False),
    )


def _extra_body():
    """全局关闭 DeepSeek thinking 以保证响应速度。"""
    return {"thinking": {"type": "disabled"}}


def refine_chat_answer(answer: str, max_chars: int = 50) -> str:
    """Ask the model to regenerate an over-budget Chat answer; never slice it."""

    original = str(answer or "").strip()
    if not original:
        raise ValueError("Chat 回复为空，无法建立可见语音正文。")
    client = _client()
    try:
        candidate = original
        for _ in range(2):
            response = client.chat.completions.create(
                model=settings_store.current().model_name,
                messages=[{
                    "role": "user",
                    "content": CHAT_REFINEMENT_POLICY.format(
                        max_chars=max_chars,
                        answer=candidate,
                    ),
                }],
                extra_body=_extra_body(),
            )
            candidate = (response.choices[0].message.content or "").strip()
            if candidate and len(candidate) <= max_chars:
                return candidate
    except APITimeoutError as error:
        raise ModelServiceError("DeepSeek 精炼回复超时，请重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接 DeepSeek 精炼回复，请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(
            f"DeepSeek 精炼回复返回异常（状态码 {error.status_code}）。", 502
        ) from error
    raise ValueError(
        f"模型连续两次未能生成不超过 {max_chars} 字的完整回复，请重试。"
    )


def _messages(history, interaction_mode=None, harness_context=None, policy_override=None):
    if policy_override is not None:
        policy = policy_override
    else:
        policy = EXPERIMENT_RECORD_POLICY
    system = INSTRUCTIONS + "\n\n" + policy + "\n\n" + _memory_context()
    if harness_context:
        system += "\n\n" + harness_context
    return [{"role": "system", "content": system}, *history]


def _tools_for_mode(interaction_mode=None, conversation_id=None, user_message=""):
    """统一工具加载：核心常驻工具 + 关键词检测的 skill 组。

    不再区分实验/聊天模式——前端早已统一只发 experiment 模式，
    所有请求走同一套 skill 加载逻辑（核心工具 + 按需 skill 注入）。
    interaction_mode 参数保留以兼容调用方签名，但不再影响工具选择。
    """
    core_only = [
        t for t in TOOLS
        if t["function"]["name"] not in lab_tools.names()
    ]
    tools = tool_router.build_tools(conversation_id, user_message, extra_tools=core_only)
    _apply_session_defaults(tools)
    return tools


def _apply_session_defaults(tools):
    """对依赖实验会话上下文的工具调整参数（自动推断，无需用户传参）。

    check_timer       → 查询当前实验会话最近启动的计时器（清空参数）
    get_protocol_detail → protocol_id 改为可选：传了查任意方案，不传查当前会话的方案
    深拷贝避免污染 lab_tools 原始定义。
    """
    for i, tool in enumerate(tools):
        name = tool.get("function", {}).get("name")
        if name == "check_timer":
            copied = json.loads(json.dumps(tool, ensure_ascii=False))
            fn = copied["function"]
            fn["parameters"]["properties"] = {}
            fn["parameters"]["required"] = []
            desc = (fn.get("description") or "").strip()
            if "查询当前实验会话" not in desc:
                desc += " 查询当前实验会话最近启动的计时器。"
            fn["description"] = desc
            tools[i] = copied
        elif name == "get_protocol_detail":
            # 不清空参数——protocol_id 改为可选，让模型能查任意方案（用于复制/参考）。
            # 工具描述已在 lab_tools 里说明：不传则查当前会话的方案。
            pass


def _select_protocol_for_session(
    conversation_id: str | None,
    lab_session_id: str | None,
    protocol_id: object | None,
):
    """切换实验方案时，除了改全局 domain 状态，也写当前 lab_session 快照。

    没有 conversation_id/lab_session_id 时退化为旧行为（只改全局）。
    有会话身份时，确保 Harness/右侧 UI 看到的是“这个实验自己的方案”。
    """
    state = lab_tools.domain.start_session(protocol_id or None)
    selected_view = lab_tools.domain.step_view(state)
    if not conversation_id or not lab_session_id:
        return selected_view
    if selected_view.get("mode") != "protocol":
        return selected_view
    try:
        from src.core.protocol_execution_state import ProtocolExecutionState
        from database.turn_store import TurnStore

        protocol = selected_view["protocol"]
        execution = ProtocolExecutionState.start(
            protocol_id=str(protocol["id"]),
            protocol_version=str(protocol["version"]),
            step_number=1,
        )
        turn_store = TurnStore()
        stored = turn_store.load_experiment_state(
            conversation_id, lab_session_id
        )
        turn_store.save_protocol_navigation(
            conversation_id=conversation_id,
            lab_session_id=lab_session_id,
            expected_revision=int(stored["revision"]),
            protocol_step_facts=execution.to_snapshot(),
        )
        selected_view["revision"] = int(stored["revision"]) + 1
    except Exception:
        # 快照写入失败时仍保留全局切换结果，不让工具调用直接失败。
        pass
    return selected_view


def _execute_experiment_tool(name, args, conversation_id, lab_session_id):
    if name not in lab_tools.experiment_command_names():
        raise PermissionError(f"实验模式不允许调用工具：{name}")
    safe_args = dict(args or {})
    if name == "check_timer":
        with _latest_experiment_timer_lock:
            timer_id = _latest_experiment_timer.get(
                (conversation_id, lab_session_id)
            )
        if timer_id is None:
            return {"found": False, "message": "本次实验会话还没有启动计时器。"}
        safe_args = {"timer_id": timer_id}
    if name == "get_protocol_detail":
        state = lab_tools.domain.session()
        protocol = state.selection.protocol
        if protocol is None:
            return {"found": False, "message": "当前没有选择实验方案。"}
        safe_args = {"protocol_id": protocol.protocol_id}
    if name == "select_protocol":
        return _select_protocol_for_session(
            conversation_id, lab_session_id, safe_args.get("protocol_id")
        )
    outcome = lab_tools.call(name, safe_args)
    if not outcome["ok"]:
        raise RuntimeError(outcome["error"])
    result = outcome["result"]
    if name == "start_timer" and isinstance(result, dict) and result.get("timer_id"):
        with _latest_experiment_timer_lock:
            _latest_experiment_timer[(conversation_id, lab_session_id)] = str(
                result["timer_id"]
            )
    # record_observation 提取了实体但需要同步到 domain 步骤进度追踪器，
    # 否则下一轮上下文看不到已记录的实测值，模型会反复追问。
    if name == "record_observation" and isinstance(result, dict):
        entities = result.get("entities") or {}
        deviations = result.get("deviations") or []
        if entities:
            try:
                step = lab_tools.domain.session().current_step()
                if step is not None:
                    lab_tools.domain.record_step_fields(
                        step.step_number, dict(entities), bool(deviations)
                    )
            except Exception:  # noqa: BLE001
                pass
    return result


def _execute_tool(name, args, conversation_id, interaction_mode=None):
    """Keep legacy three-argument test/adaptor calls while enforcing new mode requests."""

    if interaction_mode is None:
        return _run_tool_with_presentation(name, args, conversation_id)
    return _run_tool_with_presentation(
        name, args, conversation_id, interaction_mode
    )


def run_agent(history, conversation_id, interaction_mode=None):
    client = _client()
    history = compaction.compact_history(history, conversation_id)
    user_message = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            user_message = msg.get("content", "") if isinstance(msg.get("content"), str) else ""
            break
    messages = _messages(history, interaction_mode)
    last_plan = None
    try:
        for _ in range(DEFAULT_MAX_TOOL_TURNS):
            response = client.chat.completions.create(model=settings_store.current().model_name, messages=messages, tools=_tools_for_mode(interaction_mode, conversation_id, user_message), extra_body=_extra_body())
            assistant = response.choices[0].message
            calls = assistant.tool_calls or []
            if not calls:
                return assistant.content or "模型没有返回文字内容。"
            messages.append(assistant)
            presentation_plans = []
            for call in calls:
                try:
                    result, presentation_plan = _execute_tool(
                        call.function.name,
                        json.loads(call.function.arguments),
                        conversation_id, interaction_mode,
                    )
                except Exception as error:
                    result = {"error": str(error)}
                    presentation_plan = None
                messages.append({"role":"tool","tool_call_id":call.id,"content":json.dumps(result, ensure_ascii=False)})
                if presentation_plan is not None:
                    presentation_plans.append(presentation_plan)
            if presentation_plans:
                last_plan = merge_tool_plans(presentation_plans)
                # 不 return——让模型看到工具结果后继续推理下一轮
    except APITimeoutError as error:
        raise ModelServiceError("大模型连接超时，请检查网络后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接大模型服务，请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    # 循环耗尽——用最后的工具计划兜底回复
    if last_plan is not None:
        return tool_reply_text(last_plan)
    return "本次处理步骤过多已停止，请拆成小步骤再说一次。"


TEMPLATE_SKILL = """你是「模板制作助手」。用户要制作实验模板（试剂配方或实验方案）时，按照以下规范工作：
1. 先明确模板类型：试剂配方（reagent_prep）还是实验方案（protocol）。
2. 收集字段：名称、用途、目标浓度、体积、溶剂、保存条件、有效期、步骤。
3. 如果用户提供 PDF/图片，你可以建议调用文档解析接口（MinerU/OCR）读取，再整理成规范结构。
4. 步骤必须一行一步，可用“+”连接；每步尽量包含可量化参数。
5. 生成后询问用户是否保存到本地试剂配置库/实验方案库；如果要发布到社区，提醒先保存到本地再通过社区页发布。
6. 输出使用清晰、无 Markdown 的简洁中文；复杂内容可分点但保持结构化。
"""


STORAGE_SKILL = """你是「储存库制作助手」。用户要制作储存库（存储位置/物品登记/库存模板）时：
1. 识别是位置（冰箱/冰柜/试剂柜/架位）还是物品/样品/溶液。
2. 收集字段：名称、类型、温度、容量、位置、数量、有效期、备注。
3. 调用储存库工具（list_storage_items / add_storage_item / add_storage_location / update_storage_item / delete_storage_item / storage_stats）进行登记。
4. 生成命名规范、格位建议和保存条件。
5. 输出简洁中文；必要时提醒用户到“储存库”页面可视化编辑。
"""


def _run_skill_agent(skill: str, history, conversation_id, harness_context=None, skill_tools=None):
    client = _client()
    history = compaction.compact_history(history, conversation_id)
    if harness_context is None:
        harness_context = build_harness_context(
            conversation_id=conversation_id,
            interaction_mode=None,
        )
    messages = [{"role": "system", "content": skill + "\n\n" + _memory_context() + "\n\n" + harness_context}] + list(history)
    # skill_tools 指定这组 skill 可用的工具名；None 时退化为全量
    if skill_tools is not None:
        tool_map = {t["function"]["name"]: t for t in TOOLS}
        active = [tool_map[n] for n in skill_tools if n in tool_map]
    else:
        active = TOOLS
    last_plan = None
    try:
        for _ in range(DEFAULT_MAX_TOOL_TURNS):
            response = client.chat.completions.create(
                model=settings_store.current().model_name, messages=messages,
                tools=active, extra_body=_extra_body(),
            )
            assistant = response.choices[0].message
            calls = assistant.tool_calls or []
            if not calls:
                return assistant.content or "模型没有返回文字内容。"
            messages.append(assistant)
            presentation_plans = []
            for call in calls:
                try:
                    result, presentation_plan = _execute_tool(
                        call.function.name, json.loads(call.function.arguments),
                        conversation_id, "experiment",
                    )
                except Exception as error:
                    result = {"error": str(error)}
                    presentation_plan = None
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                if presentation_plan is not None:
                    presentation_plans.append(presentation_plan)
            if presentation_plans:
                last_plan = merge_tool_plans(presentation_plans)
                # 不 return——让模型看到工具结果后继续推理下一轮
    except APITimeoutError as error:
        raise ModelServiceError("大模型连接超时，请检查网络后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接大模型服务，请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    if last_plan is not None:
        return tool_reply_text(last_plan)
    return "本次处理步骤过多已停止，请拆成小步骤再说一次。"


def run_template_agent(history, conversation_id):
    skill_tools = tool_router.SKILL_GROUPS["reagent_edit"]["tools"] | tool_router.SKILL_GROUPS["protocol_edit"]["tools"]
    return _run_skill_agent(TEMPLATE_SKILL, history, conversation_id, skill_tools=skill_tools)


def run_storage_agent(history, conversation_id):
    skill_tools = tool_router.SKILL_GROUPS["storage"]["tools"] | {"calculate"}
    return _run_skill_agent(STORAGE_SKILL, history, conversation_id, skill_tools=skill_tools)


def stream_agent(history, conversation_id, interaction_mode=None, lab_session_id=None, policy_override=None, allow_tools=True):
    """逐段产出模型文字；遇到工具调用时先执行工具，再继续流式回答。"""
    client = _client()
    history = compaction.compact_history(history, conversation_id)
    # 从历史最后一条用户消息提取文本，用于关键词检测
    user_message = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_message = content
            elif isinstance(content, list):
                user_message = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            break
    harness_context = build_harness_context(
        conversation_id=conversation_id,
        lab_session_id=lab_session_id,
        interaction_mode=interaction_mode,
    )
    messages = _messages(history, interaction_mode, harness_context, policy_override)
    last_plan = None
    try:
        for _ in range(DEFAULT_MAX_TOOL_TURNS):
            text_parts = []
            calls_by_index = {}
            request_args = {
                "model": settings_store.current().model_name,
                "messages": messages,
                "stream": True,
                "extra_body": _extra_body(),
            }
            if allow_tools:
                request_args["tools"] = _tools_for_mode(
                    interaction_mode, conversation_id, user_message
                )
                _logger.info("ROUND tools=[%s] user_msg=%r",
                             ",".join(t["function"]["name"] for t in request_args["tools"]),
                             user_message[:80])
            stream = client.chat.completions.create(**request_args)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # DeepSeek 等推理模型把思维链放在 reasoning_content 里，
                # 与正文分开。用独立标记转发，前端渲染成可折叠的 Think 行，
                # 不混进正文，也不进入后续消息历史。
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield "[[LABTHINK]]" + reasoning
                if delta.content:
                    text_parts.append(delta.content)
                    # 不立即 yield：工具调用前的文字是模型的内部推理，
                    # 只有本轮没有工具调用时才是最终回复。
                for partial in delta.tool_calls or []:
                    call = calls_by_index.setdefault(partial.index, {"id":"", "type":"function", "function":{"name":"", "arguments":""}})
                    if partial.id:
                        call["id"] = partial.id
                    if partial.function:
                        if partial.function.name:
                            call["function"]["name"] = partial.function.name
                        if partial.function.arguments:
                            call["function"]["arguments"] += partial.function.arguments

            calls = [calls_by_index[index] for index in sorted(calls_by_index)]
            if not calls:
                # 本轮没有工具调用 → 积累的文本就是最终回复
                final_text = "".join(text_parts)
                if final_text.strip():
                    yield final_text
                _logger.info("NO TOOL CALL → final reply (%d chars)", len(final_text))
                return
            # 记录模型选择的工具
            _logger.info("TOOL CALLS: %s",
                         ", ".join(c["function"]["name"] + "(" + (c["function"]["arguments"] or "")[:100] + ")"
                                   for c in calls))
            messages.append({"role":"assistant", "content":"".join(text_parts) or None, "tool_calls":calls})
            presentation_plans = []
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                # activate_skill：激活扩展工具组，下一轮注入
                if tool_router.is_activate_skill_call(name):
                    result = tool_router.handle_activate_skill(args, conversation_id)
                    messages.append({"role":"tool", "tool_call_id":call["id"], "content":json.dumps(result, ensure_ascii=False)})
                    continue
                # 参考 deepseek-harness：执行前先推「待执行卡片」，
                # 让用户看见系统正在做什么，而不是干等一段空白。
                if name in lab_tools.names():
                    call_view = dict(lab_tools.present_call(name, args))
                    call_view["tool_call_id"] = call["id"]
                    yield "[[LABCARD]]" + json.dumps(
                        call_view, ensure_ascii=False)
                try:
                    result, presentation_plan = _execute_tool(
                        name, args, conversation_id, interaction_mode
                    )
                    outcome = {"ok": True, "result": result}
                except Exception as error:
                    result = {"error": str(error)}
                    outcome = {"ok": False, "error": str(error)}
                    presentation_plan = None
                if name in lab_tools.names():
                    result_view = dict(lab_tools.present_result(name, args, outcome))
                    result_view["tool_call_id"] = call["id"]
                    yield "[[LABCARD]]" + json.dumps(
                        result_view, ensure_ascii=False)
                messages.append({"role":"tool", "tool_call_id":call["id"], "content":json.dumps(result, ensure_ascii=False)})
                if presentation_plan is not None:
                    presentation_plans.append(presentation_plan)
            if presentation_plans:
                plan = merge_tool_plans(presentation_plans)
                last_plan = plan
                # 中间轮次：只推送语音进度反馈，不推送确定性文本、不终止循环
                # 让模型看到工具结果后继续推理，直到模型不再调用工具为止
                if plan.voice_items:
                    yield ToolVoiceDeliveryBatch(plan.voice_items)
        # 循环耗尽——用最后的工具计划兜底回复
        if last_plan is not None:
            yield tool_reply_text(last_plan)
            return
    except APITimeoutError as error:
        raise ModelServiceError("大模型连接超时，请检查网络后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接大模型服务，请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    raise ModelServiceError("本次处理步骤过多已停止，请拆成小步骤再说一次。", 500)
