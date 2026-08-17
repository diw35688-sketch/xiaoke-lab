import threading
import time
import unittest

from src.core.presentation_coordinator import PresentationCoordinator
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.presentation_pump import (
    PresentationDeliveryError,
    PresentationPump,
)


def _record_ack(intent_id="r", step_number=1):
    return PresentationIntent(
        intent_id=intent_id,
        kind=MessageKind.RECORD_ACK,
        args={"result": "recorded", "step_number": step_number},
        priority=MessagePriority.ROUTINE,
        screen_target=ScreenTarget.STATUS,
    )


def _wait_until(condition, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class FakeRenderer:
    def __init__(self):
        self.rendered = []

    def render(self, intent):
        self.rendered.append(intent)
        return f"rendered:{intent.kind.value}"


class FakeOutput:
    def __init__(self):
        self.outputs = []

    def __call__(self, text):
        self.outputs.append(text)


class PresentationPumpTests(unittest.TestCase):
    def test_pump_calls_event_tone_player_for_delivered_intent(self):
        coordinator = PresentationCoordinator()
        renderer = FakeRenderer()
        output = FakeOutput()
        tones = []
        pump = PresentationPump(
            coordinator,
            renderer,
            output,
            event_tone_player=tones.append,
        )

        pump.start()
        try:
            coordinator.submit([_record_ack("r1", 1)])
            self.assertTrue(
                _wait_until(lambda: len(tones) >= 1),
                "pump 未在超时内触发事件提示音",
            )
        finally:
            pump.stop(timeout=1)

        self.assertEqual(len(tones), 1)
        self.assertEqual(tones[0].kind, MessageKind.RECORD_ACK)

    def test_pump_renders_and_outputs_submitted_intents(self):
        coordinator = PresentationCoordinator()
        renderer = FakeRenderer()
        output = FakeOutput()
        pump = PresentationPump(coordinator, renderer, output)

        pump.start()
        try:
            coordinator.submit([_record_ack("r1", 1)])
            self.assertTrue(
                _wait_until(lambda: len(output.outputs) >= 1),
                "pump 未在超时内渲染并输出消息",
            )
        finally:
            pump.stop(timeout=1)

        self.assertEqual(len(renderer.rendered), 1)
        self.assertEqual(output.outputs, ["rendered:record_ack"])

    def test_pump_outputs_in_fifo_order(self):
        coordinator = PresentationCoordinator()
        renderer = FakeRenderer()
        output = FakeOutput()
        pump = PresentationPump(coordinator, renderer, output)

        pump.start()
        try:
            coordinator.submit(
                [_record_ack("r1", 1), _record_ack("r2", 2)]
            )
            self.assertTrue(
                _wait_until(lambda: len(output.outputs) >= 2),
                "pump 未在超时内输出两条消息",
            )
        finally:
            pump.stop(timeout=1)

        self.assertEqual(output.outputs, ["rendered:record_ack"] * 2)
        self.assertEqual(len(renderer.rendered), 2)

    def test_stop_stops_the_thread(self):
        coordinator = PresentationCoordinator()
        pump = PresentationPump(coordinator, FakeRenderer(), FakeOutput())

        pump.start()
        pump.stop(timeout=1)

        self.assertFalse(pump._thread.is_alive())

    def test_flush_waits_for_output_after_coordinator_is_empty(self):
        coordinator = PresentationCoordinator()
        output_started = threading.Event()
        release_output = threading.Event()

        def slow_output(text):
            output_started.set()
            release_output.wait(timeout=2)

        pump = PresentationPump(coordinator, FakeRenderer(), slow_output)
        pump.start()
        try:
            coordinator.submit([_record_ack("slow", 1)])
            self.assertTrue(output_started.wait(timeout=1))
            self.assertEqual(coordinator.pending_count, 0)

            self.assertFalse(
                pump.flush(timeout=0.05),
                "output 仍阻塞时 flush 不应误报完成",
            )

            release_output.set()
            self.assertTrue(pump.flush(timeout=1))
        finally:
            release_output.set()
            pump.stop(timeout=1)

    def test_flush_reports_delivery_failure_and_pump_continues(self):
        coordinator = PresentationCoordinator()
        outputs = []

        class FailFirstRenderer:
            def __init__(self):
                self.calls = 0

            def render(self, intent):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("broken render")
                return f"ok:{intent.intent_id}"

        pump = PresentationPump(coordinator, FailFirstRenderer(), outputs.append)
        pump.start()
        try:
            coordinator.submit([
                _record_ack("bad", 1),
                _record_ack("good", 2),
            ])
            with self.assertRaises(PresentationDeliveryError) as raised:
                pump.flush(timeout=1)
        finally:
            pump.stop(timeout=1)

        self.assertEqual(outputs, ["ok:good"])
        self.assertEqual(len(raised.exception.failures), 1)
        failure = raised.exception.failures[0]
        self.assertEqual(failure.intent_id, "bad")
        self.assertEqual(failure.error_type, "ValueError")


if __name__ == "__main__":
    unittest.main()
