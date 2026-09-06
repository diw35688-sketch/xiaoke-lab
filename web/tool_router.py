# -*- coding: utf-8 -*-
"""按对话场景动态注入工具，替代把 58 个工具全发给模型。

核心思路：
  1. 核心工具每次都带（实验流程、计时、计算、试剂查询、导航）
  2. Skill 组按用户消息关键词自动检测注入
  3. 模型可通过 activate_skill 主动激活某组
  4. 已激活的 skill 在会话内保持（直到用户切换话题）

这样每次请求只发 ~18 个核心工具 + 0-1 个 skill 组，
而不是 58 个全部塞进去。
"""

from __future__ import annotations

import json
import re

import lab_tools


# ── 工具分组 ──

# 开发者工具：永远不发给科研助手模型
_EXCLUDED = {
    "read_uploaded_file", "run_bash", "list_project_files",
    "read_project_file", "search_project_text", "list_project_docs",
    "check_project_environment",
}

# 核心工具：每次请求都带
_CORE = {
    # 实验流程
    "get_current_step", "move_step", "record_observation",
    "navigate_view", "get_protocol_detail",
    "get_protocol_prep_requirements", "search_protocols",
    "generate_prep_bench", "mark_prep_item", "set_prep_bench_status",
    "rescale_prep_bench",
    # 计时
    "start_timer", "check_timer", "start_step_timer",
    # 试剂查询（只读）
    "list_reagent_preps", "get_reagent_prep", "check_reagent_safety",
    # 知识库检索（引物表等共享表格）
    "search_knowledge_base",
    # 基础计算（其余高级计算走 skill 组）
    "calculate", "calculate_solution_prep", "calculate_dilution",
    # 时间基础
    "get_current_time", "generate_schedule",
    # 杂项
    "list_experiment_commands",
}

# Skill 组：按需加载
SKILL_GROUPS = {
    "storage": {
        "description": "储存库管理：查库存、入库、修改物品、管理存储位置",
        "keywords": [
            "储存", "库存", "入库", "冰箱", "冰柜", "试剂柜", "存放",
            "存到", "保存到库", "放到", "取出", "取用", "丢弃", "扔掉",
            "过期", "位置", "架位", "样品柜", "种子", " glycerol",
            "存了什么", "有什么", "还剩多少", "消耗",
        ],
        "tools": {
            "list_storage_items", "add_storage_item", "update_storage_item",
            "delete_storage_item", "list_storage_locations", "add_storage_location",
            "storage_stats",
        },
    },
    "protocol_edit": {
        "description": "方案选择与管理：选方案、创建方案、修改步骤",
        "keywords": [
            "选方案", "创建方案", "新建方案", "制作方案",
            "改方案", "修改方案", "加一步", "删一步", "改步骤",
            "添加步骤", "删除步骤", "修改步骤", "编辑方案",
            "我要做", "开始做", "换方案", "切方案", "哪个方案",
            "建个方案", "弄个方案", "写个方案", "PCR方案",
            "提取方案", "跑个", "做个",
            "看方案", "有什么方案", "列出方案", "浏览方案",
            "方案列表", "有哪些方案",
            "制作一个", "做一个实验", "制作实验", "制作一个实验",
            "菌落", "重新制作方案", "新建一个", "建一个方案",
        ],
        "tools": {
            "list_protocols", "select_protocol", "create_protocol_from_text",
            "add_protocol_step", "update_protocol_step", "delete_protocol_step",
            "suggest_step_improvement",
        },
    },
    "reagent_edit": {
        "description": "配方与社区：创建/修改配方、搜社区方案、导入模板、联网查配方、启动配制流程",
        "keywords": [
            "创建配方", "新建配方", "改配方", "修改配方", "删配方",
            "制作配方", "编辑配方", "配制流程", "开始配",
            "搜社区", "导入方案", "导入模板", "导入这个",
            "怎么配", "配方来源", "缺什么配方", "社区下载",
            "网上查", "联网查", "上网找", "互联网", "搜一下", "网上找",
            "查一下配方", "没有这个配方", "本地没有", "临时配方",
        ],
        "tools": {
            "create_reagent_prep_from_text", "update_reagent_prep",
            "delete_reagent_prep", "start_reagent_prep_flow",
            "show_reagent_prep_flow", "advance_reagent_prep_flow",
            "search_community", "import_community_entry",
            "web_search", "web_search_and_save_recipe",
        },
    },
    "time_planning": {
        "description": "时间规划：时钟安排、剩余时间、跨实验规划、分子量/比例计算",
        "keywords": [
            "安排时间", "帮我安排", "几点能做完", "9点开始",
            "午饭", "下班", "还有多久", "怎么做最快",
            "分子量", "摩尔质量", "比例", "按比例",
            "今天做", "来得及",
        ],
        "tools": {
            "get_remaining_schedule", "plan_multi_protocols",
            "plan_clock_schedule",
            "calculate_molecular_weight", "calculate_proportion",
        },
    },
    "experiment_mgmt": {
        "description": "实验安排管理：创建实验计划、记录长期记忆",
        "keywords": [
            "安排实验", "计划实验", "创建实验", "新实验",
            "记住这个", "长期记忆", "帮我记住", "别忘了",
            "帮我记一下", "保存记忆",
        ],
        "tools": {
            "list_experiments", "check_conflicts", "propose_experiment",
            "confirm_create_experiment", "propose_memory", "confirm_save_memory",
        },
    },
}

# activate_skill 入口工具定义（让模型能主动请求某组工具）
_ACTIVATE_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "activate_skill",
        "description": (
            "激活一组扩展工具。当用户要做储存库操作、方案编辑、配方编辑或实验安排时调用。"
            "调用后该组工具在后续对话中可用。可用 skill："
            + "；".join(f'{k}（{v["description"]}）' for k, v in SKILL_GROUPS.items())
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "enum": list(SKILL_GROUPS.keys()),
                    "description": "要激活的 skill 名称",
                },
            },
            "required": ["skill"],
            "additionalProperties": False,
        },
    },
}

# suggest_step_improvement 归入 protocol_edit 组


# ── 会话级激活状态 ──
# 只保留模型主动调 activate_skill 的能力；关键词检测是每轮独立、用完即弃。

_active_skills: dict[str, set[str]] = {}
_active_skills_lock = None  # 延迟创建


def _get_lock():
    global _active_skills_lock
    if _active_skills_lock is None:
        import threading
        _active_skills_lock = threading.Lock()
    return _active_skills_lock


def activate_skill(conversation_id: str | None, skill_name: str) -> dict:
    """激活某个 skill 组，返回确认信息。"""
    if skill_name not in SKILL_GROUPS:
        return {"ok": False, "error": f"未知 skill：{skill_name}"}
    cid = conversation_id or "_default"
    with _get_lock():
        _active_skills.setdefault(cid, set()).add(skill_name)
    group = SKILL_GROUPS[skill_name]
    return {
        "ok": True,
        "skill": skill_name,
        "description": group["description"],
        "tools_unlocked": sorted(group["tools"]),
    }


def deactivate_skills(conversation_id: str | None):
    """清除会话的激活状态。"""
    cid = conversation_id or "_default"
    with _get_lock():
        _active_skills.pop(cid, None)


def _get_active_skills(conversation_id: str | None) -> set[str]:
    cid = conversation_id or "_default"
    with _get_lock():
        return set(_active_skills.get(cid, set()))


# ── 关键词检测 ──

def detect_skills_from_message(message: str) -> set[str]:
    """从用户消息文本自动检测需要哪些 skill 组。"""
    if not message:
        return set()
    text = message.lower().strip()
    detected = set()
    for skill_name, group in SKILL_GROUPS.items():
        for kw in group["keywords"]:
            if kw.lower() in text:
                detected.add(skill_name)
                break
    return detected


# ── 主入口：构建发给模型的工具列表 ──

def build_tools(
    conversation_id: str | None,
    user_message: str = "",
    *,
    include_activate_skill: bool = True,
    extra_tools: list[dict] | None = None,
) -> list[dict]:
    """构建本轮发给模型的工具列表。

    = 核心工具 + 本轮关键词检测到的 skill 组 + 模型之前激活的 skill 组。
    每轮独立，用完即弃——不做持久化。

    extra_tools：来自 core.TOOLS 里直接定义的工具（不在 lab_tools 里的）。
    """
    detected = detect_skills_from_message(user_message)
    active = _get_active_skills(conversation_id)
    all_skills = detected | active

    # 收集需要的工具名
    needed = set(_CORE)
    for skill_name in all_skills:
        group = SKILL_GROUPS.get(skill_name)
        if group:
            needed |= group["tools"]

    # 从全量工具定义中筛选（合并 lab_tools + extra_tools）
    tool_map = {t["function"]["name"]: t for t in lab_tools.openai_tools()}
    if extra_tools:
        for t in extra_tools:
            tool_map.setdefault(t["function"]["name"], t)
    result = []
    for name in sorted(needed):
        if name in _EXCLUDED:
            continue
        tool = tool_map.get(name)
        if tool:
            result.append(tool)

    # 加 activate_skill 入口
    if include_activate_skill and len(all_skills) < len(SKILL_GROUPS):
        result.append(dict(_ACTIVATE_SKILL_TOOL))

    return result


def handle_activate_skill(args: dict, conversation_id: str | None) -> dict:
    """处理模型调用的 activate_skill 工具。"""
    skill = args.get("skill", "")
    return activate_skill(conversation_id, skill)


def is_activate_skill_call(name: str) -> bool:
    return name == "activate_skill"


# ── 重置（测试用）──

def _reset():
    """清空所有激活状态。仅供测试。"""
    with _get_lock():
        _active_skills.clear()
