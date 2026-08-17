# -*- coding: utf-8 -*-
"""批量扩充实验方案库、试剂配置库和危化品库。

所有新增数据均为 UNREVIEWED，使用前必须经教师复核。
来源说明：
- Protocol：本科实验教学通用方案整理；如已有 protocols.io 公开来源则显式注明。
- 试剂配置：本科实验教学通用配方整理。
- 危化品：GHS 分类采用 GB 30000 系列中文表述；来源 PubChem，具体 CID 待核。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.protocol import ProtocolStep
from src.core.reagent_prep import ReagentPrep
from src.storage.hazmat_store import HazmatStore
from src.storage.protocol_store import ProtocolStore
from src.storage.reagent_prep_store import ReagentPrepStore

PROTOCOL_FILE = ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"
REAGENT_PREP_FILE = ROOT / "data" / "reagent_prep" / "reagent_prep_library.json"
HAZMAT_FILE = ROOT / "data" / "hazmat" / "reagent_safety.json"

H_CODE_TEXT = {
    "H225": "高度易燃液体和蒸气",
    "H271": "可能引起火灾或爆炸；强氧化性",
    "H272": "可能加剧燃烧；氧化性",
    "H290": "可能腐蚀金属",
    "H301": "吞咽有毒",
    "H302": "吞咽有害",
    "H311": "皮肤接触有毒",
    "H312": "皮肤接触有害",
    "H314": "造成严重皮肤灼伤和眼损伤",
    "H315": "造成皮肤刺激",
    "H317": "可能引起皮肤过敏反应",
    "H318": "造成严重眼损伤",
    "H319": "造成严重眼刺激",
    "H330": "吸入致命",
    "H331": "吸入有毒",
    "H332": "吸入有害",
    "H334": "吸入可能引起过敏或哮喘症状或呼吸困难",
    "H335": "可能引起呼吸道刺激",
    "H336": "可能引起昏昏欲睡或眩晕",
    "H340": "可能引起遗传缺陷",
    "H341": "怀疑可能引起遗传缺陷",
    "H350": "可能致癌",
    "H351": "怀疑可能致癌",
    "H361": "怀疑可能对生育能力或胎儿造成伤害",
    "H370": "对器官造成损害",
    "H372": "长期或反复接触对器官造成损害",
    "H373": "长期或反复接触可能对器官造成损害",
    "H400": "对水生生物毒性极大",
    "H410": "对水生生物毒性极大并具有长期持续影响",
}

# 新增试剂配置：20 条
NEW_REAGENT_PREPS = [
    dict(reagent_prep_id="tae-1x", name_zh="1× TAE 电泳缓冲液", purpose="琼脂糖凝胶电泳工作液", target_concentration="1×", target_volume="1 L", solvent="去离子水",
         steps=["量取 20 mL 50× TAE 母液", "加去离子水定容至 1 L", "混匀后使用"], storage_condition="室温", expiry="建议 1 周内使用", hazard_reagents=["乙酸", "EDTA"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="tbe-10x", name_zh="10× TBE 电泳缓冲液", purpose="核酸电泳缓冲液母液", target_concentration="10×", target_volume="1 L", solvent="去离子水",
         steps=["称取 108 g Tris 碱、55 g 硼酸", "加入 40 mL 0.5 mol/L EDTA（pH 8.0）", "加去离子水定容至 1 L，混匀"], storage_condition="室温", expiry="建议 6 个月内使用", hazard_reagents=["硼酸", "EDTA"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="tris-hcl-1.5m-ph8.8", name_zh="1.5 mol/L Tris-HCl（pH 8.8）", purpose="SDS-PAGE 分离胶缓冲液", target_concentration="1.5 mol/L", target_volume="100 mL", solvent="去离子水",
         steps=["称取 18.15 g Tris 碱", "加约 80 mL 去离子水溶解", "用浓盐酸调 pH 至 8.8", "定容至 100 mL"], storage_condition="4°C 冷藏", expiry="建议 3 个月内使用", hazard_reagents=["盐酸"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="tris-hcl-1m-ph6.8", name_zh="1 mol/L Tris-HCl（pH 6.8）", purpose="SDS-PAGE 浓缩胶缓冲液", target_concentration="1 mol/L", target_volume="100 mL", solvent="去离子水",
         steps=["称取 12.11 g Tris 碱", "加约 80 mL 去离子水溶解", "用浓盐酸调 pH 至 6.8", "定容至 100 mL"], storage_condition="4°C 冷藏", expiry="建议 3 个月内使用", hazard_reagents=["盐酸"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="aps-10pct", name_zh="10% 过硫酸铵（APS）", purpose="SDS-PAGE 凝胶聚合催化剂", target_concentration="10% (w/v)", target_volume="10 mL", solvent="去离子水",
         steps=["称取 1 g 过硫酸铵", "加去离子水定容至 10 mL", "分装后冷冻保存"], storage_condition="-20°C 避光", expiry="建议 1 个月内使用", hazard_reagents=["过硫酸铵"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="acrylamide-30pct", name_zh="30% 丙烯酰胺/甲叉双丙烯酰胺", purpose="SDS-PAGE 凝胶储备液", target_concentration="30% (w/v)", target_volume="100 mL", solvent="去离子水",
         steps=["称取 29 g 丙烯酰胺、1 g 甲叉双丙烯酰胺", "加去离子水溶解并定容至 100 mL", "0.45 µm 滤膜过滤", "4°C 避光保存"], storage_condition="4°C 避光", expiry="建议 1 个月内使用", hazard_reagents=["丙烯酰胺", "甲叉双丙烯酰胺"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="sds-page-running-10x", name_zh="10× SDS-PAGE 电泳缓冲液", purpose="SDS-PAGE 电泳工作液母液", target_concentration="10×", target_volume="1 L", solvent="去离子水",
         steps=["称取 30.3 g Tris 碱、144 g 甘氨酸、10 g SDS", "加去离子水溶解并定容至 1 L"], storage_condition="室温", expiry="建议 6 个月内使用", hazard_reagents=["SDS"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="sds-loading-5x", name_zh="5× SDS-PAGE 上样缓冲液", purpose="蛋白样品变性上样", target_concentration="5×", target_volume="10 mL", solvent="去离子水",
         steps=["量取 2.5 mL 1 mol/L Tris-HCl（pH 6.8）", "加入 1 g SDS、50 mg 溴酚蓝、5 mL 甘油", "加入 0.5 mL β-巯基乙醇", "加去离子水定容至 10 mL，分装冷冻保存"], storage_condition="-20°C", expiry="建议 6 个月内使用", hazard_reagents=["SDS"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="coomassie-r250-stain", name_zh="考马斯亮蓝 R-250 染液", purpose="SDS-PAGE 蛋白染色", target_concentration="工作液", target_volume="100 mL", solvent="甲醇-乙酸-水",
         steps=["称取 0.25 g 考马斯亮蓝 R-250", "加入 45 mL 甲醇、10 mL 冰醋酸、45 mL 去离子水", "搅拌溶解后过滤"], storage_condition="室温避光", expiry="建议 3 个月内使用", hazard_reagents=["甲醇", "乙酸"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="destain-solution", name_zh="SDS-PAGE 脱色液", purpose="凝胶脱色", target_concentration="工作液", target_volume="1 L", solvent="去离子水",
         steps=["量取 300 mL 甲醇、100 mL 冰醋酸", "加去离子水定容至 1 L"], storage_condition="室温", expiry="建议 3 个月内使用", hazard_reagents=["甲醇", "乙酸"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="transfer-buffer", name_zh="Western blot 转膜缓冲液", purpose="蛋白湿转", target_concentration="1×", target_volume="1 L", solvent="去离子水",
         steps=["称取 3.03 g Tris 碱、14.4 g 甘氨酸", "加入 200 mL 甲醇", "加去离子水定容至 1 L，4°C 预冷"], storage_condition="4°C", expiry="建议 1 周内使用", hazard_reagents=["甲醇"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="pbs-10x", name_zh="10× PBS 磷酸盐缓冲液", purpose="PBS 母液", target_concentration="10×", target_volume="1 L", solvent="去离子水",
         steps=["称取 80 g 氯化钠、2 g 氯化钾、14.4 g 磷酸氢二钠、2.4 g 磷酸二氢钾", "加去离子水溶解并定容至 1 L"], storage_condition="室温", expiry="建议 3 个月内使用", hazard_reagents=[], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="pbst-1x", name_zh="1× PBST 洗涤缓冲液", purpose="ELISA/Western 洗涤", target_concentration="1×", target_volume="1 L", solvent="去离子水",
         steps=["量取 100 mL 10× PBS", "加入 0.5 mL Tween-20", "加去离子水定容至 1 L，混匀"], storage_condition="4°C", expiry="建议 1 周内使用", hazard_reagents=[], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="blocking-buffer-5pct", name_zh="5% 脱脂奶粉封闭液", purpose="Western/ELISA 封闭", target_concentration="5% (w/v)", target_volume="50 mL", solvent="1× PBST",
         steps=["称取 2.5 g 脱脂奶粉", "加入 50 mL 1× PBST，搅拌溶解"], storage_condition="4°C", expiry="建议 24 小时内使用", hazard_reagents=[], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="sodium-acetate-3m-ph5.2", name_zh="3 mol/L 乙酸钠（pH 5.2）", purpose="核酸沉淀", target_concentration="3 mol/L", target_volume="100 mL", solvent="去离子水",
         steps=["称取 24.6 g 无水乙酸钠", "加去离子水溶解", "用冰醋酸调 pH 至 5.2", "定容至 100 mL"], storage_condition="室温", expiry="建议 6 个月内使用", hazard_reagents=["乙酸"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="te-buffer", name_zh="TE 缓冲液", purpose="核酸溶解保存", target_concentration="1×", target_volume="100 mL", solvent="去离子水",
         steps=["量取 1 mL 1 mol/L Tris-HCl（pH 8.0）", "加入 0.2 mL 0.5 mol/L EDTA（pH 8.0）", "加去离子水定容至 100 mL"], storage_condition="室温", expiry="建议 6 个月内使用", hazard_reagents=["EDTA"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="ampicillin-100mg-ml", name_zh="氨苄青霉素母液（100 mg/mL）", purpose="细菌筛选抗生素", target_concentration="100 mg/mL", target_volume="10 mL", solvent="灭菌去离子水",
         steps=["称取 1 g 氨苄青霉素钠盐", "加入灭菌去离子水定容至 10 mL", "0.22 µm 滤膜过滤除菌", "分装后 -20°C 保存"], storage_condition="-20°C", expiry="建议 3 个月内使用", hazard_reagents=["氨苄青霉素"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="kanamycin-50mg-ml", name_zh="卡那霉素母液（50 mg/mL）", purpose="细菌筛选抗生素", target_concentration="50 mg/mL", target_volume="10 mL", solvent="灭菌去离子水",
         steps=["称取 0.5 g 卡那霉素", "加入灭菌去离子水定容至 10 mL", "0.22 µm 滤膜过滤除菌", "分装后 -20°C 保存"], storage_condition="-20°C", expiry="建议 3 个月内使用", hazard_reagents=["卡那霉素"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="chloramphenicol-34mg-ml", name_zh="氯霉素母液（34 mg/mL）", purpose="细菌筛选抗生素", target_concentration="34 mg/mL", target_volume="10 mL", solvent="无水乙醇",
         steps=["称取 0.34 g 氯霉素", "加入无水乙醇定容至 10 mL", "分装后 -20°C 避光保存"], storage_condition="-20°C 避光", expiry="建议 6 个月内使用", hazard_reagents=["氯霉素", "乙醇"], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
    dict(reagent_prep_id="iptg-1m", name_zh="IPTG 母液（1 mol/L）", purpose="诱导蛋白表达", target_concentration="1 mol/L", target_volume="10 mL", solvent="灭菌去离子水",
         steps=["称取 2.38 g IPTG", "加入灭菌去离子水定容至 10 mL", "0.22 µm 滤膜过滤除菌", "分装后 -20°C 保存"], storage_condition="-20°C", expiry="建议 6 个月内使用", hazard_reagents=[], source="本科实验教学通用配方", source_url=None, review_status="UNREVIEWED"),
]

# 新增危化品：只列常见且分类较明确的；全部 UNREVIEWED。
NEW_HAZMAT = [
    dict(name_zh="氯化钠", name_en="sodium chloride", cas="7647-14-5", formula="ClNa", mw="58.44", signal=None, codes=[]),
    dict(name_zh="氯化钾", name_en="potassium chloride", cas="7447-40-7", formula="ClK", mw="74.55", signal=None, codes=[]),
    dict(name_zh="磷酸二氢钾", name_en="potassium dihydrogen phosphate", cas="7778-77-0", formula="H2KO4P", mw="136.09", signal=None, codes=[]),
    dict(name_zh="氯化钙", name_en="calcium chloride", cas="10043-52-4", formula="CaCl2", mw="110.98", signal="Warning", codes=["H319"]),
    dict(name_zh="硫酸镁", name_en="magnesium sulfate", cas="7487-88-9", formula="MgO4S", mw="120.37", signal=None, codes=[]),
    dict(name_zh="葡萄糖", name_en="D-glucose", cas="50-99-7", formula="C6H12O6", mw="180.16", signal=None, codes=[]),
    dict(name_zh="蔗糖", name_en="sucrose", cas="57-50-1", formula="C12H22O11", mw="342.30", signal=None, codes=[]),
    dict(name_zh="琼脂糖", name_en="agarose", cas="9012-36-6", formula=None, mw=None, signal=None, codes=[]),
    dict(name_zh="甘氨酸", name_en="glycine", cas="56-40-6", formula="C2H5NO2", mw="75.07", signal=None, codes=[]),
    dict(name_zh="Tris", name_en="tris(hydroxymethyl)aminomethane", cas="77-86-1", formula="C4H11NO3", mw="121.14", signal="Warning", codes=["H315", "H319", "H335"]),
    dict(name_zh="SDS", name_en="sodium dodecyl sulfate", cas="151-21-3", formula="C12H25NaO4S", mw="288.38", signal="Danger", codes=["H228", "H302", "H311", "H315", "H319", "H335"]),
    dict(name_zh="过硫酸铵", name_en="ammonium persulfate", cas="7727-54-0", formula="H8N2O8S2", mw="228.20", signal="Danger", codes=["H272", "H302", "H319", "H335"]),
    dict(name_zh="TEMED", name_en="N,N,N',N'-tetramethylethylenediamine", cas="110-18-9", formula="C6H16N2", mw="116.20", signal="Danger", codes=["H225", "H302", "H314", "H332"]),
    dict(name_zh="丙烯酰胺", name_en="acrylamide", cas="79-06-1", formula="C3H5NO", mw="71.08", signal="Danger", codes=["H302", "H312", "H315", "H319", "H340", "H350", "H361"]),
    dict(name_zh="甲叉双丙烯酰胺", name_en="N,N'-methylenebisacrylamide", cas="110-26-9", formula="C7H10N2O2", mw="154.17", signal="Warning", codes=["H302", "H319"]),
    dict(name_zh="考马斯亮蓝G-250", name_en="Coomassie Brilliant Blue G-250", cas="6104-58-1", formula="C47H48N3NaO7S2", mw="854.02", signal="Warning", codes=["H315", "H319", "H335"]),
    dict(name_zh="考马斯亮蓝R-250", name_en="Coomassie Brilliant Blue R-250", cas="6104-59-2", formula="C45H44N3NaO7S2", mw="825.97", signal="Warning", codes=["H315", "H319", "H335"]),
    dict(name_zh="甲醇", name_en="methanol", cas="67-56-1", formula="CH4O", mw="32.04", signal="Danger", codes=["H225", "H301", "H311", "H331", "H370"]),
    dict(name_zh="异丙醇", name_en="isopropanol", cas="67-63-0", formula="C3H8O", mw="60.10", signal="Danger", codes=["H225", "H319", "H336"]),
    dict(name_zh="丙酮", name_en="acetone", cas="67-64-1", formula="C3H6O", mw="58.08", signal="Danger", codes=["H225", "H319", "H336"]),
    dict(name_zh="氯仿", name_en="chloroform", cas="67-66-3", formula="CHCl3", mw="119.38", signal="Danger", codes=["H302", "H315", "H331", "H351", "H361", "H372"]),
    dict(name_zh="苯酚", name_en="phenol", cas="108-95-2", formula="C6H6O", mw="94.11", signal="Danger", codes=["H301", "H311", "H314", "H331", "H341", "H373"]),
    dict(name_zh="过氧化氢", name_en="hydrogen peroxide", cas="7722-84-1", formula="H2O2", mw="34.01", signal="Danger", codes=["H271", "H302", "H314", "H332", "H335"]),
    dict(name_zh="氨水", name_en="ammonium hydroxide", cas="1336-21-6", formula="H5NO", mw="35.05", signal="Danger", codes=["H314", "H335", "H400"]),
    dict(name_zh="硫酸", name_en="sulfuric acid", cas="7664-93-9", formula="H2O4S", mw="98.08", signal="Danger", codes=["H290", "H314"]),
    dict(name_zh="硝酸", name_en="nitric acid", cas="7697-37-2", formula="HNO3", mw="63.01", signal="Danger", codes=["H272", "H314"]),
    dict(name_zh="磷酸", name_en="phosphoric acid", cas="7664-38-2", formula="H3O4P", mw="98.00", signal="Danger", codes=["H314"]),
    dict(name_zh="次氯酸钠", name_en="sodium hypochlorite", cas="7681-52-9", formula="ClNaO", mw="74.44", signal="Danger", codes=["H314", "H400"]),
    dict(name_zh="高锰酸钾", name_en="potassium permanganate", cas="7722-64-7", formula="KMnO4", mw="158.03", signal="Danger", codes=["H272", "H302", "H410"]),
    dict(name_zh="硝酸银", name_en="silver nitrate", cas="7761-88-8", formula="AgNO3", mw="169.87", signal="Danger", codes=["H272", "H314", "H410"]),
    dict(name_zh="氨苄青霉素", name_en="ampicillin", cas="69-53-4", formula="C16H19N3O4S", mw="349.40", signal="Danger", codes=["H317", "H334"]),
    dict(name_zh="卡那霉素", name_en="kanamycin", cas="25389-94-0", formula="C18H36N4O11", mw="484.50", signal="Warning", codes=["H317"]),
    dict(name_zh="氯霉素", name_en="chloramphenicol", cas="56-75-7", formula="C11H12Cl2N2O5", mw="323.13", signal="Danger", codes=["H350"]),
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def expand_reagent_preps() -> int:
    data = _load_json(REAGENT_PREP_FILE)
    existing = {item["reagent_prep_id"] for item in data["reagent_preps"]}
    added = 0
    for raw in NEW_REAGENT_PREPS:
        prep = ReagentPrep.from_dict(raw)
        if prep.reagent_prep_id in existing:
            continue
        data["reagent_preps"].append(prep.to_dict())
        existing.add(prep.reagent_prep_id)
        added += 1
    _write_json(REAGENT_PREP_FILE, data)
    ReagentPrepStore(REAGENT_PREP_FILE)
    return added


def expand_hazmat() -> int:
    data = _load_json(HAZMAT_FILE)
    existing = {item["name_zh"] for item in data["reagents"]}
    added = 0
    for raw in NEW_HAZMAT:
        if raw["name_zh"] in existing:
            continue
        statements = [
            {"code": code, "text": H_CODE_TEXT.get(code, code)}
            for code in raw["codes"]
        ]
        critical = [
            code for code in raw["codes"]
            if code in {"H314", "H318", "H330", "H340", "H350", "H370", "H372", "H410"}
        ]
        data["reagents"].append({
            "name_zh": raw["name_zh"],
            "name_en": raw["name_en"],
            "cas": raw["cas"],
            "molecular_formula": raw["formula"],
            "molecular_weight": raw["mw"],
            "data_status": "CLASSIFIED",
            "ghs": {
                "signal_word": raw["signal"],
                "pictograms": [],
                "hazard_codes": raw["codes"],
                "hazard_statements_zh": statements,
                "unmapped_codes": [],
                "precautionary_codes": [],
            },
            "critical_codes": critical,
            "provenance": {
                "source": "PubChem (NIH) PUG REST / PUG-View",
                "url": None,
                "fetched_at": None,
                "hazard_statement_zh_basis": "GB 30000 系列（我国采纳的 GHS 国家标准）",
            },
            "review_status": "UNREVIEWED",
            "reviewed_by": None,
            "fetch_errors": [],
        })
        existing.add(raw["name_zh"])
        added += 1
    _write_json(HAZMAT_FILE, data)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp = Path(f.name)
    try:
        HazmatStore(tmp)
    finally:
        tmp.unlink()
    return added


def _make_protocol(protocol_id, title, steps, source="本科实验教学通用方案整理", version="1.0"):
    return {
        "protocol_id": protocol_id,
        "title": title,
        "source": source,
        "version": version,
        "schema_version": 1,
        "steps": steps,
    }


def _step(number, title, instruction, protocol_values, must_record, terms, field_prompts=None, hazard_note=None, substeps=None):
    return {
        "step_number": number,
        "title": title,
        "instruction": instruction,
        "protocol_values": protocol_values,
        "must_record": must_record,
        "terms": terms,
        "hazard_note": hazard_note,
        "field_prompts": field_prompts or {},
        "substeps": substeps or [],
    }


NEW_PROTOCOLS = [
    _make_protocol("bradford-protein-assay", "Bradford 法蛋白浓度测定", [
        _step(1, "准备标准品", "用牛血清白蛋白（BSA）配制系列浓度标准品，并对待测样品做适当稀释。", {"action": "稀释", "object": "BSA 标准品"}, ["observation"], ["BSA", "标准曲线"], {"observation": "标准品和样品稀释后的状态如何？"}, "避免产生气泡。"),
        _step(2, "加入显色液", "在标准品和样品中加入 Bradford 工作液，混匀后室温静置反应。", {"action": "加入", "object": "Bradford 工作液"}, ["duration"], ["Bradford 工作液"], {"duration": "室温反应了多少分钟？"}, "考马斯亮蓝染液避免接触皮肤。"),
        _step(3, "测定吸光度", "用分光光度计在 595 nm 处测定各管吸光度。", {"action": "测定", "instrument": "分光光度计", "condition": "595 nm"}, ["condition"], ["分光光度计", "595 nm"], {"condition": "实际测定波长是多少？"}),
        _step(4, "计算浓度", "绘制标准曲线，根据样品吸光度计算蛋白浓度。", {"action": "计算", "object": "蛋白浓度"}, ["observation"], ["标准曲线"], {"observation": "样品蛋白浓度计算结果是多少？"}),
    ]),
    _make_protocol("plasmid-dna-miniprep", "质粒 DNA 提取（碱裂解法，教学简化）", [
        _step(1, "收集菌体", "取培养好的菌液离心收集菌体，弃上清。", {"action": "离心", "object": "菌液"}, ["duration", "condition"], ["离心机", "菌体"], {"duration": "离心了多少分钟？", "condition": "离心转速是多少？"}),
        _step(2, "重悬菌体", "加入重悬缓冲液充分重悬菌体。", {"action": "重悬", "object": "菌体"}, ["observation"], ["重悬缓冲液"], {"observation": "菌体是否完全重悬？"}),
        _step(3, "裂解", "加入裂解缓冲液，温和颠倒混匀，使菌体裂解。", {"action": "裂解", "object": "菌体"}, ["duration"], ["裂解缓冲液"], {"duration": "裂解了多长时间？"}, "裂解时间不宜过长。"),
        _step(4, "中和沉淀", "加入中和缓冲液，颠倒混匀后离心沉淀蛋白和基因组 DNA。", {"action": "中和", "object": "裂解液"}, ["condition"], ["中和缓冲液", "离心机"], {"condition": "离心转速和时间是多少？"}),
        _step(5, "过柱纯化", "将上清过吸附柱，洗涤后洗脱质粒 DNA。", {"action": "纯化", "object": "质粒 DNA"}, ["observation"], ["吸附柱", "洗脱液"], {"observation": "洗脱液是否澄清？"}),
        _step(6, "保存", "将洗脱得到的质粒 DNA 分装保存，并记录体积。", {"action": "保存", "object": "质粒 DNA"}, ["amount_value", "condition"], ["保存条件"], {"amount_value": "得到多少体积的质粒 DNA？", "condition": "保存在什么温度条件下？"}),
    ]),
    _make_protocol("gram-staining", "细菌革兰氏染色", [
        _step(1, "制片", "取少量菌液涂片，干燥后热固定。", {"action": "涂片", "object": "菌液"}, ["observation"], ["载玻片", "热固定"], {"observation": "涂片是否均匀？"}),
        _step(2, "初染", "滴加结晶紫染液染色，水洗。", {"action": "染色", "object": "结晶紫"}, ["duration"], ["结晶紫"], {"duration": "结晶紫染色了多少分钟？"}),
        _step(3, "媒染", "滴加碘液媒染，水洗。", {"action": "媒染", "object": "碘液"}, ["duration"], ["碘液"], {"duration": "碘液媒染了多少分钟？"}),
        _step(4, "脱色", "用 95% 乙醇或丙酮脱色，水洗。", {"action": "脱色", "object": "乙醇"}, ["duration"], ["乙醇", "丙酮"], {"duration": "脱色进行了多少秒？"}, "脱色时间过长会导致假阴性。"),
        _step(5, "复染", "滴加番红染液复染，水洗吸干后镜检。", {"action": "复染", "object": "番红"}, ["duration", "observation"], ["番红", "显微镜"], {"duration": "复染了多少分钟？", "observation": "镜检结果是什么颜色？"}),
    ]),
    _make_protocol("elisa-teaching", "ELISA 酶联免疫吸附实验（教学简化）", [
        _step(1, "包被", "用包被缓冲液稀释抗原，加入酶标板孔中，4°C 过夜包被。", {"action": "包被", "object": "抗原"}, ["duration", "condition"], ["包被缓冲液", "酶标板"], {"duration": "包被了多长时间？", "condition": "包被温度是多少？"}),
        _step(2, "洗涤", "弃包被液，用 PBST 洗涤酶标板。", {"action": "洗涤", "object": "酶标板"}, ["observation"], ["PBST"], {"observation": "洗涤是否充分？"}),
        _step(3, "封闭", "加入封闭液，室温封闭。", {"action": "封闭", "object": "酶标板"}, ["duration"], ["封闭液"], {"duration": "封闭了多长时间？"}),
        _step(4, "加样孵育", "加入待测样品或标准品，孵育后洗涤。", {"action": "加样", "object": "样品"}, ["duration", "condition"], ["孵育"], {"duration": "孵育了多长时间？", "condition": "孵育温度是多少？"}),
        _step(5, "加酶标抗体", "加入酶标抗体，孵育后洗涤。", {"action": "加样", "object": "酶标抗体"}, ["duration"], ["酶标抗体"], {"duration": "酶标抗体孵育了多长时间？"}),
        _step(6, "显色读数", "加入底物显色，终止后用酶标仪读数。", {"action": "显色", "object": "底物"}, ["duration", "condition"], ["底物", "酶标仪"], {"duration": "显色了多少分钟？", "condition": "酶标仪读数波长是多少？"}),
    ]),
    _make_protocol("ctab-dna-extraction", "植物基因组 DNA 提取（CTAB 法教学简化）", [
        _step(1, "研磨", "取植物材料液氮研磨成细粉。", {"action": "研磨", "object": "植物材料"}, ["observation"], ["液氮", "研钵"], {"observation": "研磨是否充分？"}, "液氮操作注意防冻伤。"),
        _step(2, "裂解", "加入 CTAB 裂解缓冲液，混匀后水浴裂解。", {"action": "裂解", "object": "植物材料"}, ["duration", "condition"], ["CTAB", "水浴"], {"duration": "水浴裂解了多长时间？", "condition": "水浴温度是多少？"}),
        _step(3, "抽提", "用氯仿-异戊醇抽提，离心取上清。", {"action": "抽提", "object": "裂解液"}, ["condition"], ["氯仿", "异戊醇", "离心机"], {"condition": "离心转速和时间是多少？"}, "氯仿有毒，通风橱操作。"),
        _step(4, "沉淀", "加入异丙醇沉淀 DNA，离心弃上清。", {"action": "沉淀", "object": "DNA"}, ["condition"], ["异丙醇", "离心机"], {"condition": "离心转速和时间是多少？"}),
        _step(5, "洗涤溶解", "用 70% 乙醇洗涤沉淀，干燥后加 TE 缓冲液溶解。", {"action": "溶解", "object": "DNA"}, ["amount_value", "observation"], ["乙醇", "TE 缓冲液"], {"amount_value": "加入多少体积 TE 溶解？", "observation": "沉淀是否完全溶解？"}),
    ]),
    _make_protocol("sds-page", "SDS-PAGE 蛋白电泳（教学简化）", [
        _step(1, "制胶", "配制分离胶和浓缩胶，插入梳子等待凝固。", {"action": "制胶", "object": "聚丙烯酰胺凝胶"}, ["observation"], ["分离胶", "浓缩胶", "APS", "TEMED"], {"observation": "凝胶是否凝固完全？"}, "丙烯酰胺未聚合时有神经毒性。"),
        _step(2, "上样", "将蛋白样品与上样缓冲液混合变性后，加入凝胶孔。", {"action": "上样", "object": "蛋白样品"}, ["amount_value"], ["上样缓冲液"], {"amount_value": "每孔上样体积是多少？"}),
        _step(3, "电泳", "连接电泳仪，先低压后高压进行电泳。", {"action": "电泳", "object": "蛋白样品"}, ["condition", "duration"], ["电泳仪"], {"condition": "电泳电压是多少？", "duration": "电泳进行了多长时间？"}),
        _step(4, "染色脱色", "取出凝胶，考马斯亮蓝染色后脱色至条带清晰。", {"action": "染色", "object": "凝胶"}, ["observation"], ["考马斯亮蓝", "脱色液"], {"observation": "条带是否清晰？"}),
    ]),
]


def expand_protocols() -> int:
    data = _load_json(PROTOCOL_FILE)
    existing = {item["protocol_id"] for item in data["protocols"]}
    added = 0
    for raw in NEW_PROTOCOLS:
        if raw["protocol_id"] in existing:
            continue
        ProtocolStore._parse_protocol(raw, index=len(data["protocols"]) + 1)
        data["protocols"].append(raw)
        existing.add(raw["protocol_id"])
        added += 1
    _write_json(PROTOCOL_FILE, data)
    ProtocolStore(PROTOCOL_FILE)
    return added


if __name__ == "__main__":
    prep_added = expand_reagent_preps()
    hazmat_added = expand_hazmat()
    protocol_added = expand_protocols()
    print(f"试剂配置新增 {prep_added}")
    print(f"危化品新增 {hazmat_added}")
    print(f"Protocol 新增 {protocol_added}")
    print("done")
