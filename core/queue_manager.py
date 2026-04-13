import threading
import time
import traceback
import asyncio
from core.event_system import events


class DownloadQueueManager:
    def __init__(self, controller=None):
        self.controller = controller
        self.tasks = []
        self.lock = threading.RLock()
        self.active_tasks = {}

        self.max_workers = 2
        self.workers = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)

    def add_to_queue(self, task_data):
        with self.lock:
            self.tasks.append(task_data)
        events.emit(
            "log",
            f"QUEUE: Added '{task_data.get('name')}' to queue. (Total pending: {len(self.tasks)})",
        )
        self._emit_size()

    def _emit_size(self):
        with self.lock:
            total = len(self.tasks) + len(self.active_tasks)
            events.emit("queue_size_update", total)

    def get_queue_size(self):
        with self.lock:
            return len(self.tasks) + len(self.active_tasks)

    def get_pending_tasks(self):
        with self.lock:
            return list(self.tasks)

    def remove_from_queue(self, index):
        with self.lock:
            if 0 <= index < len(self.tasks):
                removed = self.tasks.pop(index)
                events.emit(
                    "log", f"QUEUE: Removed '{removed.get('name')}' from queue."
                )
                self._emit_size()
                return True
        return False

    def move_up(self, index):
        with self.lock:
            if 1 <= index < len(self.tasks):
                self.tasks[index], self.tasks[index - 1] = (
                    self.tasks[index - 1],
                    self.tasks[index],
                )
                return True
        return False

    def move_down(self, index):
        with self.lock:
            if 0 <= index < len(self.tasks) - 1:
                self.tasks[index], self.tasks[index + 1] = (
                    self.tasks[index + 1],
                    self.tasks[index],
                )
                return True
        return False

    def move_to_top(self, index):
        with self.lock:
            if 0 < index < len(self.tasks):
                task = self.tasks.pop(index)
                self.tasks.insert(0, task)
                return True
        return False

    def _worker(self):
        tid = threading.get_ident()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            try:
                task = None
                with self.lock:
                    if self.tasks:
                        task = self.tasks.pop(0)
                        self.active_tasks[tid] = task
                        self._emit_size()

                if not task:
                    time.sleep(1)
                    continue

                events.emit("log", f"QUEUE: Processing next item: {task.get('name')}")

                if not self.controller:
                    events.emit("log", "QUEUE ERROR: Controller not initialized.")
                    with self.lock:
                        if tid in self.active_tasks:
                            del self.active_tasks[tid]
                    continue

                try:
                    if self.controller.stop_event.is_set():
                        events.emit("log", "QUEUE: Stop event set, skipping task.")
                    else:
                        self.controller.process_queued_item(task)
                except Exception as e:
                    events.emit(
                        "log", f"QUEUE ERROR: Task '{task.get('name')}' failed: {e}"
                    )
                    events.emit("log", traceback.format_exc())
                finally:
                    with self.lock:
                        if tid in self.active_tasks:
                            del self.active_tasks[tid]

                    events.emit("log", f"QUEUE: Task '{task.get('name')}' finalized.")

                    with self.lock:
                        if not self.tasks and not self.active_tasks and self.controller:
                            for s in list(self.controller.scrapers.values()):
                                try:
                                    s.quit_driver()
                                except:
                                    pass
                            self.controller.scrapers.clear()

                        if (
                            not self.tasks
                            and not self.active_tasks
                            and self.controller
                            and self.controller.missing_links
                            and not self.controller.stop_event.is_set()
                        ):
                            events.emit("show_missing_links")

                    self._emit_size()
                    time.sleep(2)

            except Exception as e:
                events.emit("log", f"QUEUE MANAGER CRITICAL ERROR: {e}")
                with self.lock:
                    if tid in self.active_tasks:
                        del self.active_tasks[tid]
                time.sleep(5)
