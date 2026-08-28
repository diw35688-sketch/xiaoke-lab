import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.storage.protocol_store import (
    ProtocolStore,
    ProtocolStoreError,
)


def valid_step(**changes) -> dict:
    values = {
        "step_number": 1,
        "title": "加热溶液",
        "instruction": "将溶液加热到60摄氏度并保持10分钟。",
        "protocol_values": {"temperature": "60摄氏度"},
        "must_record": ["temperature", "duration"],
        "field_prompts": {
            "temperature": "实际温度是多少？",
            "duration": "保持了多久？",
        },
        "terms": ["恒温水浴"],
        "hazard_note": None,
    }
    values.update(changes)
    return values


def valid_protocol(**changes) -> dict:
    values = {
        "protocol_id": "heating-demo",
        "title": "加热示例",
        "source": "本科实验教学示例",
        "version": "1.0",
        "steps": [valid_step()],
        "schema_version": 1,
    }
    values.update(changes)
    return values


def valid_library() -> dict:
    return {"protocols": [valid_protocol()]}


class ProtocolStoreTests(unittest.TestCase):
    def write_library(
        self,
        directory: str,
        data: object,
    ) -> Path:
        path = Path(directory) / "protocols.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_loads_protocols_in_file_order(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            second = valid_protocol(
                protocol_id="cooling-demo",
                title="冷却示例",
            )
            data["protocols"].append(second)
            path = self.write_library(directory, data)

            store = ProtocolStore(path)

            self.assertEqual(
                tuple(
                    protocol.protocol_id
                    for protocol in store.list_all()
                ),
                ("heating-demo", "cooling-demo"),
            )

    def test_get_by_id_returns_matching_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, valid_library())
            store = ProtocolStore(path)

            protocol = store.get_by_id("heating-demo")

        self.assertEqual(protocol.title, "加热示例")

    def test_loads_validated_step_local_value_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0]["value_aliases"] = {
                "temperature": ["60℃"]
            }
            protocol = ProtocolStore(self.write_library(directory, data)).get(
                "heating-demo"
            )

            self.assertEqual(
                protocol.steps[0].value_aliases["temperature"], ("60℃",)
            )

    def test_rejects_alias_for_field_without_protocol_value(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0]["value_aliases"] = {
                "object": ["样品"]
            }

            with self.assertRaisesRegex(ProtocolStoreError, "必须对应.*protocol_values"):
                ProtocolStore(self.write_library(directory, data))

    def test_rejects_aliases_that_are_not_a_json_array(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0]["value_aliases"] = {
                "temperature": "60℃"
            }

            with self.assertRaisesRegex(ProtocolStoreError, "必须是JSON数组"):
                ProtocolStore(self.write_library(directory, data))

    def test_get_alias_returns_matching_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, valid_library())
            store = ProtocolStore(path)

            protocol = store.get("heating-demo")

            self.assertEqual(protocol.protocol_id, "heating-demo")

    def test_missing_id_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, valid_library())
            store = ProtocolStore(path)

            protocol = store.get_by_id("unknown")

            self.assertIsNone(protocol)

    def test_rejects_blank_lookup_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, valid_library())
            store = ProtocolStore(path)

            with self.assertRaises(ProtocolStoreError):
                store.get_by_id(" ")

    def test_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "文件不存在",
            ):
                ProtocolStore(path)

    def test_rejects_directory_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ProtocolStoreError,
                "不是文件",
            ):
                ProtocolStore(directory)

    def test_rejects_damaged_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocols.json"
            path.write_text("{不是JSON", encoding="utf-8")

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "不是合法JSON",
            ):
                ProtocolStore(path)

    def test_rejects_non_object_top_level(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, [])

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "顶层必须是JSON对象",
            ):
                ProtocolStore(path)

    def test_rejects_unknown_top_level_field(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["comment"] = "不允许的字段"
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "额外=.*comment",
            ):
                ProtocolStore(path)

    def test_rejects_missing_top_level_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(directory, {})

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "缺少=.*protocols",
            ):
                ProtocolStore(path)

    def test_rejects_protocols_with_wrong_type(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(
                directory,
                {"protocols": {}},
            )

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "必须是JSON数组",
            ):
                ProtocolStore(path)

    def test_rejects_empty_protocol_library(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_library(
                directory,
                {"protocols": []},
            )

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "不能为空",
            ):
                ProtocolStore(path)

    def test_rejects_missing_protocol_field(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            del data["protocols"][0]["source"]
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "缺少=.*source",
            ):
                ProtocolStore(path)

    def test_rejects_unknown_protocol_field(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["owner"] = "实验中心"
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "额外=.*owner",
            ):
                ProtocolStore(path)

    def test_rejects_missing_step_field(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            del data["protocols"][0]["steps"][0]["terms"]
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "缺少=.*terms",
            ):
                ProtocolStore(path)

    def test_legacy_fixture_without_field_prompts_remains_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0].pop("field_prompts", None)
            path = self.write_library(directory, data)

            step = ProtocolStore(path).list_all()[0].steps[0]

        self.assertEqual(step.field_prompts, {})

    def test_rejects_unknown_step_field(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0]["note"] = "额外"
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "额外=.*note",
            ):
                ProtocolStore(path)

    def test_rejects_schema_version_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["schema_version"] = 2
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "schema_version不受支持",
            ):
                ProtocolStore(path)

    def test_rejects_duplicate_protocol_id(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"].append(
                copy.deepcopy(data["protocols"][0])
            )
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "protocol_id.*重复",
            ):
                ProtocolStore(path)

    def test_wraps_invalid_protocol_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["title"] = " "
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "方案标题",
            ):
                ProtocolStore(path)

    def test_wraps_invalid_step_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            data = valid_library()
            data["protocols"][0]["steps"][0]["must_record"] = [
                "temperature",
                "temperature",
            ]
            path = self.write_library(directory, data)

            with self.assertRaisesRegex(
                ProtocolStoreError,
                "不能重复",
            ):
                ProtocolStore(path)

    def test_loads_repository_seed_data(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "protocols"
            / "undergraduate_basic_protocols.json"
        )

        store = ProtocolStore(path)

        self.assertGreaterEqual(len(store.list_all()), 3)


if __name__ == "__main__":
    unittest.main()
