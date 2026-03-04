import os
import re
import time
from watchdog.events import FileSystemEventHandler


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, app, media_name=None, media_year=None):
        self.app = app
        self.media_name = media_name
        self.media_year = media_year

    def process_file(self, path):
        try:
            target = getattr(self.app, "current_target_folder", None)
            if not target:
                return

            abs_target = os.path.normpath(os.path.abspath(target)).lower()
            abs_path = os.path.normpath(os.path.abspath(path)).lower()

            if not abs_path.startswith(abs_target):
                return

            if not os.path.exists(path):
                return

            ext = path.lower()
            size = os.path.getsize(path)
            is_video = ext.endswith((".mp4", ".mkv"))
            is_srt = ext.endswith(".srt")

            if is_video:
                if size < 1000000:
                    return
            elif is_srt:
                if size < 100:
                    return
            else:
                return

            if is_srt and not self.app.sub_only_var.get():
                return

            fname = os.path.basename(path)
            if any(
                f.startswith(fname) and f.endswith(".crdownload")
                for f in os.listdir(os.path.dirname(path))
            ):
                return

            match = re.search(r"S(\d+)\s*E(\d+)", fname, re.IGNORECASE)

            name = (
                self.media_name
                if self.media_name
                else getattr(self.app, "selected_name", None)
            )
            year = (
                self.media_year
                if self.media_year
                else getattr(self.app, "selected_year", None)
            )

            if match:
                s_num, e_num = match.group(1), match.group(2)
                task_id = f"S{s_num.zfill(2)}E{e_num.zfill(2)}"

                if is_video and name and year:
                    from core.utils import sanitize_path

                    clean_name = sanitize_path(name)
                    new_fname = f"{clean_name} ({year}) S{int(s_num)} E{int(e_num)}{os.path.splitext(fname)[1]}"
                    new_path = os.path.join(os.path.dirname(path), new_fname)
                    if path != new_path and not os.path.exists(new_path):
                        try:
                            os.rename(path, new_path)
                            path = new_path
                            fname = new_fname
                        except:
                            pass
            else:
                task_id = "MOVIE"
                if is_video and name and year:
                    from core.utils import sanitize_path

                    new_fname = (
                        f"{sanitize_path(name)} ({year}){os.path.splitext(fname)[1]}"
                    )
                    new_path = os.path.join(os.path.dirname(path), new_fname)
                    if path != new_path and not os.path.exists(new_path):
                        try:
                            os.rename(path, new_path)
                            path = new_path
                            fname = new_fname
                        except:
                            pass

            self.app.update_task_status(task_id, "FINISHED")
        except:
            pass

    def on_moved(self, event):
        if not event.is_directory and event.src_path.endswith(".crdownload"):
            time.sleep(1)
            self.process_file(event.dest_path)

    def on_created(self, event):
        if not event.is_directory:
            self.process_file(event.src_path)
