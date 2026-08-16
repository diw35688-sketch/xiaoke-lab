from fastapi import APIRouter, HTTPException
from database.memory_store import clear_memories, delete_memory, get_memories

router = APIRouter(prefix="/memories", tags=["长期记忆"])


@router.get("")
def list_all_memories():
    return get_memories()


@router.delete("")
def remove_all_memories():
    return {"deleted": clear_memories()}


@router.delete("/{memory_id}")
def remove_memory(memory_id: int):
    if not delete_memory(memory_id):
        raise HTTPException(404, "未找到该长期记忆。")
    return {"deleted": True}
