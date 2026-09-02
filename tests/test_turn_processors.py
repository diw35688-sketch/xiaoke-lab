import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import domain  # noqa: E402
from src.asr.schemas import ASRResult  # noqa: E402
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
    def __init__(
        self, *, reply_coordinator=None, step_count=0,
        protocol_step_facts=None,
    ):
        self.reply_coordinator = reply_coordinator or {}
        self.step_count = step_count
        self.protocol_step_facts = protocol_step_facts or {}

    def load_experiment_state(self, conversation_id, lab_session_id):
        return {
            "revision": 0, "reply_coordinator": self.reply_coordinator,
            "session_context": {}, "next_segment_id": self.step_count + 1,
            "experiment_step_count": self.step_count,
            "protocol_step_facts": self.protocol_step_facts,
        }

    def adopt(self, prepared):
        state = prepared.session_state or {}
        self.reply_coordinator = state.get("reply_coordinator") or {}
        self.protocol_step_facts = state.get("protocol_step_facts") or {}
        if prepared.lab_record is not None:
            self.step_count += 1


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


class _SequenceProtocolLLM:
    def understand(self, request):
        if "透明" in request.raw_text:
            entities = ExperimentEntities(observation="溶液透明")
            # Deliberately opposite to the deterministic protocol result.
            analysis = LLMAnalysisResult(
                events=[ExperimentEvent(
                    ExperimentEventType.OBSERVATION,
                    request.raw_text, request.raw_text,
                    entities=entities,
                    source_session_id=request.session_id,
                    source_segment_id=request.segment_id,
                )],
                should_ask_follow_up=False,
            )
        else:
            entities = ExperimentEntities(condition="室温保存")
            analysis = LLMAnalysisResult(
                events=[ExperimentEvent(
                    ExperimentEventType.OBSERVATION,
                    request.raw_text, request.raw_text,
                    entities=entities,
                    missing_fields=("observation",),
                    source_session_id=request.session_id,
                    source_segment_id=request.segment_id,
                )],
                should_ask_follow_up=True,
                follow_up_question="请重新补充观察现象。",
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
    def test_exact_next_step_moves_protocol_in_same_turn_without_llm(self):
        llm = _NeverLLM()
        processor = ExperimentProcessor(
            _StateStore(),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(llm)
            )),
        )
        selected = SimpleNamespace(
            jump_to=lambda number: SimpleNamespace(step_number=number)
        )

        def step_view(state):
            number = getattr(state, "step_number", 1)
            return {
                "mode": "protocol",
                "protocol": {
                    "id": "p1", "title": "测试方案", "source": "test",
                    "version": "1", "total_steps": 3,
                },
                "step": {
                    "number": number, "title": f"步骤{number}",
                    "instruction": f"执行步骤{number}",
                    "protocol_values": {}, "must_record": [],
                    "hazard_note": None, "terms": [], "substeps": [],
                },
                "safety": [], "safety_note": None,
            }

        with mock.patch("turn_processors.domain.session", return_value=selected), \
             mock.patch("turn_processors.domain.step_view", side_effect=step_view), \
             mock.patch(
                 "turn_processors.domain.evaluate_for_state",
                 return_value={"missing_fields": []},
             ):
            result = processor.prepare(
                TurnInput(
                    "c1", "r-voice-next", "t-voice-next", "lab1",
                    InteractionMode.EXPERIMENT,
                    ExperimentContext.PROTOCOL,
                    1,
                    InputSource.SINGLE_RECORDING,
                    "下一步",
                    ASRResult(
                        asr_transcript="下一步",
                        asr_model_raw_text="下一步",
                        audio_path="fixed://next-step.wav",
                        audio_duration_seconds=0.8,
                        recognition_seconds=0.1,
                        model="fake-asr",
                        language="zh",
                    ),
                ),
                TurnTimingRecorder(),
            )

        self.assertEqual(llm.calls, 0)
        self.assertIsNone(result.lab_record)
        self.assertEqual(
            result.session_state["protocol_step_facts"]["current_step_number"],
            2,
        )
        step_cards = [
            block for block in result.turn.blocks if block.type.value == "step_card"
        ]
        self.assertEqual(step_cards[0].payload["number"], 2)
        self.assertIn("已进入下一步", result.voice_items[0].voice_text)
        self.assertIn("第 2 步：步骤2", result.voice_items[0].voice_text)

    def test_next_step_in_free_mode_does_not_change_state(self):
        llm = _NeverLLM()
        processor = ExperimentProcessor(
            _StateStore(),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(llm)
            )),
        )

        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT,
                ExperimentContext.FREE,
                "下一步",
                lab="lab1",
            ),
            TurnTimingRecorder(),
        )

        self.assertEqual(llm.calls, 0)
        self.assertIsNone(result.session_state)
        self.assertIn("当前没有运行实验方案", result.voice_items[0].voice_text)

    def test_protocol_complete_turn_ignores_llm_create_decision(self):
        step_view = {
            "mode": "protocol",
            "protocol": {
                "id": "p1", "title": "加热", "source": "test",
                "version": "1.0", "total_steps": 1,
            },
            "step": {
                "number": 1, "title": "加热", "instruction": "加热离心管",
                "protocol_values": {},
                "must_record": ["action", "object"],
                "hazard_note": None, "terms": [], "substeps": [],
            },
            "safety": [], "safety_note": "",
        }
        processor = ExperimentProcessor(
            _StateStore(),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_QuestionLLM())
            )),
        )
        with mock.patch("turn_processors.domain.session", return_value=None), \
             mock.patch("turn_processors.domain.step_view", return_value=step_view), \
             mock.patch(
                 "turn_processors.domain.evaluate_for_state",
                 return_value={
                     "missing_fields": [], "follow_up_required": False,
                     "follow_up_question": None, "deviations": [],
                 },
             ):
            result = processor.prepare(
                TurnInput(
                    "c1", "r-protocol-complete", "t-protocol-complete", "lab1",
                    InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL, 1,
                    InputSource.TEXT, "我把离心管加热了",
                ),
                TurnTimingRecorder(),
            )

        self.assertEqual(result.business["clarification_action"], "no_action")
        self.assertNotIn(
            "confirmation_card", [block.type.value for block in result.turn.blocks]
        )
        assistant = next(
            block for block in result.turn.blocks
            if block.type.value == "assistant_text"
        )
        self.assertEqual(assistant.payload["text"], "已记录。")

    def test_free_partial_answer_projects_only_remaining_field(self):
        snapshot = {
            "clarifications": [{
                "clarification_id": "q1", "display_number": 1,
                "source_segment_id": 1, "source_raw_text": "加热样品",
                "question": "请补充温度和时间。",
                "missing_fields": ["temperature", "duration"],
                "status": "active", "revision": 1, "reply_pending": False,
                "requires_confirmation": False,
                "last_updated_segment_id": None,
            }],
            "next_display_number": 2,
            "current_clarification_id": "q1",
        }
        processor = ExperimentProcessor(
            _StateStore(reply_coordinator=snapshot, step_count=1),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_NeverLLM())
            )),
        )
        result = processor.prepare(
            TurnInput(
                "c1", "r-free-answer", "t-free-answer", "lab1",
                InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
                InputSource.TEXT, "问题1，温度是80摄氏度",
            ),
            TurnTimingRecorder(),
        )

        self.assertIn("还需要补充：时间", result.turn.blocks[-2].payload["text"])
        card = next(
            block for block in result.turn.blocks
            if block.type.value == "confirmation_card"
        )
        self.assertEqual(card.payload["missing_fields"], ("duration",))
        self.assertEqual(card.payload["question"], "还需要补充：时间。")
        self.assertEqual(card.payload["original_question"], "请补充温度和时间。")

    def test_free_uncertain_chinese_temperature_answers_unique_current_question(self):
        snapshot = {
            "clarifications": [{
                "clarification_id": "q1", "display_number": 1,
                "source_segment_id": 1, "source_raw_text": "加热溶液十分钟",
                "question": "加热溶液的温度是多少？",
                "missing_fields": ["temperature"],
                "status": "active", "revision": 1, "reply_pending": False,
                "requires_confirmation": False,
                "last_updated_segment_id": None,
            }],
            "next_display_number": 2,
            "current_clarification_id": "q1",
        }
        processor = ExperimentProcessor(
            _StateStore(reply_coordinator=snapshot, step_count=1),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_FixedLLM(uncertain=True))
            )),
        )
        result = processor.prepare(
            TurnInput(
                "c1", "r-free-natural-answer", "t-free-natural-answer", "lab1",
                InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
                InputSource.TEXT, "六十摄氏度",
            ),
            TurnTimingRecorder(),
        )

        self.assertEqual(result.business["clarification_action"], "answer")
        self.assertIn("已补充完整", result.turn.blocks[-2].payload["text"])
        clarification = result.session_state["reply_coordinator"]["clarifications"][0]
        self.assertEqual(clarification["status"], "resolved")

    def test_protocol_natural_turns_accumulate_and_resolve_one_question(self):
        step_view = {
            "mode": "protocol",
            "protocol": {
                "id": "p1", "title": "保存样品", "source": "test",
                "version": "1.0", "total_steps": 1,
            },
            "step": {
                "number": 1, "title": "观察并保存",
                "instruction": "记录观察现象和保存条件",
                "protocol_values": {},
                "must_record": ["observation", "condition"],
                "hazard_note": None, "terms": [], "substeps": [],
            },
            "safety": [], "safety_note": "",
        }
        store = _StateStore()
        processor = ExperimentProcessor(
            store,
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_SequenceProtocolLLM())
            )),
        )

        def evaluate(_state, values):
            missing = [
                name for name in ("observation", "condition")
                if name not in values
            ]
            return {
                "missing_fields": missing,
                "follow_up_required": bool(missing),
                "follow_up_question": (
                    "请补充保存条件。" if missing else None
                ),
                "deviations": [],
            }

        patches = (
            mock.patch("turn_processors.domain.session", return_value=None),
            mock.patch("turn_processors.domain.step_view", return_value=step_view),
            mock.patch(
                "turn_processors.domain.evaluate_for_state", side_effect=evaluate
            ),
        )
        with patches[0], patches[1], patches[2]:
            first = processor.prepare(
                TurnInput(
                    "c1", "r-protocol-1", "t-protocol-1", "lab1",
                    InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL, 1,
                    InputSource.TEXT, "倒转混匀，溶液透明",
                ),
                TurnTimingRecorder(),
            )
            store.adopt(first)
            second = processor.prepare(
                TurnInput(
                    "c1", "r-protocol-2", "t-protocol-2", "lab1",
                    InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL, 1,
                    InputSource.TEXT, "室温保存",
                ),
                TurnTimingRecorder(),
            )

        self.assertEqual(
            first.lab_record["evaluation"]["missing_fields"], ["condition"]
        )
        self.assertEqual(first.business["clarification_action"], "create")
        self.assertEqual(second.lab_record["evaluation"]["missing_fields"], [])
        self.assertEqual(second.business["clarification_action"], "answer")
        self.assertIn("已补充完整", second.turn.blocks[-2].payload["text"])
        saved = second.session_state["protocol_step_facts"]
        step_one = saved["steps"]["1"]
        self.assertEqual(
            step_one["values"]["observation"]["value"], "溶液透明"
        )
        self.assertEqual(
            step_one["values"]["condition"]["value"], "室温保存"
        )
        active = second.session_state["reply_coordinator"]["clarifications"]
        self.assertEqual(active[0]["status"], "resolved")
        self.assertEqual(active[0]["protocol_step_number"], 1)

    def test_protocol_uncertain_natural_short_answer_resolves_unique_question(self):
        step_view = {
            "mode": "protocol",
            "protocol": {
                "id": "p1", "title": "显色反应", "source": "test",
                "version": "1.0", "total_steps": 1,
            },
            "step": {
                "number": 1, "title": "观察终点",
                "instruction": "记录终点颜色", "protocol_values": {},
                "must_record": ["observation"], "hazard_note": None,
                "terms": [], "substeps": [],
            },
            "safety": [], "safety_note": "",
        }
        question = {
            "clarification_id": "q1", "display_number": 1,
            "source_segment_id": 1, "source_raw_text": "反应到达终点",
            "question": "终点时溶液颜色是什么？",
            "missing_fields": ["observation"], "status": "active",
            "revision": 1, "reply_pending": False,
            "requires_confirmation": False, "last_updated_segment_id": None,
            "protocol_id": "p1", "protocol_version": "1.0",
            "protocol_step_number": 1,
        }
        store = _StateStore(
            reply_coordinator={
                "clarifications": [question], "next_display_number": 2,
                "current_clarification_id": "q1",
            },
            step_count=1,
            protocol_step_facts={
                "protocol_id": "p1", "protocol_version": "1.0",
                "current_step_number": 1,
                "steps": {"1": {
                    "protocol_id": "p1", "protocol_version": "1.0",
                    "step_number": 1, "values": {}, "clarification_id": "q1",
                }},
                "statuses": {"1": "in_progress"},
            },
        )
        processor = ExperimentProcessor(
            store,
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_FixedLLM(uncertain=True))
            )),
        )
        with mock.patch("turn_processors.domain.session", return_value=None), \
             mock.patch("turn_processors.domain.step_view", return_value=step_view), \
             mock.patch(
                 "turn_processors.domain.evaluate_for_state",
                 side_effect=lambda _state, values: {
                     "missing_fields": ([] if values.get("observation") else ["observation"]),
                     "follow_up_required": not bool(values.get("observation")),
                     "follow_up_question": None,
                     "deviations": [],
                 },
             ):
            result = processor.prepare(
                TurnInput(
                    "c1", "r-short-answer", "t-short-answer", "lab1",
                    InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL, 1,
                    InputSource.TEXT, "粉红色",
                ),
                TurnTimingRecorder(),
            )

        self.assertEqual(result.business["clarification_action"], "answer")
        self.assertIn("已补充完整", result.turn.blocks[-2].payload["text"])
        step = result.session_state["protocol_step_facts"]["steps"]["1"]
        self.assertEqual(step["values"]["observation"]["value"], "粉红色")
        clarification = result.session_state["reply_coordinator"]["clarifications"][0]
        self.assertEqual(clarification["status"], "resolved")

    def test_protocol_answer_from_step_two_updates_debt_on_step_one(self):
        protocol = domain.protocols().list_all()[0]
        selected = domain.start_session(protocol.protocol_id)
        first_step = {
            "protocol_id": protocol.protocol_id,
            "protocol_version": protocol.version,
            "step_number": 1,
            "values": {},
            "clarification_id": "q1",
        }
        execution_snapshot = {
            "protocol_id": protocol.protocol_id,
            "protocol_version": protocol.version,
            "current_step_number": 2,
            "steps": {
                "1": first_step,
                "2": {
                    "protocol_id": protocol.protocol_id,
                    "protocol_version": protocol.version,
                    "step_number": 2,
                    "values": {},
                    "clarification_id": None,
                },
            },
            "statuses": {"1": "left_with_pending", "2": "in_progress"},
        }
        question_snapshot = {
            "clarifications": [{
                "clarification_id": "q1", "display_number": 1,
                "source_segment_id": 1, "source_raw_text": "称量磷酸盐",
                "question": "实际称量值是多少？",
                "missing_fields": ["amount_value"],
                "status": "active", "revision": 3,
                "reply_pending": False, "requires_confirmation": False,
                "last_updated_segment_id": 2,
                "protocol_id": protocol.protocol_id,
                "protocol_version": protocol.version,
                "protocol_step_number": 1,
            }],
            "next_display_number": 2,
            "current_clarification_id": "q1",
        }
        processor = ExperimentProcessor(
            _StateStore(
                reply_coordinator=question_snapshot,
                step_count=1,
                protocol_step_facts=execution_snapshot,
            ),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_NeverLLM())
            )),
        )

        result = processor.prepare(
            TurnInput(
                "c1", "r-old-step-answer", "t-old-step-answer", "lab1",
                InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL, 1,
                InputSource.TEXT, "问题一，3.58克",
            ),
            TurnTimingRecorder(),
        )

        saved = result.session_state["protocol_step_facts"]
        self.assertEqual(saved["current_step_number"], 2)
        written_value = saved["steps"]["1"]["values"]["amount_value"]
        self.assertTrue(written_value["value"])
        self.assertEqual(written_value["request_id"], "r-old-step-answer")
        self.assertEqual(saved["statuses"]["1"], "completed")
        clarification = result.session_state["reply_coordinator"][
            "clarifications"
        ][0]
        self.assertEqual(clarification["status"], "resolved")

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

    def test_exact_reactivate_command_restores_deferred_question_without_llm(self):
        snapshot = {
            "clarifications": [{
                "clarification_id": "q1", "display_number": 1,
                "source_segment_id": 1, "source_raw_text": "保存样品",
                "question": "请补充温度和时长。",
                "missing_fields": ["temperature", "duration"],
                "status": "deferred", "revision": 2,
                "reply_pending": False, "requires_confirmation": False,
                "last_updated_segment_id": 2,
            }],
            "next_display_number": 2,
            "current_clarification_id": None,
        }
        llm = _NeverLLM()
        processor = ExperimentProcessor(
            _StateStore(reply_coordinator=snapshot, step_count=1),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(llm)
            )),
        )

        result = processor.prepare(
            _text(
                InteractionMode.EXPERIMENT,
                ExperimentContext.FREE,
                "继续问题1",
                lab="lab1",
            ),
            TurnTimingRecorder(),
        )

        self.assertEqual(llm.calls, 0)
        self.assertEqual(result.business["clarification_action"], "reactivate")
        self.assertTrue(result.business["execution"]["state_changed"])
        self.assertIn("已恢复问题 1", result.turn.blocks[1].payload["text"])
        saved = result.session_state["reply_coordinator"]
        self.assertEqual(saved["current_clarification_id"], "q1")
        self.assertEqual(saved["clarifications"][0]["status"], "active")
        self.assertEqual(saved["next_display_number"], 2)

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

    def test_protocol_turn_carries_protocol_step_and_safety_blocks(self):
        step_view = {
            "mode": "protocol",
            "protocol": {
                "id": "p1", "title": "磷酸缓冲液配制", "source": "教学示例",
                "version": "1.0", "total_steps": 5,
            },
            "step": {
                "number": 1, "title": "称量磷酸盐",
                "instruction": "称取方案规定质量的磷酸盐",
                "protocol_values": {"action": "称量", "amount_value": "3.58"},
                "must_record": ["amount_value"],
                "hazard_note": None,
                "terms": [],
                "substeps": [{"order": 1, "text": "打开分析天平", "note": None}],
            },
            "safety": [{
                "name": "磷酸盐", "cas": "CAS-1", "critical": True,
                "codes": [], "statements": ["避免吸入"], "source_url": "",
            }],
            "safety_note": "注意实验安全",
        }
        processor = ExperimentProcessor(
            _StateStore(),
            observer_factory=lambda: UnifiedObserver(UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(_FixedLLM())
            )),
        )
        with mock.patch("turn_processors.domain.session", return_value=None), \
             mock.patch("turn_processors.domain.step_view", return_value=step_view), \
             mock.patch(
                 "turn_processors.domain.evaluate_for_state",
                 return_value={
                     "missing_fields": ["amount_value"],
                     "follow_up_required": True,
                     "follow_up_question": "实际称量值是多少？",
                     "deviations": [],
                 },
             ):
            result = processor.prepare(
                _text(
                    InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL,
                    "称了 3.6 克磷酸盐", lab="lab1",
                ),
                TurnTimingRecorder(),
            )

        types = [block.type.value for block in result.turn.blocks]
        self.assertIn("protocol_card", types)
        self.assertIn("step_card", types)
        self.assertIn("safety_alert", types)

        protocol_card = next(
            block for block in result.turn.blocks
            if block.type.value == "protocol_card"
        )
        self.assertEqual(protocol_card.payload["title"], "磷酸缓冲液配制")
        self.assertEqual(protocol_card.payload["summary"], "共 5 步")

        step_card = next(
            block for block in result.turn.blocks
            if block.type.value == "step_card"
        )
        self.assertEqual(step_card.payload["number"], 1)
        self.assertEqual(step_card.payload["instruction"], "称取方案规定质量的磷酸盐")
        self.assertEqual(step_card.payload["lines"], ("打开分析天平",))

        safety = next(
            block for block in result.turn.blocks
            if block.type.value == "safety_alert"
        )
        self.assertEqual(safety.payload["critical"], True)
        self.assertEqual(safety.payload["note"], "注意实验安全")


if __name__ == "__main__":
    unittest.main()
