import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "web"
else:
    BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", os.getenv("LLM_API_KEY", ""))
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", os.getenv("LLM_BASE_URL", os.getenv("BASE_URL", "https://api.deepseek.com/v1")))
MODEL_NAME = os.getenv("MODEL_NAME", os.getenv("LLM_MODEL", "deepseek-chat"))

# 语音合成只使用本机 Qwen 服务。
LOCAL_QWEN_TTS_URL = os.getenv("LOCAL_QWEN_TTS_URL", "http://127.0.0.1:8001/tts").rstrip("/")

DATABASE_PATH = BASE_DIR / "lab_agent.db"
AUDIO_STORAGE_ROOT = BASE_DIR / "data" / "turn_audio"
