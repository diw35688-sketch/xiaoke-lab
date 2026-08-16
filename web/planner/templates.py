from copy import deepcopy
from datetime import datetime, timedelta


TEMPLATES = [
    {
        "id": "cck8", "name": "CCK-8 细胞活性检测", "goal": "完成细胞活性检测并整理结果。",
        "description": "包含准备、处理、检测与结果归档的计划骨架；具体条件请按实验室 SOP 确认。",
        "consumables": ["96 孔板", "CCK-8 试剂", "移液器吸头", "待测样品"],
        "steps": [
            {"title": "样品与细胞状态确认", "offset_hours": 0, "duration_hours": 0.5, "equipment": "", "depends_on": [], "notes": "确认样品、细胞状态及当日安排；关键条件按 SOP 执行。"},
            {"title": "铺板与实验记录", "offset_hours": 1, "duration_hours": 1, "equipment": "生物安全柜", "depends_on": [1], "notes": "完成铺板并记录批次、孔位与分组。"},
            {"title": "处理与观察节点", "offset_hours": 25, "duration_hours": 0.5, "equipment": "", "depends_on": [2], "notes": "按既定方案完成处理并记录观察时间。"},
            {"title": "读板检测", "offset_hours": 49, "duration_hours": 1, "equipment": "酶标仪", "depends_on": [3], "notes": "检测前确认仪器预约、板型和实验室 SOP。"},
            {"title": "结果导出与初步整理", "offset_hours": 50.5, "duration_hours": 0.5, "equipment": "", "depends_on": [4], "notes": "导出原始数据，关联到本次实验记录。"},
        ],
    },
    {
        "id": "western_blot", "name": "Western blot", "goal": "完成蛋白检测流程并归档图像与分析结果。",
        "description": "用于排期与资源协调；抗体、样品和关键条件必须按本实验室 SOP 确认。",
        "consumables": ["样品", "凝胶/试剂", "膜", "一抗/二抗", "显影耗材"],
        "steps": [
            {"title": "样品与抗体计划确认", "offset_hours": 0, "duration_hours": 0.5, "equipment": "", "depends_on": [], "notes": "确认样品、抗体、耗材与仪器预约。"},
            {"title": "样品处理与上样准备", "offset_hours": 1, "duration_hours": 2, "equipment": "", "depends_on": [1], "notes": "按 SOP 完成样品和上样准备。"},
            {"title": "电泳与转膜", "offset_hours": 3.5, "duration_hours": 2, "equipment": "电泳转膜仪", "depends_on": [2], "notes": "记录胶、膜和仪器使用信息。"},
            {"title": "抗体孵育与检测准备", "offset_hours": 6, "duration_hours": 1, "equipment": "", "depends_on": [3], "notes": "按 SOP 安排后续孵育与检测时间。"},
            {"title": "成像与结果归档", "offset_hours": 30, "duration_hours": 1, "equipment": "化学发光成像仪", "depends_on": [4], "notes": "导出图像并记录初步结论。"},
        ],
    },
    {
        "id": "pcr", "name": "PCR 检测", "goal": "完成 PCR 检测计划并归档结果。",
        "description": "用于排期与记录，不包含体系配制或循环参数；请严格遵循实验室 SOP。",
        "consumables": ["模板", "引物", "PCR 相关试剂", "PCR 管", "吸头"],
        "steps": [
            {"title": "模板与引物计划确认", "offset_hours": 0, "duration_hours": 0.5, "equipment": "", "depends_on": [], "notes": "确认模板、引物、对照和样本编号。"},
            {"title": "反应准备与记录", "offset_hours": 0.5, "duration_hours": 1, "equipment": "", "depends_on": [1], "notes": "按 SOP 配置并完成板位/管位记录。"},
            {"title": "PCR 仪运行", "offset_hours": 1.5, "duration_hours": 2, "equipment": "PCR仪", "depends_on": [2], "notes": "确认仪器预约与程序设置符合 SOP。"},
            {"title": "结果检查与归档", "offset_hours": 3.75, "duration_hours": 0.5, "equipment": "", "depends_on": [3], "notes": "导出结果并记录异常与后续安排。"},
        ],
    },
]


def list_templates():
    return deepcopy(TEMPLATES)


def get_template(template_id: str):
    for template in TEMPLATES:
        if template["id"] == template_id:
            return deepcopy(template)
    raise ValueError("未找到该实验模板。")


def build_plan(template_id: str, start_at: str, plan_name: str = ""):
    template = get_template(template_id)
    try:
        base_time = datetime.fromisoformat(start_at)
    except (TypeError, ValueError) as error:
        raise ValueError("计划开始时间格式无效。") from error
    title = plan_name.strip() or template["name"]
    planned_steps = []
    for index, step in enumerate(template["steps"], start=1):
        start = base_time + timedelta(hours=float(step["offset_hours"]))
        end = start + timedelta(hours=float(step["duration_hours"]))
        dependencies = [int(item) for item in step.get("depends_on", [])]
        planned_steps.append({
            "order": index,
            "name": f"{title} · {step['title']}",
            "short_name": step["title"],
            "goal": template["goal"],
            "start_at": start.isoformat(timespec="minutes"),
            "end_at": end.isoformat(timespec="minutes"),
            "equipment": step.get("equipment", ""),
            "notes": step.get("notes", ""),
            "depends_on": dependencies,
        })
    return {"template": template, "plan_name": title, "start_at": base_time.isoformat(timespec="minutes"), "steps": planned_steps}
