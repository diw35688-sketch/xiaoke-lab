from datetime import datetime
from database.crud import list_experiments


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("时间请使用 ISO 格式，例如 2026-08-01T09:00") from error


def find_conflicts(start_at, end_at, equipment):
    start, end = parse_time(start_at), parse_time(end_at)
    if not all([start, end, equipment]):
        return []
    if end <= start:
        raise ValueError("结束时间必须晚于开始时间")
    return [
        item for item in list_experiments()
        if item["status"] != "completed"
        and item["equipment"].strip().lower() == equipment.strip().lower()
        and parse_time(item["start_at"])
        and parse_time(item["end_at"])
        and start < parse_time(item["end_at"])
        and end > parse_time(item["start_at"])
    ]
