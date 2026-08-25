# -*- coding: utf-8 -*-
r"""打包当前源码为 zip，排除虚拟环境、构建产物、密钥、模型缓存等。

用法（仓库根目录）：
  .\.venv\Scripts\python.exe scripts\package.py
"""

from __future__ import annotations

import datetime
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "dist"
OUT_NAME = f"ai107-source-{datetime.datetime.now():%Y%m%d-%H%M%S}.zip"

# 无论出现在哪一层都排除的目录名
EXCLUDE_DIR_NAMES = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "node_modules",
}

# 精确相对路径排除的目录（源码包不包含运行产物/密钥/模型权重）
EXCLUDE_DIR_PATHS = {
    "audio/raw",
    "audio/recordings",
    "results",
    "web/certs",
    "web/uploads",
    "web/voice/outputs",
    "models/modelscope_cache",
    "models/vad",
    "models/wakeword/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20",
}

# 模型目录里唯一保留的小文件（其余模型权重/缓存都不进源码包）
MODEL_ALLOWED_FILES = {
    "models/wakeword/custom/keywords.txt",
}

# 精确相对路径排除的文件
EXCLUDE_FILES = {
    ".env",
    "web/settings.json",
    "web/lab_agent.db",
    "setup_log.txt",
    "*.pyc",
    "*.pyo",
    "*.spec",
}


def should_skip(rel: str) -> bool:
    # 本机便携解释器及其压缩包可能很大，也不保证兼容接收者电脑。
    if rel.split("/", 1)[0].startswith(".runtime-python"):
        return True
    # 排除 .env / *.env（含密钥/本机路径），但保留 .env.example
    if rel.endswith(".env"):
        return True
    if rel in EXCLUDE_FILES:
        return True
    if rel.endswith((".pyc", ".pyo", ".spec")):
        return True
    if rel.endswith((".log", ".out.log", ".err.log")):
        return True
    # models/ 下只保留自定义唤醒词文本，其余模型缓存不进入源码包
    if rel.startswith("models/"):
        return rel not in MODEL_ALLOWED_FILES
    return False


def prune_dirs(dirpath: Path, dirnames: list[str]) -> None:
    """原地删除不需要递归的目录，避免遍历 .venv/dist 等大目录。"""
    keep: list[str] = []
    for name in dirnames:
        rel_dir = (dirpath / name).relative_to(ROOT).as_posix()
        if name.startswith(".runtime-python"):
            continue
        if name in EXCLUDE_DIR_NAMES:
            continue
        if rel_dir in EXCLUDE_DIR_PATHS:
            continue
        keep.append(name)
    dirnames[:] = keep


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / OUT_NAME
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirpath_obj = Path(dirpath)
            prune_dirs(dirpath_obj, dirnames)
            for filename in sorted(filenames):
                path = dirpath_obj / filename
                rel = path.relative_to(ROOT).as_posix()
                if should_skip(rel):
                    continue
                zf.write(path, arcname=rel)
                count += 1
    print(f"打包完成：{out_path}")
    print(f"文件数：{count}")


if __name__ == "__main__":
    sys.exit(main())
