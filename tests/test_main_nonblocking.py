"""非阻塞录音的集成测试（Fake 连线，不碰真实麦克风/LLM/文件）。

用一个会阻塞的 Fake 观察器模拟"慢 LLM"，证明：当第 1 段口述的
后台处理还没完成时，主线程已经在继续录第 2、3 段——即录音不等待 LLM。

这条测试是 RESTORE-NONBLOCK-01 的核心行为证据。
"""

import threading
import unittest
from unittest.mock import patch

from src.asr.schemas import ASRResult
from src.core.state_manager import StateManager
from src.core.unified_observer import (
    UnifiedObservation,
    UnifiedObservationStatus,
)
from src.main import run_experiment_session


def _failed_observation(segment_id: int) -> UnifiedObservation:
    return UnifiedObservation(
        request_id=f"unified-it-{segment_id}",
        session_id="it",
        segment_id=segment_id,
        status=UnifiedObservationStatus.FAILED,
        error_type="ValueError",
    )


class BlockingFakeObserver:
    """第一次 observe 阻塞（模拟慢 LLM），之后立即返回。"""

    def __init__(self, observation):
        self._observation = observation
        self._blocking = False
        self._first = True
        self.observe_started = threading.Event()
        self.release = threading.Event()

    def observe(self, **kwargs):
        if self._first:
            self._first = False
            self._blocking = True
            self.observe_started.set()
            self.release.wait(timeout=10)
            self._blocking = False
        return self._observation

    def is_blocking(self) -> bool:
        return self._blocking


class FakeRecorder:
    """按顺序返回路径；从第 2 次录音起，记录"录音时 LLM 是否还在阻塞"。"""

    def __init__(self, paths, observer):
        self._paths = list(paths)
        self._observer = observer
        self.record_calls = 0
        self.blocked_during_record = False
        self.recorded_all = threading.Event()

    def record_until_silence(self):
        self.record_calls += 1
        if self.record_calls >= 2:
            self._observer.observe_started.wait(timeout=5)
            if self._observer.is_blocking():
                self.blocked_during_record = True
        path = self._paths.pop(0)
        if not self._paths:
            self.recorded_all.set()
        return path


class FakeRecognizer:
    def __init__(self, mapping):
        self._mapping = mapping

    def recognize(self, audio_path):
        return self._mapping[audio_path]


class FakeExecutor:
    """不应被调用（FAILED 观察没有 pending_action）。"""

    def __init__(self):
        self.calls = 0

    def execute(self, action):
        self.calls += 1
        raise AssertionError("集成测试不应执行任何动作")


class FakeAsrStore:
    def __init__(self):
        self.appended = []

    def append(self, *, result, session_id, segment_id):
        self.appended.append((result, session_id, segment_id))


class FakeEventStore:
    def append_analysis(self, outcome):
        pass


class FakeConfirmationStore:
    def append(self, record):
        pass


class NonBlockingIntegrationTest(unittest.TestCase):
    def _run_short_session(self, ui_mode):
        asr_1 = ASRResult(
            asr_transcript="加入缓冲液",
            asr_model_raw_text="加入缓冲液",
        )
        asr_end = ASRResult(
            asr_transcript="结束实验记录",
            asr_model_raw_text="结束实验记录",
        )
        observer = BlockingFakeObserver(_failed_observation(1))
        recorder = FakeRecorder(["p1", "p2"], observer)
        recognizer = FakeRecognizer({
            "p1": asr_1,
            "p2": asr_end,
        })

        with patch("builtins.print") as output, patch(
            "src.main.UI_MODE", ui_mode
        ), patch("src.main._attach_session_debug_log"):
            run_experiment_session(
                recorder=recorder,
                recognizer=recognizer,
                asr_store=FakeAsrStore(),
                event_store=FakeEventStore(),
                confirmation_store=FakeConfirmationStore(),
                state_manager=StateManager(),
                observer=observer,
                executor=FakeExecutor(),
            )

        return "\n".join(
            call.args[0] for call in output.call_args_list
        )

    def test_transcript_respects_ui_mode(self):
        user_rendered = self._run_short_session("user")
        self.assertNotIn("本段 ASR 识别完成", user_rendered)

        admin_rendered = self._run_short_session("admin")
        self.assertIn("本段 ASR 识别完成：加入缓冲液", admin_rendered)

    def test_recording_continues_while_llm_processes(self):
        # Arrange：3 段口述，第 3 段是结束命令
        asr_1 = ASRResult(
            asr_transcript="加入缓冲液",
            asr_model_raw_text="加入缓冲液",
        )
        asr_2 = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        asr_end = ASRResult(
            asr_transcript="结束实验记录",
            asr_model_raw_text="结束实验记录",
        )

        observer = BlockingFakeObserver(_failed_observation(1))
        recorder = FakeRecorder(["p1", "p2", "p3"], observer)
        recognizer = FakeRecognizer({
            "p1": asr_1,
            "p2": asr_2,
            "p3": asr_end,
        })
        asr_store = FakeAsrStore()

        session_done = threading.Event()

        def run():
            run_experiment_session(
                recorder=recorder,
                recognizer=recognizer,
                asr_store=asr_store,
                event_store=FakeEventStore(),
                confirmation_store=FakeConfirmationStore(),
                state_manager=StateManager(),
                observer=observer,
                executor=FakeExecutor(),
            )
            session_done.set()

        # Act：在后台线程运行会话
        with patch("builtins.print") as output:
            thread = threading.Thread(target=run)
            thread.start()

            # Assert 1：三段都录完（此时第 1 段 LLM 仍在阻塞）
            self.assertTrue(
                recorder.recorded_all.wait(timeout=5),
                "三段口述未在预期时间内录完",
            )
            # Assert 2：录音期间 LLM 确实还在阻塞 → 非阻塞成立
            self.assertTrue(
                recorder.blocked_during_record,
                "录音等待了 LLM（阻塞回归）",
            )

            # 放行第 1 段的 LLM，让后台排空、会话正常结束
            observer.release.set()
            thread.join(timeout=5)

            rendered = "\n".join(
                call.args[0] for call in output.call_args_list
            )

        # Assert 3：会话结束；两段非结束口述都提交并落盘 ASR
        self.assertTrue(session_done.is_set(), "会话未正常结束")
        self.assertEqual(recorder.record_calls, 3)
        self.assertEqual(len(asr_store.appended), 2)

        # Assert 4：会话级引导只出现一次，循环不再重复宣布继续监听。
        self.assertEqual(rendered.count("实验记录会话已开始"), 1)
        self.assertEqual(rendered.count("请开始口述实验过程"), 1)
        self.assertNotIn("系统将立即继续监听", rendered)

        # 去重复不能吞掉逐段业务结果和结束反馈。
        self.assertIn("本段结构化处理失败，原始记录已保存", rendered)
        self.assertEqual(rendered.count("实验记录会话已结束"), 1)
        self.assertIn("本次共记录 0 个实验步骤", rendered)
        self.assertEqual(rendered.count("没有待确认问题"), 1)
        self.assertNotIn("提交 0 段实验口述", rendered)


if __name__ == "__main__":
    unittest.main()
