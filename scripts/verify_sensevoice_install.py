"""验证 SenseVoice 后端能否成功加载（首次运行会自动下载模型）。

用法（安装完 funasr 后）：
    .\.venv\Scripts\python.exe -B scripts\verify_sensevoice_install.py
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

from src.asr.sensevoice_backend import SenseVoiceBackend  # noqa: E402


def main() -> None:
    print("开始加载 SenseVoice 后端（首次会从 modelscope 下载模型，约 1.2GB，请耐心等待）…")
    started = time.monotonic()
    backend = SenseVoiceBackend()
    elapsed = time.monotonic() - started
    print(f"SenseVoiceBackend 加载成功，耗时 {elapsed:.1f} 秒")
    print(f"模型：{backend.model_name}，设备：{backend.device}")
    print("下一步：调用 recognize 对真实音频做识别验证。")


if __name__ == "__main__":
    main()
