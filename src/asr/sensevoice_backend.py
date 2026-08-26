"""SenseVoiceSmall对项目统一ASR合同的适配器。"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import soundfile as sf

from src.asr.languages import SUPPORTED_SENSEVOICE_LANGUAGES
from src.asr.schemas import ASRResult
from src.config import (
    ASR_LANGUAGE,
    ASR_SENSEVOICE_MODEL,
    DEVICE,
    PROJECT_DIR,
)


logger = logging.getLogger(__name__)


def _local_sensevoice_path(model_name: str) -> str:
    """Prefer the bundled cache and avoid ModelScope resolution on every boot."""

    supplied = Path(model_name)
    if supplied.is_dir():
        return str(supplied.resolve())
    cache_root = Path(os.getenv(
        "MODELSCOPE_CACHE", str(PROJECT_DIR / "models" / "modelscope_cache")
    ))
    candidate = (
        cache_root / "models" / "iic--SenseVoiceSmall" / "snapshots" / "master"
    )
    return str(candidate.resolve()) if candidate.is_dir() else model_name


class SenseVoiceBackend:
    """隔离SenseVoice的加载参数、输出格式和文本后处理。"""

    def __init__(
        self,
        *,
        model_name: str = ASR_SENSEVOICE_MODEL,
        device: str = DEVICE,
        model_engine: Any | None = None,
        postprocess: Callable[[str], str] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device

        if model_engine is None:
            # FunASR/ModelScope 会在模型初始化期间自行创建 tqdm 和下载日志。
            # 使用依赖原生开关，避免全局重定向 stdout/stderr 吞掉并发 Pump 输出。
            os.environ["TQDM_DISABLE"] = "1"
            logging.getLogger("modelscope_hub.download").setLevel(
                logging.WARNING
            )
            logging.getLogger("modelscope").setLevel(logging.WARNING)

            from funasr import AutoModel
            from funasr.utils import version_checker

            # FunASR 1.4.1 即使 disable_update=True，仍会在检查开关前
            # 直接 print 版本号。只替换该版本检查入口，避免进程级重定向。
            version_checker.check_for_update = lambda disable=False: None

            logger.info("正在加载SenseVoice ASR模型……")
            resolved_model = _local_sensevoice_path(model_name)
            model_engine = AutoModel(
                model=resolved_model,
                device=device,
                disable_update=True,
                disable_pbar=True,
                disable_log=True,
            )
            logger.info("SenseVoice使用本地模型目录：%s", resolved_model)
            logger.info("SenseVoice ASR模型加载完成")

        if postprocess is None:
            from funasr.utils.postprocess_utils import (
                rich_transcription_postprocess,
            )

            postprocess = rich_transcription_postprocess

        self._model_engine = model_engine
        self._postprocess = postprocess

    def recognize(
        self,
        audio_path: Path,
        *,
        language: str = ASR_LANGUAGE,
    ) -> ASRResult:
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(
                f"找不到音频文件：{audio_path}"
            )
        if language not in SUPPORTED_SENSEVOICE_LANGUAGES:
            raise ValueError(
                "SenseVoice language 不受支持："
                f"{language!r}；可选值为："
                f"{sorted(SUPPORTED_SENSEVOICE_LANGUAGES)}"
            )

        audio_info = sf.info(audio_path)
        audio_duration = (
            audio_info.frames / audio_info.samplerate
        )

        logger.debug(f"正在识别：{audio_path}")
        start_time = time.perf_counter()
        result = self._model_engine.generate(
            input=str(audio_path),
            cache={},
            language=language,
            use_itn=True,
            batch_size_s=60,
            disable_pbar=True,
            disable_log=True,
        )
        recognition_seconds = (
            time.perf_counter() - start_time
        )

        if not result:
            raise RuntimeError("FunASR没有返回识别结果")

        raw_text = result[0].get("text", "")
        clean_text = self._postprocess(raw_text)

        return ASRResult(
            asr_transcript=clean_text,
            asr_model_raw_text=raw_text,
            audio_path=str(audio_path.resolve()),
            audio_duration_seconds=round(
                audio_duration,
                3,
            ),
            recognition_seconds=round(
                recognition_seconds,
                3,
            ),
            model=self.model_name,
            language=language,
            is_final=True,
        )
