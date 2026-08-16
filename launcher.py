# -*- coding: utf-8 -*-
"""PyInstaller 入口：最终用户双击这个 exe 后直接启动实验助手。

在打包环境里，所有数据（web / models / data / bin）都会随 exe 一起发布，
最终用户不需要再下载任何模型或 cloudflared。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller onedir 把所有资源和依赖放在 _internal 里
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    ROOT = Path(__file__).resolve().parent

os.chdir(ROOT)
for path in (str(ROOT), str(ROOT / "web"), str(ROOT / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

from start_best import main  # noqa: E402


def run() -> None:
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("程序启动失败，按回车退出...")
        raise


if __name__ == "__main__":
    run()
