from database.crud import save_memory

PENDING_MEMORIES: dict[str, dict] = {}


def propose_memory(conversation_id, content, category="general"):
    """仅暂存待确认的长期记忆，不会写入数据库。"""
    PENDING_MEMORIES[conversation_id] = {"content": content.strip(), "category": category}
    return {"confirmation_required": True, "memory": PENDING_MEMORIES[conversation_id]}


def confirm_pending_memory(conversation_id):
    memory = PENDING_MEMORIES.get(conversation_id)
    if not memory:
        return {"saved": False, "reason": "没有待确认的长期记忆。"}
    saved = save_memory(**memory)
    PENDING_MEMORIES.pop(conversation_id, None)
    return {"saved": True, "memory": saved}
