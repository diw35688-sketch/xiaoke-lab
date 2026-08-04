import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", os.getenv("BASE_URL", "https://api.llm.ustc.edu.cn/v1"))
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-pro")
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY", "")
INWORLD_VOICE_ID = os.getenv("INWORLD_VOICE_ID", "")
DATABASE_PATH = BASE_DIR / "lab_agent.db"
