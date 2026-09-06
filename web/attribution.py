# -*- coding: utf-8 -*-
"""实验记录与社区投稿的署名。

为什么存两列
------------
`recorded_by_id`  可追溯：日后改名、合并账号，仍能查到是哪个账号做的。
`recorded_by_name` 当时的显示名快照：实验记录是科学档案，
                  应当反映"当时是谁做的、当时叫什么"，事后改名不该改写历史。
只存 id 会让旧记录跟着改名漂移；只存名字则无法追溯。两列各司其职。

为什么从会话归属反查而不是从请求上下文取
----------------------------------------
记录的落库发生在后台线程（turn_store 提交 Turn 时），那里没有 HTTP 请求上下文。
而 conversations.user_id 已经记录了归属，顺着 conversation_id 查即可，
不必把用户身份一路穿过十几层调用栈。
"""

from __future__ import annotations

from contextlib import closing

from database.db import get_connection

UNKNOWN = ("", "")


def signature_for_conversation(conversation_id: str | None) -> tuple[str, str]:
    """返回 (user_id, display_name)。查不到就退回单账号，再查不到返回空。

    个人使用场景下库里通常只有一个账号，因此"退回唯一账号"覆盖了
    绝大多数情况（例如自由记录模式没有 conversation_id）。
    绝不编造署名：什么都查不到时返回空串，让记录如实显示"未署名"。
    """
    with closing(get_connection()) as connection:
        if conversation_id:
            row = connection.execute(
                "SELECT u.id, u.display_name, u.username FROM conversations c"
                " JOIN users u ON u.id = c.user_id WHERE c.id = ?",
                (conversation_id,),
            ).fetchone()
            if row is not None:
                return row["id"], (row["display_name"] or row["username"])
        rows = connection.execute(
            "SELECT id, display_name, username FROM users"
            " WHERE is_active = 1 ORDER BY created_at LIMIT 2"
        ).fetchall()
    if len(rows) == 1:
        return rows[0]["id"], (rows[0]["display_name"] or rows[0]["username"])
    return UNKNOWN


def signature_of(user) -> tuple[str, str]:
    """把登录态里的用户对象转成署名二元组。"""
    if not user:
        return UNKNOWN
    return user.get("id", ""), (user.get("display_name") or user.get("username") or "")
