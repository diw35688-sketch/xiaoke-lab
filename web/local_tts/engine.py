import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from qwen_tts import Qwen3TTSModel

BASE_DIR = Path(__file__).resolve().parents[1]
VOICE_DIR = BASE_DIR / "voice"
REFERENCE_AUDIO = VOICE_DIR / "reference.wav"
CONFIG_DIR = Path(__file__).resolve().parent

# 默认读取原有克隆音配置；custom_voice.env 存在时会覆盖为预置音色配置。
load_dotenv(CONFIG_DIR / ".env")
load_dotenv(CONFIG_DIR / "custom_voice.env", override=True)


class QwenVoiceEngine:
    def __init__(self):
        self.model = None
        self.voice_clone_prompt = None
        self.mode = "clone"
        self.speaker = None
        self.instruct = ""

    def load(self):
        self.mode = os.getenv("QWEN_TTS_MODE", "clone").strip().lower()
        device = os.getenv("QWEN_TTS_DEVICE", "cuda:0")
        dtype_name = os.getenv("QWEN_TTS_DTYPE", "bfloat16")
        dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}.get(dtype_name)
        if dtype is None:
            raise RuntimeError("QWEN_TTS_DTYPE 只能是 float16 或 bfloat16。")
        if not torch.cuda.is_available():
            raise RuntimeError("未检测到可用 NVIDIA CUDA 显卡；本地 Qwen TTS 建议使用 GPU。")

        if self.mode == "custom":
            model_path = os.getenv("QWEN_TTS_CUSTOM_MODEL_PATH", "").strip()
            self.speaker = os.getenv("QWEN_TTS_SPEAKER", "Serena").strip() or "Serena"
            self.instruct = os.getenv(
                "QWEN_TTS_INSTRUCT",
                "自然、温柔、有亲和力的年轻女声；语速适中，适合实验室助手交流。",
            ).strip()
            if not model_path or not Path(model_path).is_dir():
                raise RuntimeError("未找到 CustomVoice 模型，请完成下载后检查 local_tts/custom_voice.env。")
            self.model = Qwen3TTSModel.from_pretrained(model_path, device_map=device, dtype=dtype)
            return

        if self.mode != "clone":
            raise RuntimeError("QWEN_TTS_MODE 只能是 clone 或 custom。")
        model_path = os.getenv("QWEN_TTS_MODEL_PATH", "").strip()
        reference_text = os.getenv("QWEN_TTS_REFERENCE_TEXT", "").strip()
        if not model_path:
            raise RuntimeError("缺少 QWEN_TTS_MODEL_PATH，请填写 local_tts/.env。")
        if not reference_text:
            raise RuntimeError("缺少 QWEN_TTS_REFERENCE_TEXT，请填写 local_tts/.env。")
        if not REFERENCE_AUDIO.is_file():
            raise RuntimeError(f"未找到参考音频：{REFERENCE_AUDIO}")
        self.model = Qwen3TTSModel.from_pretrained(model_path, device_map=device, dtype=dtype)
        self.voice_clone_prompt = self.model.create_voice_clone_prompt(
            ref_audio=str(REFERENCE_AUDIO),
            ref_text=reference_text,
        )

    def synthesize(self, text: str):
        if self.model is None:
            raise RuntimeError("模型尚未加载完成。")
        if self.mode == "custom":
            return self.model.generate_custom_voice(
                text=text,
                language="Chinese",
                speaker=self.speaker,
                instruct=self.instruct,
            )
        if self.voice_clone_prompt is None:
            raise RuntimeError("克隆音色提示尚未准备完成。")
        return self.model.generate_voice_clone(
            text=text,
            language="Chinese",
            voice_clone_prompt=self.voice_clone_prompt,
        )


engine = QwenVoiceEngine()
