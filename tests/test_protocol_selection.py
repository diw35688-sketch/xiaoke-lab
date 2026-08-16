import unittest
from dataclasses import FrozenInstanceError

from src.core.protocol import ExperimentProtocol, ProtocolStep
from src.core.protocol_selection import (
    ProtocolSelection,
    ProtocolSelectionError,
    ProtocolSelectionMode,
    select_protocol,
)


def make_protocol(
    protocol_id: str = "first-protocol",
) -> ExperimentProtocol:
    step = ProtocolStep(
        step_number=1,
        title="记录观察",
        instruction="记录实验现象。",
        protocol_values={},
        must_record=("observation",),
        terms=(),
        hazard_note=None,
    )
    return ExperimentProtocol(
        protocol_id=protocol_id,
        title=f"方案{protocol_id}",
        source="本科实验教学示例",
        version="1.0",
        steps=(step,),
        schema_version=1,
    )


class FakeProtocolCatalog:
    def __init__(self, protocols):
        self._protocols = tuple(protocols)

    def list_all(self):
        return self._protocols

    def get_by_id(self, protocol_id):
        for protocol in self._protocols:
            if protocol.protocol_id == protocol_id:
                return protocol
        return None


class ProtocolSelectionTests(unittest.TestCase):
    def setUp(self):
        self.first = make_protocol("first-protocol")
        self.second = make_protocol("second-protocol")
        self.catalog = FakeProtocolCatalog((self.first, self.second))

    def test_none_selects_free_recording_mode(self):
        result = select_protocol(self.catalog, None)

        self.assertEqual(result.mode, ProtocolSelectionMode.FREE)
        self.assertTrue(result.is_free_mode)
        self.assertFalse(result.has_protocol)
        self.assertIsNone(result.protocol)

    def test_selects_protocol_by_one_based_number(self):
        result = select_protocol(self.catalog, 2)

        self.assertIs(result.protocol, self.second)

    def test_selects_protocol_by_protocol_id(self):
        result = select_protocol(
            self.catalog,
            "first-protocol",
        )

        self.assertIs(result.protocol, self.first)

    def test_selected_result_reports_protocol_mode(self):
        result = ProtocolSelection.selected(self.first)

        self.assertEqual(result.mode, ProtocolSelectionMode.SELECTED)
        self.assertTrue(result.has_protocol)
        self.assertFalse(result.is_free_mode)

    def test_rejects_zero_sequence_number(self):
        with self.assertRaisesRegex(
            ProtocolSelectionError,
            "从1开始",
        ):
            select_protocol(self.catalog, 0)

    def test_rejects_out_of_range_sequence_number(self):
        with self.assertRaisesRegex(
            ProtocolSelectionError,
            "超出范围",
        ):
            select_protocol(self.catalog, 3)

    def test_rejects_boolean_sequence_number(self):
        with self.assertRaisesRegex(
            ProtocolSelectionError,
            "布尔值",
        ):
            select_protocol(self.catalog, True)

    def test_rejects_blank_protocol_id(self):
        with self.assertRaisesRegex(
            ProtocolSelectionError,
            "不能为空",
        ):
            select_protocol(self.catalog, " ")

    def test_rejects_unknown_protocol_id(self):
        with self.assertRaisesRegex(
            ProtocolSelectionError,
            "未找到",
        ):
            select_protocol(self.catalog, "unknown")

    def test_rejects_unsupported_selection_type(self):
        with self.assertRaises(ProtocolSelectionError):
            select_protocol(self.catalog, 1.5)

    def test_rejects_selected_result_without_protocol(self):
        with self.assertRaises(ProtocolSelectionError):
            ProtocolSelection(
                mode=ProtocolSelectionMode.SELECTED,
                protocol=None,
            )

    def test_rejects_free_result_with_protocol(self):
        with self.assertRaises(ProtocolSelectionError):
            ProtocolSelection(
                mode=ProtocolSelectionMode.FREE,
                protocol=self.first,
            )

    def test_selection_result_is_frozen(self):
        result = ProtocolSelection.free_mode()

        with self.assertRaises(FrozenInstanceError):
            result.protocol = self.first


if __name__ == "__main__":
    unittest.main()
