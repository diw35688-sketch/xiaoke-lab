import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", os.getenv("BASE_URL", "https://api.llm.ustc.edu.cn/v1"))
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-pro")

# 语音合成只使用本机 Qwen 服务。
LOCAL_QWEN_TTS_URL = os.getenv("LOCAL_QWEN_TTS_URL", "http://127.0.0.1:8001/tts").rstrip("/")

DATABASE_PATH = BASE_DIR / "lab_agent.db"
