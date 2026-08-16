import re

# 明确需要工具、数据库或多步骤处理的动作。
ACTION_PATTERN = re.compile(r"(查询|查一下|查一查|检查|冲突|安排|创建|新建|计划|模板|总结|汇总|导出|上传|知识库|预约|预定|取消|修改|更新)")
# 实验室对象出现时，即使用户省略了“查询”，也通常需要查数据库或工具。
LAB_OBJECT_PATTERN = re.compile(r"(实验|实验记录|实验安排|日程|离心机|显微镜|酶标仪|PCR仪|电泳|转膜|成像仪|仪器|设备|CCK-?8|WB|Western|PCR|样品|试剂|耗材)", re.IGNORECASE)
# 与实验室对象组合出现的排期表达。
SCHEDULE_PATTERN = re.compile(r"(今天|明天|后天|上午|下午|晚上|几点|点到|有空|空吗|时间|周[一二三四五六日天]|本周|下周)")
SMALL_TALK_PATTERN = re.compile(r"^(你好|嗨|在吗|谢谢|再见|你是谁|今天星期几|现在几点)[！!。？? ]*$")


def requires_background_task(message: str) -> bool:
    """简单闲聊走实时回答；实验室查询、排期和工具工作交给后台。"""
    text = message.strip()
    if not text or SMALL_TALK_PATTERN.fullmatch(text):
        return False
    if ACTION_PATTERN.search(text):
        return True
    return bool(LAB_OBJECT_PATTERN.search(text) and SCHEDULE_PATTERN.search(text)) or bool(LAB_OBJECT_PATTERN.search(text))


def acknowledgement(task_id: str) -> str:
    return f"好的，我已把这个请求交给后台处理（任务 #{task_id}）。你可以继续提问，完成后我会主动告诉你结果。"
