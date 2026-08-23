import logging
import time
from datetime import datetime

from src.asr.factory import (
    create_asr_backend,
)
from src.audio.feedback import (
    play_wake_tone,
)
from src.audio.vad_recorder import (
    VadAudioRecorder,
)
from src.config import (
    RESULTS_DIR,
    SESSION_CONTEXT_MAX_EVENTS,
    UI_MODE,
    WAKEWORD_KEYWORDS_FILE,
    WAKEWORD_MODEL_DIR,
)
from src.core.interaction_command import (
    InteractionCommandParser,
    InteractionCommandType,
)
from src.core.pending_clarification import (
    ClarificationStatus,
)
from src.core.reply_coordinator import (
    ReplyCoordinator,
)
from src.core.session_context import (
    SessionContext,
)
from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypass
from src.core.unified_observer import (
    UnifiedObserver,
)
from src.core.ordered_task_queue import (
    OrderedTaskQueue,
)
from src.core.unified_segment_processor import (
    SegmentJob,
    UnifiedSegmentProcessor,
)
from src.core.presentation_coordinator import (
    PresentationCoordinator,
)
from src.core.presentation_copy import (
    ProgramStatus,
    ReviewItem,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.presentation_projection import (
    messages_for_observation,
    messages_for_program_status,
    messages_for_review,
    messages_for_wake_ack,
)
from src.core.presentation_pump import (
    PresentationDeliveryError,
    PresentationPump,
)
from src.core.presentation_timing import (
    IdleNoticeTracker,
)
from src.core.terminal_renderer import (
    TerminalRenderer,
)
from src.core.retry import (
    next_backoff_delay,
)
from src.core.state_manager import (
    StateManager,
)
from src.core.states import (
    AssistantState,
)
from src.llm.factory import (
    create_llm_client,
)
from src.storage.event_store import (
    ExperimentEventStore,
)
from src.llm.unified_processor import UnifiedUnderstandingProcessor
from src.llm.unified_router import UnifiedUnderstandingRouter
from src.storage.confirmation_store import (
    ConfirmationStore,
)
from src.storage.result_store import (
    ASRResultStore,
)
from src.wakeword.detector import (
    WakeWordDetector,
)

SESSION_IDLE_TIMEOUT_SECONDS = 5 * 60

def normalize_command(
    text: str,
) -> str:
    """
    清除空格和常见标点，
    便于匹配语音控制指令。
    """

    return InteractionCommandParser.normalize(text)

def is_end_session_command(
    text: str,
) -> bool:
    """
    判断识别文本是否为结束会话指令。
    """

    command = InteractionCommandParser.parse(text)
    return command.command_type == InteractionCommandType.END_SESSION

def is_affirm_command(
    text: str,
) -> bool:
    """
    判断识别文本是否为肯定答复（"是/是的/对…"）。
    """

    command = InteractionCommandParser.parse(text)
    return command.command_type == InteractionCommandType.AFFIRM

def create_unified_observer() -> UnifiedObserver:
    """创建统一理解链观察器；统一链是唯一默认路径。"""

    logging.info("统一理解链已启用（唯一默认路径）。")
    processor = UnifiedUnderstandingProcessor(create_llm_client())
    router = UnifiedUnderstandingRouter(processor)
    return UnifiedObserver(UnifiedAcceptanceBypass(router))

def recognize_one_segment(
    *,
    recorder,
    recognizer,
    state_manager: StateManager,
):
    """
    录制并识别一段实验口述。

    本函数只负责录音和 ASR，
    不负责保存、LLM 或上下文。
    """

    state_manager.change_to(
        AssistantState.LISTENING
    )

    audio_path = (
        recorder.record_until_silence()
    )

    state_manager.change_to(
        AssistantState.PROCESSING
    )

    return recognizer.recognize(
        audio_path
    )

def account_completed_task(task) -> bool:
    """统计一个已完成的后台任务；失败时报错，返回它是否算实验段。"""

    if task.error is not None:
        logging.error(
            "统一链第%s段处理失败：%s",
            task.item.segment_id,
            task.error,
        )
        return False
    return task.result.observation.is_experiment_evidence

def run_experiment_session(
    *,
    recorder,
    recognizer,
    asr_store: ASRResultStore,
    event_store: ExperimentEventStore,
    confirmation_store: ConfirmationStore,
    state_manager: StateManager,
    observer: UnifiedObserver,
    executor=None,
    presentation_coordinator: PresentationCoordinator | None = None,
    presentation_pump: PresentationPump | None = None,
) -> None:
    """
    运行一次完整实验会话。

    主线程只负责：录音、ASR、判断结束指令、提交后台任务、显示结果。
    观察/落盘/兜底/执行/确认等业务逻辑在后台单线程按序执行，
    因此录音不必等待 LLM 处理完成。
    """

    session_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    session_context = (
        SessionContext(
            max_events=(
                SESSION_CONTEXT_MAX_EVENTS
            )
        )
    )

    # ReplyCoordinator 是会话级状态。
    # 新实验会创建新实例，避免问题跨会话残留。
    reply_coordinator = (
        ReplyCoordinator()
    )

    # 执行器是会话级对象；默认创建真实执行器，
    # 测试时可注入 Fake 以避免真实 LLM 提取器。
    if executor is None:
        from src.core.clarification_executor import (
            AnswerEntityExtractor,
            ClarificationExecutor
        )
        executor = ClarificationExecutor(
            reply_coordinator,
            entity_extractor=AnswerEntityExtractor(create_llm_client())
        )

    # 会话级"待确认结束"标志：后台识别到结束意图时置真，主循环读它。
    pending_end_confirmation = {"value": False}

    # 生产环境复用程序级 pump，保证启动/唤醒/会话/退出共用单一输出权。
    # 独立测试可不注入，由本函数创建并回收本地呈现链。
    owns_presentation = presentation_coordinator is None
    if owns_presentation:
        coordinator = PresentationCoordinator()
        renderer = TerminalRenderer(ui_mode=UI_MODE)
        pump = PresentationPump(coordinator, renderer, output=print)
        pump.start()
    else:
        if presentation_pump is None:
            raise ValueError(
                "注入 presentation_coordinator 时必须同时注入 presentation_pump。"
            )
        coordinator = presentation_coordinator
        pump = presentation_pump

    # 实验步骤计数器：只对结构化实验段递增，供投影层做编号分离（UX-07）。
    experiment_step_counter = {"value": 0}

    # 主线程用户消息的唯一出口：固定提示投递给 pump。
    emit_counter = {"value": 0}

    def emit(
        kind,
        text,
        *,
        priority=MessagePriority.ROUTINE,
        screen_target=ScreenTarget.STATUS,
    ) -> None:
        emit_counter["value"] += 1
        coordinator.submit([PresentationIntent(
            intent_id=f"main-{emit_counter['value']}",
            kind=kind,
            args={"text": text},
            priority=priority,
            screen_target=screen_target,
        )])

    def display_segment_outcome(outcome) -> None:
        """后台算完时投递呈现意图；开发详情只进日志。"""

        observation = outcome.observation
        logging.debug(
            "统一链第%s段：目标=%s，采用=%s，待确认动作=%s，"
            "已执行=%s，执行原因=%s",
            observation.segment_id,
            observation.destination,
            observation.acceptance_kind or "none",
            observation.clarification_action,
            observation.executed,
            observation.execution_reason,
        )

        step_number = None
        if observation.acceptance_kind == "structured_experiment":
            experiment_step_counter["value"] += 1
            step_number = experiment_step_counter["value"]

        intents = list(messages_for_observation(
            observation,
            experiment_step_number=step_number,
        ))
        if outcome.review_summary is not None:
            intents.extend(messages_for_review(
                outcome.review_summary,
                request_id=observation.request_id,
            ))

        coordinator.submit(intents)

        if observation.end_confirmation_requested:
            pending_end_confirmation["value"] = True

    worker = UnifiedSegmentProcessor(
        session_id=session_id,
        observer=observer,
        executor=executor,
        asr_store=asr_store,
        event_store=event_store,
        confirmation_store=confirmation_store,
        reply_coordinator=reply_coordinator,
        session_context=session_context,
        display=display_segment_outcome,
    )

    queue = OrderedTaskQueue(
        worker=worker.process,
        max_pending_tasks=4,
    )

    utterance_count = 0
    experiment_segment_count = 0

    last_activity_time = (
        time.monotonic()
    )
    idle_notice_tracker = IdleNoticeTracker()

    state_manager.change_to(
        AssistantState.SESSION_ACTIVE
    )

    emit(
        MessageKind.STAGE_SUMMARY,
        "实验记录会话已开始。\n"
        f"会话编号：{session_id}\n"
        "现在可以连续口述，无需等待 LLM 处理完成。\n"
        "说“结束实验记录”可以结束本次会话。\n"
        "请开始口述实验过程，说完后自然停顿即可。",
    )

    while True:
        try:
            asr_result = (
                recognize_one_segment(
                    recorder=recorder,
                    recognizer=recognizer,
                    state_manager=(
                        state_manager
                    )
                )
            )

            last_activity_time = (
                time.monotonic()
            )
            idle_notice_tracker.reset()

            emit(
                MessageKind.TRANSCRIPT,
                f"本段 ASR 识别完成：{asr_result.asr_transcript}",
            )

            # 结束命令不写入 ASR 文件，
            # 也不发送给后台。
            if is_end_session_command(
            asr_result.asr_transcript
            ):
                emit(
                    MessageKind.STAGE_SUMMARY,
                    "检测到结束指令，停止接收新的实验口述。",
                )
                break

            if (
                pending_end_confirmation["value"]
                and is_affirm_command(asr_result.asr_transcript)
            ):
                emit(
                    MessageKind.STAGE_SUMMARY,
                    "确认结束，停止接收新的实验口述。",
                )
                break

            # 提前分配编号。
            #
            # 即使后台保存失败，
            # 下一段也不会重复使用此编号。
            utterance_count += 1
            segment_id = (
                utterance_count
            )

            # 提交后台处理；返回本次提交前已完成的结果。
            completed = queue.submit(
                item=SegmentJob(
                    segment_id=segment_id,
                    asr_result=asr_result,
                )
            )
            for task in completed:
                if account_completed_task(task):
                    experiment_segment_count += 1

        except TimeoutError:
            idle_seconds = (
                time.monotonic()
                - last_activity_time
            )

            if (
                idle_seconds
                >= (
                    SESSION_IDLE_TIMEOUT_SECONDS
                )
            ):
                emit(
                    MessageKind.STAGE_SUMMARY,
                    "实验会话长时间无口述，停止接收新输入。",
                )
                break

            remaining_seconds = (
                SESSION_IDLE_TIMEOUT_SECONDS
                - idle_seconds
            )

            idle_notice = idle_notice_tracker.message_for_timeout(
                remaining_seconds
            )
            if idle_notice is not None:
                emit(MessageKind.STAGE_SUMMARY, idle_notice)

        except Exception as error:
            emit(
                MessageKind.SYSTEM_ISSUE,
                "本段录音或识别失败："
                f"{type(error).__name__}: {error}。"
                "当前实验会话仍然有效，系统将继续监听。",
            )

        finally:
            state_manager.change_to(
                AssistantState.SESSION_ACTIVE
            )

    # 排空后台：等待所有已提交任务完成并统计。
    for task in queue.finish():
        if account_completed_task(task):
            experiment_segment_count += 1

    logging.debug(
        "最终上下文包含 %s 条事件。",
        len(session_context),
    )

    active = reply_coordinator.active_clarifications()
    coordinator.submit([PresentationIntent(
        intent_id=f"{session_id}-closing-summary",
        kind=MessageKind.SESSION_CLOSING_SUMMARY,
        args={
            "experiment_step_count": experiment_segment_count,
            "pending_items": tuple(
                ReviewItem(
                    display_number=clarification.display_number,
                    is_deferred=(
                        clarification.status
                        == ClarificationStatus.DEFERRED
                    ),
                    question=clarification.question,
                )
                for clarification in active
            ),
        },
        priority=MessagePriority.SUMMARY,
        screen_target=ScreenTarget.SUMMARY,
    )])

    # flush 同时等待队列中和已取走正在交付的消息。
    try:
        if not pump.flush(timeout=2.0):
            logging.error("会话收尾呈现交付超时。")
    except PresentationDeliveryError as error:
        logging.error("会话收尾呈现交付失败：%s", error)
    if owns_presentation:
        pump.stop(timeout=1)

def configure_logging() -> None:
    """按 UI_MODE 配置日志：user 写文件，admin 输出屏幕。"""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if UI_MODE == "user":
        logging.basicConfig(
            level=logging.DEBUG,
            filename=str(RESULTS_DIR / "debug.log"),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s %(name)s: %(message)s",
        )


def main() -> None:
    """
    程序组合根。

    在这里创建程序级对象，
    并明确它们之间的依赖关系。
    """

    configure_logging()

    presentation_coordinator = PresentationCoordinator()
    presentation_renderer = TerminalRenderer(ui_mode=UI_MODE)
    presentation_pump = PresentationPump(
        presentation_coordinator,
        presentation_renderer,
        output=print,
    )
    presentation_pump.start()
    program_intent_counter = 0

    def next_program_request_id() -> str:
        nonlocal program_intent_counter
        program_intent_counter += 1
        return f"program-{program_intent_counter}"

    def stop_presentation() -> None:
        """确认已入队的程序级反馈完成交付后停止 pump。"""

        try:
            if not presentation_pump.flush(timeout=2.0):
                logging.error("程序退出时呈现交付超时。")
        except PresentationDeliveryError as error:
            logging.error("程序退出时呈现交付失败：%s", error)
        presentation_pump.stop(timeout=1)

    presentation_coordinator.submit(messages_for_program_status(
        ProgramStatus.STARTING,
        request_id=next_program_request_id(),
    ))

    try:
        state_manager = StateManager()

        recorder = VadAudioRecorder(
            start_timeout_seconds=30.0
        )

        asr_store = ASRResultStore()

        confirmation_store = (
            ConfirmationStore()
        )

        event_store = (
            ExperimentEventStore()
        )

        observer = create_unified_observer()

        # ASR 模型只在程序启动时加载一次。
        recognizer = create_asr_backend()

        # 唤醒模型也只在程序启动时加载一次。
        wakeword_detector = WakeWordDetector(
            model_dir=WAKEWORD_MODEL_DIR,
            keywords_file=WAKEWORD_KEYWORDS_FILE,
        )
    except KeyboardInterrupt:
        presentation_coordinator.submit(messages_for_program_status(
            ProgramStatus.EXITED,
            request_id=next_program_request_id(),
        ))
        stop_presentation()
        return

    presentation_coordinator.submit(messages_for_program_status(
        ProgramStatus.READY,
        request_id=next_program_request_id(),
    ))

    # 唤醒连续失败次数：每次失败按指数退避等待，
    # 成功后重置为 0，避免音频设备异常时疯狂转圈。
    consecutive_failures = 0

    try:
        while True:
            try:
                state_manager.change_to(
                    AssistantState.IDLE
                )

                detected_keyword = (
                    wakeword_detector
                    .wait_for_wake_word()
                )
                consecutive_failures = 0

                presentation_coordinator.submit(messages_for_wake_ack(
                    detected_keyword,
                    request_id=next_program_request_id(),
                ))

                play_wake_tone()

                run_experiment_session(
                    recorder=recorder,
                    recognizer=recognizer,
                    asr_store=asr_store,
                    event_store=event_store,
                    confirmation_store=(
                        confirmation_store
                    ),
                    state_manager=(
                        state_manager
                    ),
                    observer=observer,
                    presentation_coordinator=presentation_coordinator,
                    presentation_pump=presentation_pump,
                )
                presentation_coordinator.submit(messages_for_program_status(
                    ProgramStatus.WAITING,
                    request_id=next_program_request_id(),
                ))
            except Exception as error:
                consecutive_failures += 1
                retry_delay = next_backoff_delay(
                    consecutive_failures
                )
                logging.error(
                    "唤醒或会话异常：%s: %s。"
                    "系统将重新进入待机状态，%.1f 秒后重试"
                    "（连续第 %s 次）。",
                    type(error).__name__,
                    error,
                    retry_delay,
                    consecutive_failures,
                )
                time.sleep(retry_delay)
            finally:
                state_manager.change_to(
                    AssistantState.IDLE
                )
    except KeyboardInterrupt:
        presentation_coordinator.submit(messages_for_program_status(
            ProgramStatus.EXITED,
            request_id=next_program_request_id(),
        ))
    finally:
        stop_presentation()

if __name__ == "__main__":
    main()
