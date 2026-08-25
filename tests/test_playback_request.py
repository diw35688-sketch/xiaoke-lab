import unittest
from datetime import datetime, timedelta, timezone

from src.core.playback_request import PlaybackRequest
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.presentation_intent import MessageKind, MessagePriority


CREATED_AT = datetime(2026, 8, 23, 9, 30, tzinfo=timezone.utc)


def _request(**overrides):
    values = {
        "intent_id": "ask-7",
        "kind": MessageKind.CLARIFICATION,
        "priority": MessagePriority.ACTIVE_QUESTION,
        "voice_text": "离心时间是多少？",
        "created_at": CREATED_AT,
        "ttl": timedelta(seconds=20),
        "supersession_key": "clarification:current",
    }
    values.update(overrides)
    return PlaybackRequest(**values)


class PlaybackRequestContractTests(unittest.TestCase):
    def test_valid_request_is_immutable_and_has_expiry_boundary(self):
        request = _request()

        self.assertEqual(request.expires_at, CREATED_AT + timedelta(seconds=20))
        with self.assertRaises(AttributeError):
            request.voice_text = "changed"

    def test_delivery_item_factory_is_the_lifecycle_metadata_entry_point(self):
        item = VoiceDeliveryItem(
            "safety-1",
            MessageKind.SAFETY_ALERT,
            MessagePriority.CRITICAL,
            "立即停止加热。",
        )

        request = PlaybackRequest.from_delivery_item(
            item,
            created_at=CREATED_AT,
            ttl=timedelta(seconds=5),
        )

        self.assertEqual(request.source_block_id, item.source_block_id)
        self.assertEqual(request.max_chars, item.max_chars)

        self.assertEqual(request.intent_id, item.intent_id)
        self.assertEqual(request.priority, MessagePriority.CRITICAL)
        self.assertIsNone(request.supersession_key)

    def test_required_lifecycle_field_cannot_be_omitted(self):
        with self.assertRaises(TypeError):
            PlaybackRequest(
                intent_id="ask-7",
                kind=MessageKind.CLARIFICATION,
                priority=MessagePriority.ACTIVE_QUESTION,
                voice_text="离心时间是多少？",
                created_at=CREATED_AT,
            )

    def test_created_at_must_be_timezone_aware(self):
        with self.assertRaisesRegex(ValueError, "时区"):
            _request(created_at=datetime(2026, 8, 23, 9, 30))

    def test_ttl_must_be_positive(self):
        for invalid in (timedelta(0), timedelta(seconds=-1)):
            with self.subTest(ttl=invalid):
                with self.assertRaisesRegex(ValueError, "大于 0"):
                    _request(ttl=invalid)

    def test_priority_must_be_message_priority_not_raw_integer(self):
        with self.assertRaisesRegex(TypeError, "MessagePriority"):
            _request(priority=20)

    def test_supersession_key_cannot_be_blank(self):
        with self.assertRaisesRegex(ValueError, "supersession_key"):
            _request(supersession_key="  ")


if __name__ == "__main__":
    unittest.main()
