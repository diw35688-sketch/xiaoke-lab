import os
from pathlib import Path

from dotenv import load_dotenv


# ==================================================
# 项目路径
# ==================================================

SRC_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

PROJECT_DIR = SRC_DIR.parent

ENV_FILE = PROJECT_DIR / ".env"


# ==================================================
# 加载本地环境配置
# ==================================================

# override=False 表示：
# 系统环境变量优先于 .env。
load_dotenv(
    dotenv_path=ENV_FILE,
    override=False,
)


# ==================================================
# 通用目录
# ==================================================

AUDIO_DIR = PROJECT_DIR / "audio"
RAW_AUDIO_DIR = AUDIO_DIR / "raw"
WAV_AUDIO_DIR = AUDIO_DIR / "wav"

RECORDINGS_DIR = (
    AUDIO_DIR
    / "recordings"
)

DATA_DIR = PROJECT_DIR / "data"

# 试剂安全知识库（PubChem 事实数据 + GB 30000 中文表述）
HAZMAT_FILE = (
    DATA_DIR
    / "hazmat"
    / "reagent_safety.json"
)
HAZMAT_SCHEMA_VERSION = 1

RESULTS_DIR = PROJECT_DIR / "results"

RESULTS_FILE = (
    RESULTS_DIR
    / "asr_segments.jsonl"
)
EVENTS_FILE = (
    RESULTS_DIR
    / "experiment_events.jsonl"
)
CONFIRMATIONS_FILE = (
    RESULTS_DIR
    / "experiment_confirmations.jsonl"
)


TEST_AUDIO = (
    WAV_AUDIO_DIR
    / "03_terms_second.wav"
)


# ==================================================
# 音频配置
# ==================================================

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"


# ==================================================
# TTS 配置
# ==================================================

TTS_BACKEND = os.getenv(
    "TTS_BACKEND",
    "null",
).strip().lower()


# ==================================================
# ASR 配置
# ==================================================

ASR_BACKEND = os.getenv(
    "ASR_BACKEND",
    "sensevoice",
).strip().lower()

ASR_SENSEVOICE_MODEL = os.getenv(
    "ASR_SENSEVOICE_MODEL",
    "iic/SenseVoiceSmall",
).strip()

# 暂时保留旧名称，避免外部脚本在迁移期间中断。
ASR_MODEL = ASR_SENSEVOICE_MODEL
VAD_MODEL = "fsmn-vad"
DEVICE = "cpu"


def read_bool(variable_name: str, default: str = "false") -> bool:
    """严格读取布尔开关，避免拼写错误意外开放功能。"""

    raw_value = os.getenv(variable_name, default).strip().lower()
    if raw_value in {"true", "1", "yes", "on"}:
        return True
    if raw_value in {"false", "0", "no", "off"}:
        return False
    raise RuntimeError(
        f"{variable_name} 必须是 true 或 false，当前值为：{raw_value!r}"
    )


TTS_ENABLED = read_bool("TTS_ENABLED")



# ==================================================
# 唤醒词配置
# ==================================================

WAKEWORD_MODEL_DIR = (
    PROJECT_DIR
    / "models"
    / "wakeword"
    / (
        "sherpa-onnx-kws-"
        "zipformer-zh-en-3M-"
        "2025-12-20"
    )
)

WAKEWORD_KEYWORDS_FILE = (
    PROJECT_DIR
    / "models"
    / "wakeword"
    / "custom"
    / "keywords.txt"
)


# ==================================================
# VAD 配置
# ==================================================

VAD_MODEL_PATH = (
    PROJECT_DIR
    / "models"
    / "vad"
    / "silero_vad.onnx"
)


# ==================================================
# LLM 配置辅助函数
# ==================================================

def read_positive_float(
    variable_name: str,
    default: str,
) -> float:
    """
    从环境变量读取正浮点数。

    配置错误时尽早给出明确提示，
    避免在网络请求阶段
    才出现模糊错误。
    """

    raw_value = os.getenv(
        variable_name,
        default,
    )

    try:
        value = float(
            raw_value
        )
    except ValueError as error:
        raise RuntimeError(
            f"{variable_name} 必须是数字，"
            f"当前值为：{raw_value!r}"
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{variable_name} 必须大于 0，"
            f"当前值为：{value}"
        )

    return value


def read_positive_int(
    variable_name: str,
    default: str,
) -> int:
    """
    从环境变量读取正整数。
    """

    raw_value = os.getenv(
        variable_name,
        default,
    )

    try:
        value = int(
            raw_value
        )
    except ValueError as error:
        raise RuntimeError(
            f"{variable_name} 必须是整数，"
            f"当前值为：{raw_value!r}"
        ) from error

    if value <= 0:
        raise RuntimeError(
            f"{variable_name} 必须大于 0，"
            f"当前值为：{value}"
        )

    return value


# ==================================================
# LLM 字符串配置
# ==================================================

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://api.deepseek.com",
).strip()

LLM_API_KEY = os.getenv(
    "LLM_API_KEY",
    "",
).strip()

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "deepseek-v4-flash",
).strip()


# ==================================================
# LLM 数值配置
# ==================================================

LLM_TIMEOUT_SECONDS = (
    read_positive_float(
        "LLM_TIMEOUT_SECONDS",
        "30",
    )
)

LLM_MAX_TOKENS = (
    read_positive_int(
        "LLM_MAX_TOKENS",
        "2000",
    )
)

# 最多尝试2次：
# 第一次请求加一次重试。
LLM_MAX_ATTEMPTS = (
    read_positive_int(
        "LLM_MAX_ATTEMPTS",
        "2",
    )
)

LLM_RETRY_DELAY_SECONDS = (
    read_positive_float(
        "LLM_RETRY_DELAY_SECONDS",
        "0.5",
    )
)


# ==================================================
# 实验会话配置
# ==================================================

SESSION_CONTEXT_MAX_EVENTS = 8

# 单次实验会话允许积压的
# 最大后台处理任务数。
SESSION_MAX_PENDING_TASKS = 4


# ==================================================
# 输出呈现配置
# ==================================================

UI_MODE = os.getenv("UI_MODE", "user").strip().lower()
if UI_MODE not in {"user", "admin"}:
    raise RuntimeError(
        f"UI_MODE 必须是 user 或 admin，当前值为：{UI_MODE!r}"
    )
