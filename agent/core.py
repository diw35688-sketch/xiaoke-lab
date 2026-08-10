import json
import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from config import MODEL_NAME, OPENAI_API_KEY, OPENAI_BASE_URL
from database.crud import list_memories
from tools.calculator import calculate
from tools.experiment_tools import check_experiment_conflicts, confirm_pending_experiment, list_current_experiments, propose_experiment
from tools.memory_tools import confirm_pending_memory, propose_memory

INSTRUCTIONS = """你是实验室实验规划辅助助手。结合近期对话理解“它”“改到周五”等指代。准确计算必须调用 calculate，查询已有实验时调用 list_experiments。

创建实验必须两步确认：用户要求创建时，先调用 check_conflicts，再调用 propose_experiment，绝对不要直接创建；提案成功后列出信息并请用户回复“确认创建”或“取消”。只有用户在最近一条消息明确确认创建时才调用 confirm_create_experiment。

长期记忆规则：当用户说出明显长期稳定且对未来有帮助的信息（例如实验室设备数量、预约规则、用户偏好、固定流程）时，调用 propose_memory 暂存这条信息，然后明确询问“是否保存为长期记忆？请回复确认或取消”。不要把临时安排、一次性实验结果、敏感个人信息、未确认的推测自动提议为记忆。只有当用户最近一条消息明确确认保存长期记忆时，调用 confirm_save_memory。若实验创建和记忆确认同时可能发生，先请用户说明要确认哪一项，绝不擅自同时确认。

当前没有 SOP 知识库，不要假装查询过 PDF、论文或实验记录。危险操作与关键参数只能作辅助建议，并提醒用户按本实验室 SOP 和负责人要求确认。用简洁中文回答。"""

TOOLS = [
    {"type":"function","function":{"name":"calculate","description":"执行基础数学计算。","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"list_experiments","description":"列出当前未完成实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"check_conflicts","description":"检查时间或仪器冲突。","parameters":{"type":"object","properties":{"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"}},"required":["start_at","end_at","equipment"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_experiment","description":"保存待确认的实验提案，不会创建实验。","parameters":{"type":"object","properties":{"name":{"type":"string"},"goal":{"type":"string"},"start_at":{"type":["string","null"]},"end_at":{"type":["string","null"]},"equipment":{"type":"string"},"notes":{"type":"string"}},"required":["name","goal","start_at","end_at","equipment","notes"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_create_experiment","description":"仅在用户明确确认后创建此前待确认的实验。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"propose_memory","description":"暂存一条待用户确认的长期记忆，不会保存。","parameters":{"type":"object","properties":{"content":{"type":"string"},"category":{"type":"string","enum":["equipment","rule","preference","general"]}},"required":["content","category"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"confirm_save_memory","description":"仅在用户明确确认保存长期记忆后调用。","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
]


class ModelServiceError(Exception):
    def __init__(self, detail, status_code):
        self.detail, self.status_code = detail, status_code
        super().__init__(detail)


def run_tool(name, args, conversation_id):
    handlers = {
        "calculate": lambda: calculate(args["expression"]),
        "list_experiments": list_current_experiments,
        "check_conflicts": lambda: check_experiment_conflicts(**args),
        "propose_experiment": lambda: propose_experiment(conversation_id, **args),
        "confirm_create_experiment": lambda: confirm_pending_experiment(conversation_id),
        "propose_memory": lambda: propose_memory(conversation_id, **args),
        "confirm_save_memory": lambda: confirm_pending_memory(conversation_id),
    }
    if name not in handlers:
        raise ValueError(f"不支持的工具：{name}")
    return handlers[name]()


def _memory_context():
    memories = list_memories()
    if not memories:
        return "当前没有已确认的长期记忆。"
    return "已确认的长期记忆：\n" + "\n".join(f"- [{item['category']}] {item['content']}" for item in memories)


def _client():
    if not OPENAI_API_KEY:
        raise ValueError("尚未配置 OPENAI_API_KEY。请检查 .env 文件。")
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=httpx.Timeout(60, connect=10), max_retries=1)


def _messages(history):
    return [{"role":"system","content":INSTRUCTIONS + "\n\n" + _memory_context()}, *history]


def run_agent(history, conversation_id):
    client = _client()
    messages = _messages(history)
    try:
        for _ in range(6):
            response = client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=TOOLS)
            assistant = response.choices[0].message
            calls = assistant.tool_calls or []
            if not calls:
                return assistant.content or "模型没有返回文字内容。"
            messages.append(assistant)
            for call in calls:
                try:
                    result = run_tool(call.function.name, json.loads(call.function.arguments), conversation_id)
                except Exception as error:
                    result = {"error": str(error)}
                messages.append({"role":"tool","tool_call_id":call.id,"content":json.dumps(result, ensure_ascii=False)})
    except APITimeoutError as error:
        raise ModelServiceError("学校大模型连接超时。请检查校园网或 VPN 后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接学校大模型服务。请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"学校大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    return "工具调用次数过多，已停止本次请求。"


def stream_agent(history, conversation_id):
    """逐段产出模型文字；遇到工具调用时先执行工具，再继续流式回答。"""
    client = _client()
    messages = _messages(history)
    try:
        for _ in range(6):
            text_parts = []
            calls_by_index = {}
            stream = client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=TOOLS, stream=True)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
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
            for call in calls:
                try:
                    result = run_tool(call["function"]["name"], json.loads(call["function"]["arguments"]), conversation_id)
                except Exception as error:
                    result = {"error":str(error)}
                messages.append({"role":"tool", "tool_call_id":call["id"], "content":json.dumps(result, ensure_ascii=False)})
    except APITimeoutError as error:
        raise ModelServiceError("学校大模型连接超时。请检查校园网或 VPN 后重试。", 504) from error
    except APIConnectionError as error:
        raise ModelServiceError("无法连接学校大模型服务。请检查网络后重试。", 502) from error
    except APIStatusError as error:
        raise ModelServiceError(f"学校大模型服务返回异常（状态码 {error.status_code}）。", 502) from error
    raise ModelServiceError("工具调用次数过多，已停止本次请求。", 500)
