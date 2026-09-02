# -*- coding: utf-8 -*-
"""开发/打包脚本：生成最终用户免下载的 exe。

这个脚本只在“开发者打包”时运行，最终用户不会运行它。
它会：
  1. 如果 bin/cloudflared.exe 不存在，先下载到项目 bin；
  2. 安装 PyInstaller；
  3. 把 web / models / data / bin 全部打进 exe 目录。

最终用户拿到的是 dist/AI107LabAssistant/ 目录，双击 AI107LabAssistant.exe 即可，
不需要再下载模型、不需要再下载 cloudflared、不需要配置。
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
CLOUDFLARED_EXE = BIN_DIR / "cloudflared.exe"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)
STAGING_DIR = ROOT / "build" / "runtime_payload"


def prepare_runtime_payload() -> Path:
    """Create a release-safe Web payload without local secrets or runtime data."""
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    staged_web = STAGING_DIR / "web"
    excluded_dirs = {
        "__pycache__", "certs", "uploads", "audio", "logs", "results",
    }
    excluded_names = {
        ".env", "settings.json", "lab_assistant.db", "lab_assistant.sqlite",
    }

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in excluded_dirs or name in excluded_names:
                ignored.add(name)
            elif name.endswith((".db", ".sqlite", ".sqlite3", ".log")):
                ignored.add(name)
        return ignored

    shutil.copytree(ROOT / "web", staged_web, ignore=ignore)
    print(f"[OK] 已生成无密钥运行资源：{staged_web}")
    return staged_web


def ensure_cloudflared() -> None:
    if CLOUDFLARED_EXE.exists():
        print(f"[OK] 项目内已有 cloudflared：{CLOUDFLARED_EXE}")
        return
    print("[*] 打包前自动下载 cloudflared（仅开发者打包时执行，最终用户不需要）...")
    BIN_DIR.mkdir(exist_ok=True)
    tmp = CLOUDFLARED_EXE.with_suffix(".exe.download")
    urllib.request.urlretrieve(CLOUDFLARED_URL, tmp)
    tmp.replace(CLOUDFLARED_EXE)
    print("[OK] cloudflared 已下载")


def main() -> None:
    ensure_cloudflared()
    staged_web = prepare_runtime_payload()

    print("[*] 检查/安装 PyInstaller ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    print("[*] 开始打包，可能需要几分钟...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir",
        "--name", "AI107LabAssistant",
        "--paths", str(ROOT / "web"),
        "--paths", str(ROOT / "src"),
        "--paths", str(ROOT / "scripts"),
        "--hidden-import", "app",
        "--collect-all", "funasr",
        "--collect-all", "modelscope",
        "--collect-all", "sherpa_onnx",
        "--add-data", f"{staged_web};web",
        "--add-data", f"{ROOT / 'src'};src",
        "--add-data", f"{ROOT / 'scripts'};scripts",
        "--add-data", f"{ROOT / 'models'};models",
        "--add-data", f"{ROOT / 'data'};data",
        "--add-data", f"{BIN_DIR};bin",
        "--add-data", f"{ROOT / 'requirements.txt'};.",
        str(ROOT / "scripts" / "launcher.py"),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    print("=" * 60)
    print("打包完成。最终用户目录：")
    print("  dist/AI107LabAssistant/")
    print("用户只需要双击：")
    print("  dist/AI107LabAssistant/AI107LabAssistant.exe")
    print("=" * 60)


if __name__ == "__main__":
    main()
