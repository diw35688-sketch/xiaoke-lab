import json
import unittest
from dataclasses import FrozenInstanceError

from src.core.conversation_turn import (
    BlockType,
    ConversationBlock,
    ConversationTurn,
    ExperimentContext,
    InputSource,
    InteractionMode,
    TurnReplayDisposition,
    TurnReplayReason,
    decide_turn_replay,
)
from src.core.presentation_intent import MessagePriority


def _block(block_id="user-1", type=BlockType.USER_TEXT, payload=None, **kwargs):
    return ConversationBlock(
        block_id=block_id,
        type=type,
        payload={"text": "请记录加入 5 毫升缓冲液"} if payload is None else payload,
        **kwargs,
    )


def _turn(*blocks, **overrides):
    values = {
        "conversation_id": "conversation-7",
        "request_id": "request-21",
        "turn_id": "turn-12",
        "interaction_mode": InteractionMode.EXPERIMENT,
        "experiment_context": ExperimentContext.FREE,
        "mode_version": 4,
        "input_source": InputSource.SINGLE_RECORDING,
        "blocks": blocks or (_block(),),
    }
    values.update(overrides)
    return ConversationTurn(**values)


class ConversationTurnContractTests(unittest.TestCase):
    def test_one_turn_carries_trace_identity_mode_context_and_input_snapshot(self):
        turn = _turn()

        wire = turn.to_wire()

        self.assertEqual(wire["conversation_id"], "conversation-7")
        self.assertEqual(wire["request_id"], "request-21")
        self.assertEqual(wire["turn_id"], "turn-12")
        self.assertEqual(wire["interaction_mode"], "experiment")
        self.assertEqual(wire["experiment_context"], "free")
        self.assertEqual(wire["mode_version"], 4)
        self.assertEqual(wire["input_source"], "single_recording")

    def test_all_required_screen_content_kinds_are_representable(self):
        kinds = (
            BlockType.USER_TEXT,
            BlockType.ASSISTANT_TEXT,
            BlockType.PROTOCOL_CARD,
            BlockType.STEP_CARD,
            BlockType.SAFETY_ALERT,
            BlockType.RECORD_CARD,
            BlockType.TOOL_CARD,
            BlockType.CONFIRMATION_CARD,
            BlockType.SYSTEM_STATUS,
        )

        turn = _turn(*(
            _block(f"block-{index}", kind, {"text": kind.value})
            for index, kind in enumerate(kinds, start=1)
        ))

        self.assertEqual({block.type for block in turn.blocks}, set(kinds))

    def test_voice_identity_points_to_visible_block_without_copying_text(self):
        answer = _block("answer-1", BlockType.ASSISTANT_TEXT, {"text": "当然可以。"})
        voice = _block(
            "voice-1",
            BlockType.VOICE,
            {},
            source_block_id="answer-1",
            intent_id="reply-1",
            priority=MessagePriority.DIRECT_ACK,
        )

        turn = _turn(answer, voice)

        self.assertEqual(turn.to_wire()["blocks"][1], {
            "block_id": "voice-1",
            "type": "voice",
            "payload": {},
            "source_block_id": "answer-1",
            "intent_id": "reply-1",
            "priority": MessagePriority.DIRECT_ACK.value,
        })

    def test_voice_cannot_reference_another_turn_or_voice_block(self):
        dangling = _block(
            "voice-1", BlockType.VOICE, {}, source_block_id="missing",
            intent_id="reply-1", priority=MessagePriority.DIRECT_ACK,
        )
        with self.assertRaisesRegex(ValueError, "本 turn"):
            _turn(dangling)

        first_voice = _block(
            "voice-1", BlockType.VOICE, {}, source_block_id="answer-1",
            intent_id="reply-1", priority=MessagePriority.DIRECT_ACK,
        )
        chained_voice = _block(
            "voice-2", BlockType.VOICE, {}, source_block_id="voice-1",
            intent_id="reply-2", priority=MessagePriority.DIRECT_ACK,
        )
        with self.assertRaisesRegex(ValueError, "非语音"):
            _turn(_block("answer-1", BlockType.ASSISTANT_TEXT), first_voice, chained_voice)

    def test_voice_fields_are_required_only_for_voice_blocks(self):
        with self.assertRaisesRegex(ValueError, "intent_id"):
            _block(
                "voice-1", BlockType.VOICE, {}, source_block_id="answer-1",
                priority=MessagePriority.DIRECT_ACK,
            )
        with self.assertRaisesRegex(ValueError, "只有 VOICE"):
            _block("answer-1", BlockType.ASSISTANT_TEXT, intent_id="reply-1")

    def test_mode_and_experiment_context_are_consistent(self):
        _turn(
            interaction_mode=InteractionMode.CHAT,
            experiment_context=ExperimentContext.NONE,
            input_source=InputSource.TEXT,
        )
        with self.assertRaisesRegex(ValueError, "chat 模式"):
            _turn(
                interaction_mode=InteractionMode.CHAT,
                experiment_context=ExperimentContext.FREE,
            )
        with self.assertRaisesRegex(ValueError, "free.*protocol"):
            _turn(experiment_context=ExperimentContext.NONE)

    def test_ids_are_non_blank_and_unique_inside_turn(self):
        with self.assertRaisesRegex(ValueError, "conversation_id"):
            _turn(conversation_id=" ")
        with self.assertRaisesRegex(ValueError, "block_id 必须唯一"):
            _turn(_block("same"), _block("same", BlockType.SYSTEM_STATUS))
        answer = _block("answer-1", BlockType.ASSISTANT_TEXT)
        voice_1 = _block(
            "voice-1", BlockType.VOICE, {}, source_block_id="answer-1",
            intent_id="same-intent", priority=MessagePriority.DIRECT_ACK,
        )
        voice_2 = _block(
            "voice-2", BlockType.VOICE, {}, source_block_id="answer-1",
            intent_id="same-intent", priority=MessagePriority.DIRECT_ACK,
        )
        with self.assertRaisesRegex(ValueError, "intent_id 必须唯一"):
            _turn(answer, voice_1, voice_2)

    def test_contract_and_nested_payload_are_immutable_but_wire_is_json_safe(self):
        supplied = {"tool": {"name": "calculate"}, "items": [1, 2]}
        block = _block("tool-1", BlockType.TOOL_CARD, supplied)
        turn = _turn(block)
        supplied["tool"]["name"] = "changed"
        supplied["items"].append(3)

        self.assertEqual(block.payload["tool"]["name"], "calculate")
        self.assertEqual(block.payload["items"], (1, 2))
        with self.assertRaises(TypeError):
            block.payload["tool"]["name"] = "changed"
        with self.assertRaises(FrozenInstanceError):
            turn.turn_id = "changed"
        self.assertEqual(json.loads(json.dumps(turn.to_wire())), turn.to_wire())

    def test_contract_construction_has_no_business_side_effect_methods(self):
        turn = _turn()

        for forbidden in ("save", "execute_tool", "schedule", "play", "speak"):
            self.assertFalse(hasattr(turn, forbidden))

    def test_mode_version_is_a_required_positive_integer_snapshot(self):
        for invalid in (0, -1):
            with self.subTest(mode_version=invalid):
                with self.assertRaisesRegex(ValueError, "正整数"):
                    _turn(mode_version=invalid)
        for invalid in (True, "4"):
            with self.subTest(mode_version=invalid):
                with self.assertRaisesRegex(TypeError, "正整数"):
                    _turn(mode_version=invalid)

    def test_same_request_and_exact_contract_is_an_idempotent_replay(self):
        existing = _turn()
        candidate = _turn()

        result = decide_turn_replay(existing, candidate)

        self.assertEqual(result.disposition, TurnReplayDisposition.IDEMPOTENT_REPLAY)
        self.assertEqual(result.reason, TurnReplayReason.EXACT_MATCH)

    def test_same_request_with_changed_mode_version_is_a_conflict(self):
        existing = _turn(mode_version=4)
        candidate = _turn(mode_version=5)

        result = decide_turn_replay(existing, candidate)

        self.assertEqual(result.disposition, TurnReplayDisposition.CONFLICT)
        self.assertEqual(result.reason, TurnReplayReason.MODE_VERSION_CHANGED)

    def test_same_request_with_changed_content_is_not_treated_as_retry(self):
        existing = _turn()
        candidate = _turn(_block(payload={"text": "另一条输入"}))

        result = decide_turn_replay(existing, candidate)

        self.assertEqual(result.disposition, TurnReplayDisposition.CONFLICT)
        self.assertEqual(result.reason, TurnReplayReason.REQUEST_CONTENT_CHANGED)

    def test_different_conversation_request_key_is_new_work(self):
        existing = _turn()
        candidate = _turn(request_id="request-22")

        result = decide_turn_replay(existing, candidate)

        self.assertEqual(result.disposition, TurnReplayDisposition.NEW_REQUEST)
        self.assertEqual(result.reason, TurnReplayReason.DIFFERENT_REQUEST)


if __name__ == "__main__":
    unittest.main()
