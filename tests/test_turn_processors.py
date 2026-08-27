import sys
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from src.core.conversation_turn import (  # noqa: E402
    ExperimentContext, InputSource, InteractionMode,
)
from src.core.turn_input import TurnInput  # noqa: E402
from src.core.turn_timing import TurnTimingRecorder  # noqa: E402
from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypass  # noqa: E402
from src.core.unified_observer import UnifiedObserver  # noqa: E402
from src.core.unified_understanding import (  # noqa: E402
    ExperimentUnderstanding, UnifiedUnderstandingResult,
    UncertainUnderstanding,
)
from src.llm.processor import ProcessOutcome  # noqa: E402
from src.llm.schemas import (  # noqa: E402
    ExperimentEntities, ExperimentEvent, ExperimentEventType,
    LLMAnalysisResult,
)
from src.llm.unified_router import UnifiedUnderstandingRouter  # noqa: E402
from turn_processors import ChatProcessor, ExperimentProcessor  # noqa: E402


class _StateStore:
    def __init__(self, *, reply_coordinator=None, step_count=0):
        self.reply_coordinator = reply_coordinator or {}
        self.step_count = step_count

    def load_experiment_state(self, conversation_id, lab_session_id):
        return {
            "revision": 0, "reply_coordinator": self.reply_coordinator,
            "session_context": {}, "next_segment_id": self.step_count + 1,
            "experiment_step_count": self.step_count,
        }


class _NeverLLM:
    def __init__(self):
        self.calls = 0

    def understand(self, request):
        self.calls += 1
        raise AssertionError("明确 control 不应调用 LLM")


class _FixedLLM:
    def __init__(self, uncertain=False):
        self.uncertain = uncertain

    def understand(self, request):
        if self.uncertain:
            value = UnifiedUnderstandingResult(
                raw_text=request.raw_text,
                uncertain=UncertainUnderstanding("证据不足"),
            )
        else:
            event = ExperimentEvent(
                ExperimentEventType.MEASUREMENT,
                request.raw_text, request.raw_text,
                entities=ExperimentEntities(temperature="80摄氏度"),
                source_session_id=request.session_id,
                source_segment_id=request.segment_id,
            )
            value = UnifiedUnderstandingResult(
                raw_text=request.raw_text,
                experiment=ExperimentUnderstanding(LLMAnalysisResult(events=[event])),
            )
        return ProcessOutcome(value=value, llm_attempts=1, llm_processing_seconds=.01)


class _QuestionLLM:
    def understand(self, request):
        event = ExperimentEvent(
            ExperimentEventType.MEASUREMENT,
            request.raw_text, request.raw_text,
            entities=ExperimentEntities(action="加热", object="离心管"),
            missing_fields=("temperature", "duration"),
            source_session_id=request.session_id,
            source_segment_id=request.segment_id,
        )
        analysis = LLMAnalysisResult(
            events=[event],
            should_ask_follow_up=True,
            follow_up_question="请问加热的温度和时间是多少？",
        )
        return ProcessOutcome(
            value=UnifiedUnderstandingResult(
                raw_text=request.raw_text,
                experiment=ExperimentUnderstanding(analysis),
            ),
            llm_attempts=1,
            llm_processing_seconds=.01,
        )


def _text(mode, context, text, *, lab=None):
    return TurnInput(
        "c1", f"r-{mode.value}", f"t-{mode.value}", lab,
        mode, context, 1, InputSource.TEXT, text,
    )


class TurnProcessorTests(unittest.TestCase):
    def test_created_clarification_is_a_numbered_card_and_voice_only_reads_question(self):
        processor = ExperimentProcessor(
            _StateStore(),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_QuestionLLM())
            )),
        )
        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT, ExperimentContext.FREE,
                "我把离心管放在酒精灯上加热", lab="lab1",
            ),
            TurnTimingRecorder(),
        )

        card = next(
            block for block in result.turn.blocks
            if block.type.value == "confirmation_card"
        )
        assistant = next(
            block for block in result.turn.blocks
            if block.type.value == "assistant_text"
        )
        self.assertEqual(card.payload["display_number"], 1)
        self.assertEqual(card.payload["title"], "问题 1")
        self.assertEqual(card.payload["question"], "请问加热的温度和时间是多少？")
        self.assertEqual(card.payload["status"], "待回答")
        self.assertEqual(assistant.payload["presentation"], "clarification_card")
        self.assertEqual(
            result.voice_items[0].voice_text,
            "请问加热的温度和时间是多少？",
        )
        self.assertNotIn("已创建", result.voice_items[0].voice_text)
        self.assertEqual(result.voice_items[0].source_block_id, card.block_id)

    def test_chat_prepares_both_messages_without_writing(self):
        seen = {}
        def generate(history, conversation_id, interaction_mode):
            seen["history"] = history
            return "回答"
        processor = ChatProcessor(generate=generate, history=lambda cid: [])
        result = processor.prepare(
            _text(InteractionMode.CHAT, ExperimentContext.NONE, "问题"),
            TurnTimingRecorder(),
        )
        self.assertEqual(seen["history"][-1], {"role": "user", "content": "问题"})
        self.assertEqual([m["role"] for m in result.messages], ["user", "assistant"])
        self.assertEqual(result.turn.blocks[1].payload["text"], "回答")

    def test_explicit_text_control_uses_zero_llm_and_no_business_side_effect(self):
        llm = _NeverLLM()
        observer = lambda: UnifiedObserver(UnifiedAcceptanceBypass(
            UnifiedUnderstandingRouter(llm)
        ))
        processor = ExperimentProcessor(_StateStore(), observer_factory=observer)
        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT, ExperimentContext.FREE,
                "查看待确认问题", lab="lab1",
            ),
            TurnTimingRecorder(),
        )
        self.assertEqual(llm.calls, 0)
        self.assertIsNone(result.lab_record)
        self.assertEqual(result.experiment_events, ())
        self.assertIsNone(result.session_state)
        self.assertIn("没有待确认", result.turn.blocks[1].payload["text"])

    def test_exact_end_command_commits_a_session_ended_turn_without_llm(self):
        llm = _NeverLLM()
        observer = lambda: UnifiedObserver(UnifiedAcceptanceBypass(
            UnifiedUnderstandingRouter(llm)
        ))
        processor = ExperimentProcessor(_StateStore(), observer_factory=observer)
        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT, ExperimentContext.FREE,
                "结束实验记录", lab="lab1",
            ),
            TurnTimingRecorder(),
        )
        self.assertEqual(llm.calls, 0)
        self.assertTrue(result.business["session_ended"])
        self.assertIsNone(result.lab_record)
        self.assertEqual(result.experiment_events, ())
        self.assertIsNone(result.session_state)
        self.assertEqual(
            result.turn.blocks[1].payload["text"],
            "本次实验记录已结束。\n"
            "本次共记录 0 个实验步骤。\n"
            "没有待确认问题。",
        )
        self.assertEqual(
            result.voice_items[0].voice_text,
            "本次实验记录已结束，没有待确认问题。",
        )
        self.assertLessEqual(len(result.voice_items[0].voice_text), 50)

    def test_end_summary_returns_every_unresolved_question_with_stable_status(self):
        snapshot = {
            "clarifications": [
                {
                    "clarification_id": "q1", "display_number": 1,
                    "source_segment_id": 1, "source_raw_text": "加热样品",
                    "question": "请问加热温度是多少？",
                    "missing_fields": ["temperature"],
                    "status": "active", "revision": 1, "reply_pending": False,
                    "requires_confirmation": False,
                    "last_updated_segment_id": None,
                },
                {
                    "clarification_id": "q2", "display_number": 2,
                    "source_segment_id": 2, "source_raw_text": "静置样品",
                    "question": "请问静置时长是多少？",
                    "missing_fields": ["duration"],
                    "status": "deferred", "revision": 2, "reply_pending": False,
                    "requires_confirmation": False,
                    "last_updated_segment_id": 3,
                },
                {
                    "clarification_id": "q3", "display_number": 3,
                    "source_segment_id": 3, "source_raw_text": "温度八十摄氏度",
                    "question": "请确认温度。", "missing_fields": [],
                    "status": "resolved", "revision": 2, "reply_pending": False,
                    "requires_confirmation": False,
                    "last_updated_segment_id": 4,
                },
            ],
            "next_display_number": 4,
            "current_clarification_id": None,
        }
        processor = ExperimentProcessor(
            _StateStore(reply_coordinator=snapshot, step_count=3),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_NeverLLM())
            )),
        )
        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT, ExperimentContext.FREE,
                "结束实验记录", lab="lab1",
            ),
            TurnTimingRecorder(),
        )
        text = result.turn.blocks[1].payload["text"]
        self.assertIn("本次共记录 3 个实验步骤", text)
        self.assertIn("仍有 2 个待确认问题", text)
        self.assertIn("问题 1（待回答）：请问加热温度是多少？", text)
        self.assertIn("问题 2（已暂缓）：请问静置时长是多少？", text)
        self.assertNotIn("请确认温度", text)
        self.assertEqual(
            result.voice_items[0].voice_text,
            "本次实验记录已结束，仍有 2 个待确认问题，请查看屏幕汇总。",
        )
        self.assertLessEqual(len(result.voice_items[0].voice_text), 50)

    def test_experiment_and_uncertain_are_mutually_exclusive(self):
        def processor_for(llm):
            return ExperimentProcessor(
                _StateStore(),
                observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                    UnifiedUnderstandingRouter(llm)
                )),
            )
        turn = _text(
            InteractionMode.EXPERIMENT, ExperimentContext.FREE,
            "温度八十摄氏度", lab="lab1",
        )
        experiment = processor_for(_FixedLLM()).prepare(turn, TurnTimingRecorder())
        self.assertIsNotNone(experiment.lab_record)
        self.assertEqual(len(experiment.experiment_events), 1)
        self.assertIsNotNone(experiment.session_state)

        uncertain = processor_for(_FixedLLM(uncertain=True)).prepare(
            TurnInput(
                "c1", "r-uncertain", "t-uncertain", "lab1",
                InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
                InputSource.TEXT, "也许这样吧",
            ), TurnTimingRecorder(),
        )
        self.assertIsNone(uncertain.lab_record)
        self.assertEqual(uncertain.experiment_events, ())
        self.assertIsNone(uncertain.session_state)
        self.assertIn("无法确定", uncertain.turn.blocks[1].payload["text"])


if __name__ == "__main__":
    unittest.main()
