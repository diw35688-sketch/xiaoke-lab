# -*- coding: utf-8 -*-
"""静态资源缓存戳守护测试。

事故（2026-08-30）：theme.css 加了整个纸面皮肤块，但 app.py 里手写的 `?v=` 没改，
浏览器按戳吃缓存 → 发的是旧样式表 → 皮肤整轮"没生效"，且现象极具误导性
（shell.js 是新的、body 挂上了 skin-paper，却没有样式接住它）。

根治方式：`_stamp_assets()` 在渲染时给所有 /static 的 js/css 统一打 BUILD_VERSION，
不再逐个手敲。本测试锁住这个机制：
1. 渲染出的首页里，每个静态资源都带 `?v=`（无戳=用户可能永远吃缓存）；
2. 全站只用同一个戳（版本错配不可能发生）；
3. 手写的旧戳会被统一覆盖（避免"改了常量但某个文件还挂着旧戳"）。
"""

import re
import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

ASSET_RE = re.compile(r'/static/[A-Za-z0-9_\-./]+\.(?:js|css)(\?v=[^"\']*)?')


class AssetCacheStampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        tests_dir = str(Path(__file__).resolve().parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)

        from fastapi.testclient import TestClient

        import auth as auth_core
        import auth_helpers
        from app import app
        from database import db

        # 首页现在需要登录；同时把库指向临时文件，测试不该写生产库。
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._patches = [
            patch.object(db, "DATABASE_PATH", Path(cls._tmp.name) / "assets.db"),
            patch.object(auth_core, "DEFAULT_ITERATIONS", 1000),
        ]
        for item in cls._patches:
            item.start()
        db.initialize_database()
        with TestClient(app) as client:
            auth_helpers.login(client)
            cls.html = client.get("/").text
        for item in reversed(cls._patches):
            item.stop()
        cls._tmp.cleanup()

    def test_every_rendered_asset_carries_a_version_stamp(self):
        missing = [m.group(0) for m in ASSET_RE.finditer(self.html) if not m.group(1)]
        self.assertEqual(
            missing, [],
            f"这些静态资源没有 ?v= 缓存戳，改了内容用户也拿不到新版：{missing}",
        )

    def test_all_assets_share_one_build_version(self):
        stamps = {m.group(1) for m in ASSET_RE.finditer(self.html)}
        self.assertEqual(
            len(stamps), 1,
            f"全站应只有一个版本戳，实际出现多个：{sorted(stamps)}",
        )

    def test_stamper_overrides_handwritten_stamps(self):
        from app import BUILD_VERSION, _stamp_assets

        stamped = _stamp_assets(
            '<link href="/static/theme.css?v=old-stamp">'
            '<script src="/static/shell.js"></script>'
        )
        self.assertNotIn("old-stamp", stamped)
        self.assertEqual(stamped.count(f"?v={BUILD_VERSION}"), 2)


if __name__ == "__main__":
    unittest.main()
