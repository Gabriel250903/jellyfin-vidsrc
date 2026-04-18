import os
import re
import time
import threading
from watchdog.events import FileSystemEventHandler
from core.event_system import events


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, controller, folder, tmdb_id, task_id=None, media_name=None, media_year=None):
        self.controller = controller
        self.folder = os.path.normpath(os.path.abspath(folder))
        self.tmdb_id = tmdb_id
        self.task_id = task_id
        self.media_name = media_name
        self.media_year = media_year
        self.pending_files = {}
        self.lock = threading.Lock()

    def process_file(self, path):
        path = self._get_path_str(path)
        if not path:
            return

        try:
            abs_path = os.path.normpath(os.path.abspath(path))

            if not abs_path.lower().startswith(self.folder.lower()):
                return

            if not os.path.exists(path):
                return

            try:
                s1 = os.path.getsize(path)
                time.sleep(2)
                s2 = os.path.getsize(path)
                if s1 != s2 or s2 == 0:
                    return
                size = s2
            except OSError:
                return

            ext = path.lower()
            is_video = ext.endswith((".mp4", ".mkv"))
            is_srt = ext.endswith(".srt")

            if is_video:
                if size < 5000000:
                    return
            elif is_srt:
                if size < 100:
                    return
            else:
                return

            if is_video and self.controller.config.get("sub_only"):
                return
            if is_srt:
                if self.controller.config.get("video_only"):
                    return
                if not self.controller.config.get("sub_only"):
                    events.emit("log", f"FILE HANDLER: Subtitle downloaded for {os.path.basename(path)}")
                    return

            fname = os.path.basename(path)

            try:
                dir_files = os.listdir(os.path.dirname(path))
                temp_exts = (".crdownload", ".part", ".tmp")
                if any(
                    f.startswith(fname) and f.lower().endswith(temp_exts)
                    for f in dir_files
                ):
                    return
            except OSError:
                return

            match = re.search(r"S(\d+)\s*E(\d+)", fname, re.IGNORECASE)

            name = self.media_name
            year = self.media_year

            if match:
                s_num, e_num = match.group(1), match.group(2)
                task_id = f"{self.tmdb_id}_S{s_num.zfill(2)}E{e_num.zfill(2)}"

                if (is_video or is_srt) and name and year:
                    from core.utils import sanitize_path

                    clean_name = sanitize_path(str(name))
                    new_fname = f"{clean_name} ({year}) S{int(s_num)} E{int(e_num)}{os.path.splitext(fname)[1]}"
                    new_path = os.path.join(os.path.dirname(path), new_fname)
                    if path != new_path and not os.path.exists(new_path):
                        try:
                            os.rename(path, new_path)
                            path = new_path
                            fname = new_fname
                        except OSError:
                            pass
            else:
                task_id = self.task_id or f"MOVIE_{self.tmdb_id}"
                if (is_video or is_srt) and name and year:
                    from core.utils import sanitize_path

                    new_fname = f"{sanitize_path(str(name))} ({year}){os.path.splitext(fname)[1]}"
                    new_path = os.path.join(os.path.dirname(path), new_fname)
                    if path != new_path and not os.path.exists(new_path):
                        try:
                            os.rename(path, new_path)
                            path = new_path
                            fname = new_fname
                        except OSError:
                            pass

            events.emit("task_status_update", task_id, "FINISHED")
            events.emit("file_processed", task_id, path)
        except Exception as e:
            events.emit("log", f"FILE HANDLER CRITICAL ERROR: {e}")

    def debounce_process(self, path):
        with self.lock:
            if path in self.pending_files:
                self.pending_files[path].cancel()

            timer = threading.Timer(3.0, self.process_file, args=[path])
            self.pending_files[path] = timer
            timer.start()

    def _get_path_str(self, path):
        if isinstance(path, str):
            return path
        try:
            return bytes(path).decode("utf-8", "ignore")
        except (UnicodeDecodeError, TypeError):
            return ""

    def on_moved(self, event):
        src_path = self._get_path_str(event.src_path)
        dest_path = self._get_path_str(event.dest_path)

        temp_exts = (".crdownload", ".part", ".tmp")
        if not event.is_directory and any(
            src_path.lower().endswith(ext) for ext in temp_exts
        ):
            if dest_path:
                self.debounce_process(dest_path)

    def on_created(self, event):
        path = self._get_path_str(event.src_path)
        if not event.is_directory and path:
            temp_exts = (".crdownload", ".part", ".tmp")
            if not any(path.lower().endswith(ext) for ext in temp_exts):
                self.debounce_process(path)
