from database.db import get_connection, initialize_database
from database.crud import list_memories


def get_memories():
    return list_memories()


def delete_memory(memory_id: int):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    return bool(cursor.rowcount)


def clear_memories():
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM memories")
    return cursor.rowcount
