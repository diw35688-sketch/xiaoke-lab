import base64
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from config import INWORLD_API_KEY, INWORLD_VOICE_ID

router=APIRouter(prefix="/tts",tags=["语音"])
class TTSRequest(BaseModel): text:str=Field(min_length=1,max_length=2000)
@router.post("")
async def synthesize_speech(request:TTSRequest):
 if not INWORLD_API_KEY or not INWORLD_VOICE_ID: raise HTTPException(503,"尚未配置 Inworld TTS。请检查 .env。")
 payload={"text":request.text,"voiceId":INWORLD_VOICE_ID,"modelId":"inworld-tts-2","audioConfig":{"audioEncoding":"MP3","sampleRateHertz":22050},"deliveryMode":"BALANCED","applyTextNormalization":"ON"}
 try:
  async with httpx.AsyncClient(timeout=45) as client: upstream=await client.post("https://api.inworld.ai/tts/v1/voice",headers={"Authorization":f"Basic {INWORLD_API_KEY}"},json=payload)
 except httpx.RequestError as error: raise HTTPException(502,"无法连接 Inworld TTS 服务。") from error
 if upstream.is_error: raise HTTPException(502,f"Inworld TTS 请求失败（状态码 {upstream.status_code}）。")
 try: audio=base64.b64decode(upstream.json()["audioContent"])
 except (KeyError,ValueError) as error: raise HTTPException(502,"Inworld TTS 返回了无法解析的音频。") from error
 return Response(content=audio,media_type="audio/mpeg")
