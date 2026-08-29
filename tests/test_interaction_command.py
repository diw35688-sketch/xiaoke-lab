import unittest

from src.core.interaction_command import (
    InteractionCommand,
    InteractionCommandParser,
    InteractionCommandType,
)


class InteractionCommandParserTests(unittest.TestCase):
    def test_parses_only_standalone_next_protocol_step_commands(self):
        for text in ("下一步", "进入下一步。", "继续下一步😊"):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NEXT_PROTOCOL_STEP,
                )

        for text in (
            "等示数稳定后再进行下一步",
            "下一步需要加多少水",
            "不要进入下一步",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(command.command_type, InteractionCommandType.NORMAL)

    def test_parses_supported_end_session_commands(self):
        for text in (
            "结束实验记录",
            "结束 实验记录。",
            "退出实验记录！",
            "接受实验记录",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.END_SESSION,
                )

    def test_does_not_end_session_for_longer_operation_text(self):
        for text in (
            "结束离心",
            "结束实验记录后生成报告",
            "加热结束后冷却至室温",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NORMAL,
                )

    def test_parses_defer_current_commands(self):
        for text in (
            "这个先跳过",
            "这个问题先跳过。",
            "稍后再问",
            "暂时无法回答",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.DEFER_CURRENT,
                )
                self.assertTrue(
                    command.requires_clarification_context
                )

    def test_parses_defer_targeted_commands(self):
        cases = (
            ("问题二先跳过", 2),
            ("问题2先跳过", 2),
            ("第二个问题先跳过", 2),
            ("问题一先暂缓", 1),
        )
        for text, number in cases:
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.DEFER_TARGETED,
                )
                self.assertEqual(
                    command.target_question_number,
                    number,
                )

    def test_parses_reactivate_targeted_commands(self):
        cases = (
            ("继续问题二", 2),
            ("继续回答问题2", 2),
            ("恢复第二个问题", 2),
            ("恢复回答问题一", 1),
        )
        for text, number in cases:
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.REACTIVATE_TARGETED,
                )
                self.assertEqual(command.target_question_number, number)

    def test_does_not_reactivate_without_question_number(self):
        for text in ("继续问题", "恢复问题", "继续实验"):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NORMAL,
                )

    def test_ignores_sensevoice_trailing_emotion_for_command(self):
        cases = (
            (
                "这个先跳过。😔",
                InteractionCommandType.DEFER_CURRENT,
            ),
            (
                "查看待确认问题。😊",
                InteractionCommandType.REVIEW_PENDING,
            ),
        )

        for text, expected_type in cases:
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(command.command_type, expected_type)
                self.assertEqual(command.raw_text, text)

    def test_does_not_ignore_sensevoice_event_prefix(self):
        command = InteractionCommandParser.parse(
            "👏查看待确认问题。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.NORMAL,
        )

    def test_does_not_guess_ambiguous_asr_skip_variants(self):
        for text in (
            "短线跳过。",
            "歌先跳过。",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NORMAL,
                )

    def test_does_not_treat_experiment_step_as_defer_command(self):
        for text in (
            "跳过过滤步骤继续加热",
            "暂时无法观察到沉淀",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NORMAL,
                )

    def test_parses_natural_defer_expressions(self):
        for text in (
            "我先跳过。",
            "可先跳过。",
            "能先跳过吗。",
            "这个先跳过去。",
            "先问下一个。",
            "这个问题先放着。",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.DEFER_CURRENT,
                    f"{text!r} 应命中 DEFER_CURRENT",
                )

    def test_natural_defer_safe_starts_still_reject_experiment(self):
        # 不以安全前缀开头的"跳过"仍是 NORMAL
        for text in (
            "跳过过滤步骤继续加热",
            "暂时无法观察到沉淀",
            "短线跳过。",
            "歌先跳过。",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.NORMAL,
                    f"{text!r} 不能误判为 DEFER",
                )

    def test_parses_review_pending_command(self):
        command = InteractionCommandParser.parse(
            "查看待确认问题。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.REVIEW_PENDING,
        )

    def test_parses_natural_review_expressions(self):
        for text in (
            "还有哪些问题没有回答？",
            "还有什么没回答的。",
            "有没有还没回答的问题？",
            "看看还缺什么。",
            "我想看一下还有什么少了。",
        ):
            with self.subTest(text=text):
                command = InteractionCommandParser.parse(text)
                self.assertEqual(
                    command.command_type,
                    InteractionCommandType.REVIEW_PENDING,
                    f"{text!r} 应命中 REVIEW_PENDING",
                )

    def test_parses_affirmative_candidate(self):
        command = InteractionCommandParser.parse(
            "是的，是移液枪。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.AFFIRM,
        )
        self.assertEqual(command.answer_text, "是的是移液枪")
        self.assertTrue(command.requires_clarification_context)

    def test_normal_operation_starting_with_dui_is_not_affirm(self):
        command = InteractionCommandParser.parse(
            "对溶液继续加热。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.NORMAL,
        )

    def test_parses_denial_with_correction(self):
        command = InteractionCommandParser.parse(
            "不对，应该是滴定管。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.DENY,
        )
        self.assertEqual(
            command.answer_text,
            "不对应该是滴定管",
        )

    def test_parses_targeted_answer_by_arabic_number(self):
        command = InteractionCommandParser.parse(
            "问题2，离心5分钟。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.TARGETED_ANSWER,
        )
        self.assertEqual(command.target_question_number, 2)
        self.assertEqual(command.answer_text, "离心5分钟")

    def test_parses_targeted_answer_by_chinese_number(self):
        command = InteractionCommandParser.parse(
            "第二个问题，是移液枪。"
        )
        self.assertEqual(
            command.command_type,
            InteractionCommandType.TARGETED_ANSWER,
        )
        self.assertEqual(command.target_question_number, 2)
        self.assertEqual(command.answer_text, "是移液枪")

    def test_target_can_be_selected_without_answer(self):
        command = InteractionCommandParser.parse("回答问题3")
        self.assertEqual(
            command.command_type,
            InteractionCommandType.TARGETED_ANSWER,
        )
        self.assertEqual(command.target_question_number, 3)
        self.assertIsNone(command.answer_text)

    def test_preserves_raw_text(self):
        raw_text = "  问题 2，离心 5 分钟。 "
        command = InteractionCommandParser.parse(raw_text)
        self.assertEqual(command.raw_text, raw_text)
        self.assertEqual(
            command.normalized_text,
            "问题2离心5分钟",
        )

    def test_empty_text_is_normal_input(self):
        command = InteractionCommandParser.parse("  。 ")
        self.assertEqual(
            command.command_type,
            InteractionCommandType.NORMAL,
        )
        self.assertFalse(command.is_control_candidate)


class InteractionCommandValidationTests(unittest.TestCase):
    def test_targeted_answer_requires_positive_number(self):
        with self.assertRaises(ValueError):
            InteractionCommand(
                command_type=(
                    InteractionCommandType.TARGETED_ANSWER
                ),
                raw_text="问题0",
                normalized_text="问题0",
                target_question_number=0,
            )

    def test_other_commands_cannot_contain_target_number(self):
        with self.assertRaises(ValueError):
            InteractionCommand(
                command_type=InteractionCommandType.AFFIRM,
                raw_text="是的",
                normalized_text="是的",
                target_question_number=1,
            )


if __name__ == "__main__":
    unittest.main()
