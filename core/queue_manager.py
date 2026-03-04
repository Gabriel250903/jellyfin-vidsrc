import threading
import time
import os
import traceback


class DownloadQueueManager:
    def __init__(self, app):
        self.app = app
        self.tasks = []
        self.lock = threading.Lock()
        self.current_task = None
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def add_to_queue(self, task_data):
        with self.lock:
            self.tasks.append(task_data)
        self.app.log(
            f"QUEUE: Added '{task_data.get('name')}' to queue. (Total pending: {len(self.tasks)})"
        )

    def get_queue_size(self):
        with self.lock:
            return len(self.tasks)

    def get_pending_tasks(self):
        with self.lock:
            return list(self.tasks)

    def remove_from_queue(self, index):
        with self.lock:
            if 0 <= index < len(self.tasks):
                removed = self.tasks.pop(index)
                self.app.log(f"QUEUE: Removed '{removed.get('name')}' from queue.")
                return True
        return False

    def _worker(self):
        while True:
            try:
                task = None
                with self.lock:
                    if self.tasks:
                        task = self.tasks.pop(0)

                if not task:
                    time.sleep(1)
                    continue

                self.current_task = task
                self.app.log(f"QUEUE: Processing next item: {task.get('name')}")

                try:
                    if self.app.stop_event.is_set():
                        self.app.log("QUEUE: Stop event set, skipping task.")
                    else:
                        self.app.process_queued_item(task)
                except Exception as e:
                    self.app.log(f"QUEUE ERROR: Task '{task.get('name')}' failed: {e}")
                    self.app.log(traceback.format_exc())
                finally:
                    if hasattr(self.app, "driver") and self.app.driver:
                        try:
                            self.app.driver.quit()
                        except:
                            pass
                        self.app.driver = None

                    self.current_task = None
                    self.app.log(f"QUEUE: Task '{task.get('name')}' finalized.")

                    with self.lock:
                        if (
                            not self.tasks
                            and self.app.missing_links
                            and not self.app.stop_event.is_set()
                        ):
                            self.app.after(1000, self.app.show_missing_links)

                    time.sleep(2)

            except Exception as e:
                if self.app:
                    self.app.log(f"QUEUE MANAGER CRITICAL ERROR: {e}")
                time.sleep(5)
