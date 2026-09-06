# -*- coding: utf-8 -*-
"""让测试用的 TestClient 带上真实登录态。

为什么不做「测试时关掉鉴权」的开关
--------------------------------
那种开关迟早会因为配置失误出现在生产环境里，而且它让测试跑在
一条真实用户永远不会走的路径上。这里选择让测试真的走一遍注册/登录，
既保证闸门被验证，也不给自己留后门。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

TEST_PASSWORD = "a good lab password"


def isolated_database():
    """返回 (临时目录, 补丁列表)：把数据库指向临时文件，并调低散列轮数。

    调低轮数是因为生产用的 60 万轮 PBKDF2 每次约 325ms，
    测试里注册/登录十几次就要多花好几秒。
    """
    import auth as auth_core
    from database import db

    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    patches = [
        patch.object(db, "DATABASE_PATH", Path(tmp.name) / "test.db"),
        patch.object(auth_core, "DEFAULT_ITERATIONS", 1000),
    ]
    return tmp, patches


def login(client, username: str = "tester", password: str = TEST_PASSWORD):
    """在空库上创建首个账号（自动成为管理员）并保持登录。

    走的是真实的 /auth/register 引导路径，因此这个助手本身
    也在持续验证"没有账号时仍能建号"这条不变量。
    """
    response = client.post(
        "/auth/register", json={"username": username, "password": password})
    if response.status_code != 200:
        raise AssertionError(
            f"测试登录失败：{response.status_code} {response.text[:200]}")
    return response.json()["user"]
