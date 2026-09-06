# 社区模板标准

社区只接受两种可导入、可执行的正式模板：

- `reagent_prep`：试剂/缓冲液配制
- `protocol`：实验方案

所有发布内容必须通过项目现有数据合同校验；无效模板不能进入社区库。

---

## 1. 试剂配制 `reagent_prep`

```json
{
  "kind": "reagent_prep",
  "title": "0.1 mol/L PBS 缓冲液",
  "tags": "缓冲液,PBS,常用",
  "content": {
    "reagent_prep_id": "pbs-0.1m",
    "name_zh": "0.1 mol/L PBS 缓冲液",
    "purpose": "用于细胞洗涤与缓冲",
    "target_concentration": "0.1 mol/L",
    "target_volume": "1 L",
    "solvent": "超纯水",
    "steps": [
      "称取 8.0 g NaCl、0.2 g KCl、1.44 g Na2HPO4、0.24 g KH2PO4",
      "加超纯水溶解并定容至 1 L",
      "用 HCl/NaOH 调节 pH 至 7.4",
      "0.22 μm 过滤除菌"
    ],
    "storage_condition": "4℃ 保存",
    "expiry": "1 个月",
    "hazard_reagents": ["NaOH"],
    "source": "实验室内部",
    "source_url": "",
    "review_status": "REVIEWED"
  }
}
```

### 必填字段

| 字段 | 说明 |
|---|---|
| `reagent_prep_id` | 唯一 ID，不能为空 |
| `name_zh` | 中文名称 |
| `purpose` | 用途 |
| `steps` | 非空字符串数组，每步必须非空 |
| `source` | 来源 |
| `review_status` | `UNREVIEWED` 或 `REVIEWED` |

### 可空字段

`target_concentration`、`target_volume`、`solvent`、`storage_condition`、`expiry`、`source_url`

### 约束

- `steps` 不能为空
- `hazard_reagents` 可为空数组，但不能重复
- `review_status` 只能二选一

---

## 2. 实验方案 `protocol`

```json
{
  "kind": "protocol",
  "title": "氢氧化钠滴定盐酸",
  "tags": "滴定,酸碱",
  "content": {
    "protocol_id": "naoh-hcl-titration",
    "title": "氢氧化钠滴定盐酸",
    "source": "实验室内部",
    "version": "1.0",
    "schema_version": 1,
    "steps": [
      {
        "step_number": 1,
        "title": "润洗碱式滴定管",
        "instruction": "取少量氢氧化钠标准溶液润洗管内壁，重复两到三次",
        "protocol_values": {},
        "must_record": ["wash_count"],
        "terms": ["滴定管", "润洗"],
        "hazard_note": "佩戴护目镜和手套",
        "field_prompts": {
          "wash_count": "实际润洗了几次？"
        },
        "value_aliases": {},
        "substeps": [
          {"order": 1, "text": "润洗滴定管 2~3 次", "note": "倒掉废液"}
        ]
      }
    ]
  }
}
```

### 必填字段

| 字段 | 说明 |
|---|---|
| `protocol_id` | 唯一 ID |
| `title` | 方案标题 |
| `source` | 来源 |
| `version` | 版本 |
| `schema_version` | 必须等于当前 `PROTOCOL_SCHEMA_VERSION`（1） |
| `steps` | 非空数组 |

### 每一步必填字段

| 字段 | 说明 |
|---|---|
| `step_number` | 从 1 开始严格连续 |
| `title` | 步骤标题 |
| `instruction` | 步骤原文 |
| `protocol_values` | 方案固定目标值；字段必须来自实体字段集合 |
| `must_record` | 现场必测字段；字段必须来自实体字段集合，且不能重复 |
| `terms` | 识别术语数组 |
| `hazard_note` | 可为空字符串；非空不能是纯空白 |

### 可空字段

- `field_prompts`
- `value_aliases`
- `substeps`

### 约束

- `step_number` 必须从 1 开始严格连续
- `protocol_values` 中的键必须是合法实体字段
- `must_record` 中的键必须是合法实体字段，且不能重复
- `field_prompts` 的键必须同时出现在 `must_record`
- `value_aliases` 的键必须出现在本步骤的 `protocol_values`
- `substeps` 的 `order` 必须从 1 开始连续

---

## 3. 发布/导入校验位置

发布与导入都走同一套校验：

```text
ReagentPrep.from_dict  → 试剂配制
ProtocolStore._parse_protocol  → 实验方案
```

校验失败的模板返回：

```text
400 模板不满足标准：...
```

不会写入社区库。
