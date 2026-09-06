import threading

from cron_service import start_cron_service, stop_cron_service

_started = False
_lock = threading.Lock()


def start_daily_scheduler():
    """兼容旧入口：现在由持久化 cron 服务统一调度心跳/反思/每日检查。"""
    global _started
    with _lock:
        if _started:
            return
        _started = True
        start_cron_service()


def stop_daily_scheduler():
    stop_cron_service()
