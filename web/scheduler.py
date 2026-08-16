import threading
from datetime import datetime, timedelta
from database.crud import run_daily_experiment_check

_started = False
_lock = threading.Lock()


def _seconds_until_next_eight():
    now = datetime.now()
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _daily_loop():
    while True:
        threading.Event().wait(_seconds_until_next_eight())
        try:
            run_daily_experiment_check()
        except Exception:
            # 定时检查失败不应让服务退出；下一天会自动再次尝试。
            pass


def start_daily_scheduler():
    global _started
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_daily_loop, name="daily-experiment-check", daemon=True).start()
