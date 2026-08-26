import json
import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
import settings_store
from database.crud import list_memories
from tools.calculator import calculate
from tools.experiment_tools import check_experiment_conflicts, confirm_pending_experiment, list_current_experiments, propose_experiment
from tools.memory_tools import confirm_pending_memory, propose_memory
import lab_tools
from src.core.conversation_turn import InteractionMode
from tool_presentation import (
    ToolVoiceDeliveryBatch,
    merge_tool_plans,
    tool_reply_text,
)

INSTRUCTIONS = """你是实验室实验规划辅助助手。结合近期对话理解“它”“改到周五”等指代。准确计算必须调用 calculate，查询已有实验时调用 list_experiments。用户问时间/日期时调用 get_current_time，需要计时/定时时调用 start_timer，之后查询剩余时间用 check_timer。

创建实验必须两步确认：用户要求创建时，先调用 check_conflicts，再调用 propose_experiment，绝对不要直接创建；提案成功后列出信息并请用户回复“确认创建”或“取消”。只有用户在最近一条消息明确确认创建时才调用 confirm_create_experiment。

长期记忆规则：当用户说出明显长期稳定且对未来有帮助的信息（例如实验室设备数量、预约规则、用户偏好、固定流程）时，调用 propose_memory 暂存这条信息，然后明确询问“是否保存为长期记忆？请回复确认或取消”。不要把临时安排、一次性实验结果、敏感个人信息、未确认的推测自动提议为记忆。只有当用户最近一条消息明确确认保存长期记忆时，调用 confirm_save_memory。若实验创建和记忆确认同时可能发生，先请用户说明要确认哪一项，绝不擅自同时确认。

当前没有 SOP 知识库，不要假装查询过 PDF、论文或实验记录。危险操作与关键参数只能作辅助建议，并提醒用户按本实验室 SOP 和负责人要求确认。

储存库规则：用户说“储存一个种子/样品/试剂/溶液”“放到储存库”“入库”“存到冰箱/冰柜”时，调用 list_storage_items / add_storage_item / add_storage_location / update_storage_item / delete_storage_item / storage_stats 进行查询和登记。这是储存库操作，不是长期记忆；不要把库存/样品信息误当成 propose_memory，除非用户明确说“长期记住”或“以后都要用”。

软件控制规则：右侧是唯一 AI 对话入口。用户要求打开页面时调用 navigate_view；查看方案时调用 get_protocol_detail；创建方案或试剂配置时调用 create_protocol_from_text / create_reagent_prep_from_text；修改、添加、删除方案步骤时调用对应 protocol 工具。不要让用户再去寻找第二个 AI 输入框，也不要只口头说“已修改”而不调用工具。

配液前确认规则：用户要配溶液时，先确认：试剂是固体还是液体、液体密度、纯度、目标pH；若试剂是酸性物质（如丙酮酸、乙酸、盐酸），必须主动提醒“配完后要调pH”，并询问目标pH；若用户要求先调母液/溶剂pH再稀释，就按“母液调pH + 溶剂调pH + 梯度稀释后微调”的方案给。

计算规则：用户问分子量、摩尔质量、配溶液称多少克、稀释取多少母液时，第一步就必须调用 calculate_molecular_weight / calculate_solution_prep / calculate_dilution，禁止在调用前凭记忆给出任何数值，禁止在结果之外再混入自己的估算值；最终只引用工具返回的数字。

语音/通话场景输出要求：回答必须简短、直接、口语化，优先用一两句话说完；不要输出大段文字、列表、Markdown 符号或重复解释。需要记录/追问时，直接给出关键字段和一句话追问。"""

CHAT_POLICY = """当前请求是自由聊天。请直接给出自然、完整且可以独立理解的简短回答，正文最多50个中文字符（含标点），不要使用Markdown、标题、列表、链接、表情或“小科：”等称呼前缀。不要先写长回答再附摘要。即使用户提到刚做的实验、温度、剂量或现象，也只能自然讨论，不能调用 record_observation，不能声称已经保存。若用户确实想记录，请提醒其切换到自由实验记录或方案实验记录模式。"""

CHAT_REFINEMENT_POLICY = """把下面的助手回答重新生成成一句自然、完整、可独立理解的中文短回复。最多{max_chars}个字符（标点也计数），不得使用Markdown、标题、列表、链接、表情或称呼前缀；保留原意和关键结论，不得只截取前半句，不得解释你的改写过程。只输出改写后的正文：\n\n{answer}"""

EXPERIMENT_RECORD_POLICY = """当前请求属于实验记录。用户描述刚完成的操作或实测事实时，必须调用 record_observation 并传递原始 transcript；只有工具返回成功后才能声称已记录，失败必须如实说明未保存。"""

TOOLS = [
    {"type":"function","function":{"name":"calculate","description":"执行基础数学计算。","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"list_experiments","description":"列出当前未完成实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"check_conflicts","description":"检查时间或仪器冲突。","parameters":{"type":"object","properties":{"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"}},"required":["start_at","end_at","equipment"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_experiment","description":"保存待确认的实验提案，不会创建实验。","parameters":{"type":"object","properties":{"name":{"type":"string"},"goal":{"type":"string"},"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"},"notes":{"type":"string"}},"required":["name","goal","start_at","end_at","equipment","notes"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_create_experiment","description":"仅在用户明确确认后创建此前待确认的实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_memory","description":"暂存一条待用户确认的长期记忆，不会保存。","parameters":{"type":"object","properties":{"content":{"type":"string"},"category":{"type":"string","enum":["equipment","rule","preference","general"]}},"required":["content","category"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_save_memory","description":"仅在用户明确确认保存长期记忆后调用。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
] + lab_tools.openai_tools()


class ModelServiceError(Exception):
    def __init__(self, detail, status_code):
        self.detail, self.status_code = detail, status_code
        super().__init__(detail)


def run_tool(name, args, conversation_id):
    result, _ = _run_tool_with_presentation(name, args, conversation_id)
    return result


def _run_tool_with_presentation(name, args, conversation_id, interaction_mode=None):
    """Execute a tool and retain any backend-owned presentation plan."""

    if interaction_mode == InteractionMode.CHAT and name == "record_observation":
        raise PermissionError("自由聊天模式禁止写入实验记录，请切换到实验记录模式。")
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
    return "已确认的长期记忆：\n" + "\n".join(f"- [{item['category']}] {item['content']}" for item in memories)


def _client():
    s = settings_store.current()
    if not s.api_key:
        raise ValueError("尚未配置模型密钥。请点击界面右上角「设置」填写。")
    return OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=httpx.Timeout(60, connect=10), max_retries=1)


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
                extra_body={"thinking": {"type": "disabled"}},
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


def _messages(history, interaction_mode=None):
    policy = (
        CHAT_POLICY
        if interaction_mode == InteractionMode.CHAT
        else EXPERIMENT_RECORD_POLICY
    )
    return [{"role":"system","content":INSTRUCTIONS + "\n\n" + policy + "\n\n" + _memory_context()}, *history]


def _tools_for_mode(interaction_mode=None):
    if interaction_mode != InteractionMode.CHAT:
        return TOOLS
    return [tool for tool in TOOLS if tool["function"]["name"] != "record_observation"]


def _execute_tool(name, args, conversation_id, interaction_mode=None):
    """Keep legacy three-argument test/adaptor calls while enforcing new mode requests."""

    if interaction_mode is None:
        return _run_tool_with_presentation(name, args, conversation_id)
    return _run_tool_with_presentation(
        name, args, conversation_id, interaction_mode
    )


def run_agent(history, conversation_id, interaction_mode=None):
    client = _client()
    messages = _messages(history, interaction_mode)
    try:
        for _ in range(6):
            response = client.chat.completions.create(model=settings_store.current().model_name, messages=messages, tools=_tools_for_mode(interaction_mode), extra_body={"thinking": {"type": "disabled"}})
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
                return tool_reply_text(merge_tool_plans(presentation_plans))
    except APITimeoutError as error:
        raise ModelServiceError("学校大模型连接超时。请检查校园网或 VPN 后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接学校大模型服务。请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"学校大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    return "工具调用次数过多，已停止本次请求。"


def stream_agent(history, conversation_id, interaction_mode=None):
    """逐段产出模型文字；遇到工具调用时先执行工具，再继续流式回答。"""
    client = _client()
    messages = _messages(history, interaction_mode)
    try:
        for _ in range(6):
            text_parts = []
            calls_by_index = {}
            stream = client.chat.completions.create(model=settings_store.current().model_name, messages=messages, tools=_tools_for_mode(interaction_mode), stream=True, extra_body={"thinking": {"type": "disabled"}})
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
                    yield delta.content
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
                return
            messages.append({"role":"assistant", "content":"".join(text_parts) or None, "tool_calls":calls})
            presentation_plans = []
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
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
                yield tool_reply_text(plan)
                if plan.voice_items:
                    yield ToolVoiceDeliveryBatch(plan.voice_items)
                return
    except APITimeoutError as error:
        raise ModelServiceError("学校大模型连接超时。请检查校园网或 VPN 后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接学校大模型服务。请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"学校大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    raise ModelServiceError("工具调用次数过多，已停止本次请求。", 500)
