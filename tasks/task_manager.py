from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from agent.core import ModelServiceError, run_agent
from database.crud import add_message
from database.task_store import (
    cancel_task, claim_task, complete_task, create_task, fail_task,
    get_task, queued_task_ids, set_progress,
)


class TaskManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lab-agent-worker")
        self._conversation_locks = defaultdict(Lock)
        self._scheduled = set()
        self._guard = Lock()

    def start(self):
        for task_id in queued_task_ids():
            self._schedule(task_id)

    def submit(self, conversation_id, prompt, kind="agent_request"):
        task = create_task(conversation_id, prompt, kind)
        self._schedule(task["id"])
        return task

    def cancel(self, task_id):
        return cancel_task(task_id)

    def _schedule(self, task_id):
        with self._guard:
            if task_id in self._scheduled:
                return
            self._scheduled.add(task_id)
        self.executor.submit(self._run, task_id)

    def _run(self, task_id):
        try:
            initial = get_task(task_id)
            if not initial or initial["status"] != "queued":
                return
            with self._conversation_locks[initial["conversation_id"]]:
                task = claim_task(task_id)
                if not task:
                    return
                set_progress(task_id, "正在后台处理请求")
                # 每个会话的后台 Agent 串行执行，防止相互覆盖上下文或并发写入。
                answer = run_agent([{"role": "user", "content": task["prompt"]}], task["conversation_id"])
                latest = get_task(task_id)
                if latest and latest["status"] == "cancelling":
                    cancel_task(task_id)
                    return
                finished = complete_task(task_id, answer)
                if finished and finished["status"] == "completed":
                    add_message(task["conversation_id"], "assistant", answer)
        except ModelServiceError as error:
            fail_task(task_id, error.detail)
        except Exception as error:
            fail_task(task_id, f"后台任务异常：{error}")
        finally:
            with self._guard:
                self._scheduled.discard(task_id)


task_manager = TaskManager()
