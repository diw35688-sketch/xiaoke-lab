"""本地 TTS HTTP 服务。模型逻辑在 local_tts/engine.py。"""
import io
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from local_tts.engine import engine

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "voice" / "outputs"
generation_lock = threading.Lock()


def next_output_path():
    numbers = [int(match.group(1)) for item in OUTPUT_DIR.glob("reply_*.wav") if (match := re.fullmatch(r"reply_(\d+)\.wav", item.name))]
    return OUTPUT_DIR / f"reply_{max(numbers, default=0) + 1:03d}.wav"


@asynccontextmanager
async def lifespan(_: FastAPI):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine.load()
    # 预热 CUDA 和生成链路：不保存、不返回，只改善后续首句响应速度。
    with generation_lock:
        engine.synthesize("你好。")
    yield


app = FastAPI(title="Local Qwen3-TTS", lifespan=lifespan)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": engine.model is not None, "output_directory": str(OUTPUT_DIR)}


@app.post("/tts")
def tts(request: TTSRequest):
    try:
        with generation_lock:
            wavs, sample_rate = engine.synthesize(request.text)
            output_path = next_output_path()
            sf.write(output_path, wavs[0], sample_rate, format="WAV")
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    audio = io.BytesIO()
    sf.write(audio, wavs[0], sample_rate, format="WAV")
    return Response(content=audio.getvalue(), media_type="audio/wav", headers={"X-Output-File": output_path.name})
