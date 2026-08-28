import threading
import unittest

from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.experiment_turn_input import ExperimentTurnInput
from src.llm.schemas import (
    ExperimentEvent,
    ExperimentEventType,
    LLMAnalysisResult,
)
from web.experiment_runtime_sessions import (
    ExperimentRuntimeSessionRegistry,
    ExperimentSessionBackpressureError,
    ExperimentSubmissionConflictError,
)


def _request(**overrides):
    values = {
        "conversation_id": "conversation-a",
        "request_id": "request-1",
        "turn_id": "turn-1",
        "interaction_mode": InteractionMode.EXPERIMENT,
        "experiment_context": ExperimentContext.FREE,
        "mode_version": 1,
        "input_source": InputSource.TEXT,
        "raw_text": "加入缓冲液。",
    }
    values.update(overrides)
    return ExperimentTurnInput(**values)


class ExperimentRuntimeSessionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ExperimentRuntimeSessionRegistry(max_pending_tasks=4)
        self.addCleanup(self.registry.clear)

    def test_same_pair_owns_one_runtime_but_other_pairs_do_not_share_it(self):
        first = self.registry.session("conversation-a", "lab-1")
        again = self.registry.session("conversation-a", "lab-1")
        other_conversation = self.registry.session("conversation-b", "lab-1")
        other_lab_session = self.registry.session("conversation-a", "lab-2")

        self.assertIs(first, again)
        self.assertIsNot(first, other_conversation)
        self.assertIsNot(first, other_lab_session)

    def test_registry_creation_is_thread_safe_for_the_same_pair(self):
        runtimes = []
        append_lock = threading.Lock()

        def get_runtime():
            runtime = self.registry.session("conversation-a", "lab-1")
            with append_lock:
                runtimes.append(runtime)

        threads = [threading.Thread(target=get_runtime) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        self.assertEqual(len(runtimes), 12)
        self.assertEqual(len({id(runtime) for runtime in runtimes}), 1)

    def test_clarification_and_context_state_do_not_cross_session_keys(self):
        runtime_a = self.registry.session("conversation-a", "lab-1")
        runtime_b = self.registry.session("conversation-b", "lab-1")

        def add_state(coordinator, context):
            coordinator.register_clarification(
                segment_id=1,
                raw_text="加入缓冲液。",
                question="加入了多少？",
                missing_fields=("amount_value",),
            )
            context.add_analysis(LLMAnalysisResult(
                events=[ExperimentEvent(
                    event_type=ExperimentEventType.OPERATION,
                    raw_text="加入缓冲液。",
                    normalized_text="加入缓冲液。",
                )],
                should_ask_follow_up=False,
                follow_up_question=None,
                assistant_reply=None,
            ))

        runtime_a.submit(_request(), add_state).future.result(timeout=1)

        self.assertEqual(len(runtime_a.active_clarifications()), 1)
        self.assertEqual(runtime_b.active_clarifications(), ())
        self.assertEqual(runtime_a.context_snapshot(), ("[operation] 加入缓冲液。",))
        self.assertEqual(runtime_b.context_snapshot(), ())

    def test_exact_request_retry_reuses_sequence_future_and_side_effect(self):
        runtime = self.registry.session("conversation-a", "lab-1")
        calls = []
        request = _request()

        first = runtime.submit(request, lambda coordinator, context: calls.append("run"))
        replay = runtime.submit(request, lambda coordinator, context: calls.append("duplicate"))

        first.future.result(timeout=1)
        self.assertEqual(first.sequence, 1)
        self.assertFalse(first.replayed)
        self.assertEqual(replay.sequence, 1)
        self.assertTrue(replay.replayed)
        self.assertIs(replay.future, first.future)
        self.assertEqual(calls, ["run"])

    def test_same_request_id_with_changed_content_is_rejected(self):
        runtime = self.registry.session("conversation-a", "lab-1")
        first = _request()
        changed = _request(raw_text="改成另一条事实。")
        runtime.submit(first, lambda coordinator, context: None)

        with self.assertRaisesRegex(
            ExperimentSubmissionConflictError, "请求内容冲突"
        ):
            runtime.submit(changed, lambda coordinator, context: None)

    def test_request_must_belong_to_the_named_conversation(self):
        runtime = self.registry.session("conversation-a", "lab-1")

        with self.assertRaisesRegex(ValueError, "conversation_id 不一致"):
            runtime.submit(
                _request(conversation_id="conversation-b"),
                lambda coordinator, context: None,
            )

    def test_one_session_executes_work_in_submission_order(self):
        runtime = self.registry.session("conversation-a", "lab-1")
        first_started = threading.Event()
        release_first = threading.Event()
        order = []

        def first(coordinator, context):
            order.append("first-start")
            first_started.set()
            self.assertTrue(release_first.wait(timeout=1))
            order.append("first-end")

        def second(coordinator, context):
            order.append("second")

        first_submission = runtime.submit(_request(), first)
        self.assertTrue(first_started.wait(timeout=1))
        second_submission = runtime.submit(
            _request(request_id="request-2", turn_id="turn-2"), second
        )
        self.assertEqual(order, ["first-start"])

        release_first.set()
        first_submission.future.result(timeout=1)
        second_submission.future.result(timeout=1)
        self.assertEqual(order, ["first-start", "first-end", "second"])
        self.assertEqual(second_submission.sequence, 2)

    def test_different_sessions_can_process_concurrently(self):
        runtime_a = self.registry.session("conversation-a", "lab-1")
        runtime_b = self.registry.session("conversation-b", "lab-1")
        barrier = threading.Barrier(2)

        def work(coordinator, context):
            barrier.wait(timeout=1)
            return "done"

        submission_a = runtime_a.submit(_request(), work)
        submission_b = runtime_b.submit(
            _request(
                conversation_id="conversation-b",
                request_id="request-b",
                turn_id="turn-b",
            ),
            work,
        )

        self.assertEqual(submission_a.future.result(timeout=2), "done")
        self.assertEqual(submission_b.future.result(timeout=2), "done")

    def test_backpressure_rejects_new_work_but_allows_idempotent_retry(self):
        registry = ExperimentRuntimeSessionRegistry(max_pending_tasks=1)
        self.addCleanup(registry.clear)
        runtime = registry.session("conversation-a", "lab-1")
        started = threading.Event()
        release = threading.Event()
        request = _request()

        def blocking(coordinator, context):
            started.set()
            self.assertTrue(release.wait(timeout=1))

        first = runtime.submit(request, blocking)
        self.assertTrue(started.wait(timeout=1))
        replay = runtime.submit(request, lambda coordinator, context: None)
        self.assertIs(replay.future, first.future)
        with self.assertRaises(ExperimentSessionBackpressureError):
            runtime.submit(
                _request(request_id="request-2", turn_id="turn-2"),
                lambda coordinator, context: None,
            )

        release.set()
        first.future.result(timeout=1)

    def test_close_removes_runtime_and_closed_instance_rejects_work(self):
        runtime = self.registry.session("conversation-a", "lab-1")

        self.assertTrue(self.registry.close("conversation-a", "lab-1"))
        with self.assertRaisesRegex(RuntimeError, "已经关闭"):
            runtime.submit(_request(), lambda coordinator, context: None)
        replacement = self.registry.session("conversation-a", "lab-1")
        self.assertIsNot(replacement, runtime)

    def test_invalid_registry_identity_is_rejected(self):
        for conversation_id, lab_session_id in (("", "lab-1"), ("c", " ")):
            with self.subTest(
                conversation_id=conversation_id,
                lab_session_id=lab_session_id,
            ):
                with self.assertRaises(ValueError):
                    self.registry.session(conversation_id, lab_session_id)

    def test_operation_must_be_callable(self):
        runtime = self.registry.session("conversation-a", "lab-1")

        with self.assertRaisesRegex(TypeError, "可调用"):
            runtime.submit(_request(), "not-callable")

    def test_pending_count_tracks_only_incomplete_work(self):
        runtime = self.registry.session("conversation-a", "lab-1")
        started = threading.Event()
        release = threading.Event()

        def blocking(coordinator, context):
            started.set()
            self.assertTrue(release.wait(timeout=1))

        self.assertEqual(runtime.pending_count(), 0)
        submission = runtime.submit(_request(), blocking)
        self.assertTrue(started.wait(timeout=1))
        self.assertEqual(runtime.pending_count(), 1)
        release.set()
        submission.future.result(timeout=1)
        self.assertEqual(runtime.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
