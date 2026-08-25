import unittest

from src.core.conversation_turn import (
    BlockType,
    ConversationTurn,
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.presentation_intent import MessagePriority
from src.core.spoken_output import (
    CHAT_DEFAULT_MAX_CHARS,
    EXPERIMENT_TURN_MAX_CHARS,
    ReplyScope,
    build_spoken_block_plan,
    select_spoken_output_policy,
)


class SpokenOutputContractTests(unittest.TestCase):
    def test_chat_default_is_estimated_ten_seconds_and_continuation_is_unbounded(self):
        default = select_spoken_output_policy(
            InteractionMode.CHAT, ExperimentContext.NONE
        )
        continuation = select_spoken_output_policy(
            InteractionMode.CHAT,
            ExperimentContext.NONE,
            reply_scope=ReplyScope.CONTINUATION,
        )

        self.assertEqual(default.estimated_max_chars, CHAT_DEFAULT_MAX_CHARS)
        self.assertEqual(CHAT_DEFAULT_MAX_CHARS, 50)
        self.assertIsNone(continuation.estimated_max_chars)

    def test_free_and_protocol_share_one_estimated_fifteen_second_turn_budget(self):
        for context in (ExperimentContext.FREE, ExperimentContext.PROTOCOL):
            with self.subTest(context=context):
                policy = select_spoken_output_policy(
                    InteractionMode.EXPERIMENT, context
                )
                self.assertEqual(policy.estimated_max_chars, 75)
                self.assertEqual(policy.max_voice_blocks, 1)
        self.assertEqual(EXPERIMENT_TURN_MAX_CHARS, 75)

    def test_visible_text_is_the_only_voice_text_source_and_is_exact(self):
        policy = select_spoken_output_policy(
            InteractionMode.EXPERIMENT, ExperimentContext.FREE
        )
        plan = build_spoken_block_plan(
            turn_id="turn-9",
            text="请补充缓冲液的浓度。",
            intent_id="experiment-summary-9",
            priority=MessagePriority.ACTIVE_QUESTION,
            policy=policy,
        )

        self.assertEqual(plan.source_block.type, BlockType.ASSISTANT_TEXT)
        self.assertEqual(plan.source_block.payload["role"], "spoken")
        self.assertEqual(plan.voice_text, plan.source_block.payload["text"])
        self.assertEqual(plan.voice_block.payload, {})
        self.assertEqual(
            plan.voice_block.source_block_id, plan.source_block.block_id
        )

    def test_plan_forms_one_valid_turn_with_exactly_one_voice_block(self):
        policy = select_spoken_output_policy(
            InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL
        )
        plan = build_spoken_block_plan(
            turn_id="turn-10",
            text="实际用量与方案不同，请确认加入量。",
            intent_id="protocol-summary-10",
            priority=MessagePriority.ACTIVE_QUESTION,
            policy=policy,
        )

        turn = ConversationTurn(
            conversation_id="conversation-1",
            request_id="request-10",
            turn_id="turn-10",
            interaction_mode=InteractionMode.EXPERIMENT,
            experiment_context=ExperimentContext.PROTOCOL,
            mode_version=2,
            input_source=InputSource.CONTINUOUS_CALL,
            blocks=plan.blocks,
        )

        self.assertEqual(
            sum(block.type == BlockType.VOICE for block in turn.blocks), 1
        )

    def test_over_budget_text_is_rejected_without_truncating_visible_text(self):
        policy = select_spoken_output_policy(
            InteractionMode.CHAT, ExperimentContext.NONE
        )
        original = "甲" * (CHAT_DEFAULT_MAX_CHARS + 1)

        with self.assertRaisesRegex(ValueError, "禁止截断"):
            build_spoken_block_plan(
                turn_id="turn-11",
                text=original,
                intent_id="chat-11",
                priority=MessagePriority.REVIEW,
                policy=policy,
            )
        self.assertEqual(len(original), CHAT_DEFAULT_MAX_CHARS + 1)

    def test_invalid_mode_context_pairs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "chat 模式"):
            select_spoken_output_policy(
                InteractionMode.CHAT, ExperimentContext.FREE
            )
        with self.assertRaisesRegex(ValueError, "free 或 protocol"):
            select_spoken_output_policy(
                InteractionMode.EXPERIMENT, ExperimentContext.NONE
            )


if __name__ == "__main__":
    unittest.main()
