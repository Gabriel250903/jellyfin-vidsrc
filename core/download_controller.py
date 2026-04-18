import os
import time
import re
import shutil
import threading
import aiohttp
from core.event_system import events
from core.utils import sanitize_path, notify
from core.file_handler import DownloadHandler
from watchdog.observers import Observer

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.scraper import VidSrcScraper
    from api.tmdb_api import TMDBAPI
    from api.jellyfin_api import JellyfinAPI
    from core.queue_manager import DownloadQueueManager


class DownloadController:
    def __init__(
        self,
        app,
        tmdb_api: "TMDBAPI",
        jellyfin_api: "JellyfinAPI",
        queue_manager: "DownloadQueueManager",
        config: dict,
    ):
        self.app = app
        self.tmdb_api: "TMDBAPI" = tmdb_api
        self.jellyfin_api: "JellyfinAPI" = jellyfin_api
        self.queue_manager: "DownloadQueueManager" = queue_manager
        self.config: dict = config

        self.scrapers = {}
        self.active_observers = {}

        self.stop_event = threading.Event()
        self.failed_tasks = {}
        self.current_speed = "0.0 MB/s"
        self.current_status = "IDLE"
        self.missing_links = []

        events.subscribe("file_processed", self._on_file_processed)

    def _on_file_processed(self, task_id, path):
        if self.jellyfin_api:
            self._run_sync(self.jellyfin_api.trigger_scan(path))

    @property
    def scraper(self):
        from core.scraper import VidSrcScraper

        tid = threading.get_ident()
        if tid not in self.scrapers:
            self.scrapers[tid] = VidSrcScraper(self)
        return self.scrapers[tid]

    def log(self, msg):
        events.emit("log", msg)

    def update_task_status(self, task_id, status, progress=None, ctx=None):
        events.emit("task_status_update", task_id, status, progress)
        if ctx and status in ["FINISHED", "NOT FOUND", "ALREADY FOUND"]:
            ctx["items_completed"] += 1
            self.update_eta(ctx)

    def update_eta(self, ctx):
        try:
            if (
                ctx["items_completed"] == 0
                or ctx["total_items"] <= ctx["items_completed"]
            ):
                return
            rem = (ctx["total_items"] - ctx["items_completed"]) * (
                (time.time() - ctx["batch_start_time"]) / ctx["items_completed"]
            )
            m, s = divmod(int(rem), 60)
            events.emit("eta_update", f"ETA: {m}m {s}s")
        except:
            pass

    def stop_process(self):
        self.stop_event.set()
        self.log("STOP: Process killed by user. Queue will halt.")
        self.current_status = "IDLE"
        events.emit("status_update", "IDLE")

        for tid, scraper in list(self.scrapers.items()):
            scraper.quit_driver()

        for tid, obs in list(self.active_observers.items()):
            try:
                obs.stop()
            except:
                pass

    def _run_sync(self, coro):
        import asyncio

        try:
            return asyncio.run(coro)
        except Exception as e:
            self.log(f"ASYNC RUN ERROR: {e}")
            return None

    def process_queued_item(self, task):
        tid = threading.get_ident()
        name, year, tid_movie, poster = (
            sanitize_path(task["name"]),
            task["year"],
            task["tid"],
            task["poster"],
        )
        mode = task["mode"]
        selection_map = task["selection_map"]

        self.log(f"CONTROLLER: Processing '{name} ({year})' from queue.")

        ctx = {
            "batch_start_time": time.time(),
            "items_completed": 0,
            "total_items": 0,
            "failed_tasks": [],
        }
        self.failed_tasks[tid] = ctx["failed_tasks"]

        self.current_status = "DOWNLOADING"
        events.emit("status_update", "DOWNLOADING")
        events.emit("clear_tasks_ui")

        season_data = task["season_data"]

        if mode == "Movie":
            ctx["total_items"] = 1
        else:
            if selection_map:
                ctx["total_items"] = sum(len(eps) for eps in selection_map.values())
            else:
                sf, st = int(task["start_season"] or 1), int(task["end_season"] or 1)
                ctx["total_items"] = sum(
                    (
                        season_data.get(str(s), 20)
                        if isinstance(season_data.get(str(s)), int)
                        else season_data.get(s, 20)
                    )
                    for s in range(sf, st + 1)
                )

        root = (
            self.config.get("show_path")
            if mode == "TV Show"
            else self.config.get("movie_path")
        )
        if not root:
            self.log("ERROR: Root path not set.")
            return

        if not os.path.exists(root):
            os.makedirs(root, exist_ok=True)

        try:
            main_folder = os.path.join(root, f"{name} ({year})")
            if not os.path.exists(main_folder):
                os.makedirs(main_folder, exist_ok=True)

            watcher_task_id = f"MOVIE_{tid_movie}" if mode == "Movie" else "MOVIE"

            observer = Observer()
            self.active_observers[tid] = observer
            observer.schedule(
                DownloadHandler(
                    self,
                    main_folder,
                    tmdb_id=tid_movie,
                    task_id=watcher_task_id,
                    media_name=name,
                    media_year=year,
                ),
                main_folder,
                recursive=True,
            )
            observer.start()

            if self.tmdb_api:
                self._run_sync(
                    self.tmdb_api.download_metadata(
                        name, year, tid_movie, mode, main_folder
                    )
                )

            if mode == "Movie":
                if self.scraper:
                    self.scraper.trigger_downloads(
                        main_folder,
                        tid_movie,
                        "movie",
                        media_name=name,
                        quality=task["quality"],
                        sub_only=task["sub_only"],
                        video_only=task["video_only"],
                    )
                self.wait_for_done(main_folder, ctx)
                self.clean_subtitles(main_folder)
                if (
                    not self.stop_event.is_set()
                    and self.config.get("show_jellyfin")
                    and self.jellyfin_api
                ):
                    self._run_sync(self.jellyfin_api.trigger_scan(main_folder))
                    self._run_sync(
                        self.jellyfin_api.send_message(
                            "Download Complete", f"'{name} ({year})' is ready!"
                        )
                    )
            else:
                if selection_map:
                    for s in sorted(selection_map.keys()):
                        if self.stop_event.is_set():
                            break
                        folder = os.path.join(main_folder, f"Season {s}")
                        if not os.path.exists(folder):
                            os.makedirs(folder, exist_ok=True)
                        if self.scraper:
                            self.scraper.trigger_selected_episodes(
                                folder,
                                tid_movie,
                                s,
                                selection_map[s],
                                media_name=name,
                                quality=task["quality"],
                                sub_only=task["sub_only"],
                                video_only=task["video_only"],
                            )
                        self.wait_for_done(folder, ctx)
                        self.clean_subtitles(folder)
                        if (
                            not self.stop_event.is_set()
                            and self.config.get("show_jellyfin")
                            and self.jellyfin_api
                        ):
                            self._run_sync(self.jellyfin_api.trigger_scan(folder))
                            self._run_sync(
                                self.jellyfin_api.send_message(
                                    "Season Ready",
                                    f"{name} - Season {s} is now available!",
                                )
                            )
                else:
                    sf, st = int(task["start_season"] or 1), int(
                        task["end_season"] or 1
                    )
                    start_ep = int(task["resume_ep"] or 1)
                    for s in range(sf, st + 1):
                        if self.stop_event.is_set():
                            break
                        folder = os.path.join(main_folder, f"Season {s}")
                        if not os.path.exists(folder):
                            os.makedirs(folder, exist_ok=True)
                        if self.scraper:
                            self.scraper.trigger_downloads(
                                folder,
                                tid_movie,
                                "tv",
                                s,
                                season_data.get(str(s), 50),
                                start_ep if s == sf else 1,
                                media_name=name,
                                quality=task["quality"],
                                sub_only=task["sub_only"],
                                video_only=task["video_only"],
                            )
                        self.wait_for_done(folder, ctx)
                        self.clean_subtitles(folder)
                        if (
                            not self.stop_event.is_set()
                            and self.config.get("show_jellyfin")
                            and self.jellyfin_api
                        ):
                            self._run_sync(self.jellyfin_api.trigger_scan(folder))
                            self._run_sync(
                                self.jellyfin_api.send_message(
                                    "Season Ready",
                                    f"{name} - Season {s} is now available!",
                                )
                            )

            retry_attempt = 0
            max_retries = 3

            failed_list = self.failed_tasks.get(tid, [])
            while (
                failed_list
                and retry_attempt < max_retries
                and not self.stop_event.is_set()
            ):
                retry_attempt += 1
                backoff_time = 30 * (2 ** (retry_attempt - 1))

                self.log(
                    f"RETRY: Attempt {retry_attempt}/{max_retries} for {len(failed_list)} failed items. "
                    f"Waiting {backoff_time}s (Backoff)..."
                )

                for _ in range(backoff_time):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)

                if self.stop_event.is_set():
                    break

                current_batch = list(failed_list)
                failed_list.clear()

                for f_task in current_batch:
                    if self.stop_event.is_set():
                        break

                    if len(f_task) == 8:
                        f, t, m, s, e, q, so, vo = f_task
                    else:
                        f, t, m, s, e = f_task
                        q, so, vo = (
                            task["quality"],
                            task["sub_only"],
                            task["video_only"],
                        )

                    already_done = False
                    if os.path.exists(f):
                        ep_pattern = (
                            rf"[sS]0*{s}[eE]0*{e}(?!\d)|0*{s}x0*{e}(?!\d)|[eE]0*{e}(?!\d)"
                            if s
                            else None
                        )
                        for file in os.listdir(f):
                            if (
                                m == "movie" and file.lower().endswith((".mp4", ".mkv"))
                            ) or (
                                ep_pattern
                                and re.search(ep_pattern, file, re.I)
                                and file.lower().endswith((".mp4", ".mkv"))
                            ):
                                already_done = True
                                break

                    if already_done:
                        self.update_task_status(
                            f"S{str(s).zfill(2)}E{str(e).zfill(2)}" if s else "MOVIE",
                            "FINISHED",
                            ctx=ctx,
                        )
                        continue

                    if self.scraper:
                        self.scraper._process_task(
                            f,
                            t,
                            m,
                            s,
                            e,
                            media_name=name,
                            quality=q,
                            sub_only=so,
                            video_only=vo,
                            is_retry=True,
                        )
                    self.wait_for_done(f, ctx)
                    self.clean_subtitles(f)

            if not self.stop_event.is_set():
                if self.cleanup_empty_folders(main_folder):
                    self.log(
                        f"CONTROLLER: Cleaned up empty folder for '{name} ({year})' as no media was found."
                    )
                else:
                    notify("Download Complete", f"All tasks for {name} have finished.")
                    self._run_sync(self.send_discord_notification(name, year, poster))
                    if self.jellyfin_api:
                        self._run_sync(self.jellyfin_api.trigger_scan(main_folder))
                    if self.config.get("open_folder"):
                        try:
                            os.startfile(main_folder)
                        except:
                            pass

        finally:
            if self.scraper:
                self.scraper.quit_driver()

            events.emit("process_finished")
            self.current_status = "IDLE"
            events.emit("status_update", "IDLE")

            observer.stop()
            observer.join()
            if tid in self.active_observers:
                del self.active_observers[tid]
            if tid in self.failed_tasks:
                del self.failed_tasks[tid]

    def wait_for_done(self, folder, ctx):
        folder_name = os.path.basename(folder)
        self.log(f"CONTROLLER: Monitoring {folder_name} for active downloads...")

        start_wait = time.time()
        found_any = False
        temp_exts = (".crdownload", ".part", ".tmp")

        while not self.stop_event.is_set() and time.time() - start_wait < 30:
            try:
                current_files = []
                for _ in range(3):
                    current_files = os.listdir(folder)
                    temp_files = [
                        f for f in current_files if f.lower().endswith(temp_exts)
                    ]
                    if temp_files:
                        break
                    time.sleep(0.5)

                if temp_files:
                    self.log(
                        f"CONTROLLER: Detected active download(s): {', '.join(temp_files)}"
                    )
                    found_any = True
                    break
            except Exception as e:
                self.log(f"CONTROLLER ERROR: Failed to list directory: {e}")

            time.sleep(1)

        if not found_any:
            recent_media = False
            try:
                for f in os.listdir(folder):
                    if f.lower().endswith((".mp4", ".mkv")):
                        f_path = os.path.join(folder, f)
                        if time.time() - os.path.getmtime(f_path) < 60:
                            recent_media = True
                            break
            except:
                pass

            if recent_media:
                self.log(
                    f"CONTROLLER: No temp files, but recently finished media found in {folder_name}."
                )
            else:
                self.log(
                    f"CONTROLLER: No active downloads detected in {folder_name} after 30s."
                )
            return

        consecutive_empty = 0
        while not self.stop_event.is_set():
            try:
                temp_files = [
                    f for f in os.listdir(folder) if f.lower().endswith(temp_exts)
                ]

                if not temp_files:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    self.log(
                        f"CONTROLLER: No temp files seen ({consecutive_empty}/3), verifying..."
                    )
                    time.sleep(3)
                    continue

                consecutive_empty = 0

                if self.scraper:
                    stats = self.scraper.get_browser_downloads()
                    if stats:
                        for task_id, filename in list(
                            self.scraper.task_file_map.items()
                        ):
                            match = next(
                                (s for s in stats if filename in s.get("fileName", "")),
                                None,
                            )
                            if match:
                                progress = match.get("percent", 0) / 100.0
                                if match.get("state") == "COMPLETE":
                                    self.update_task_status(
                                        task_id, "FINISHED", ctx=ctx
                                    )
                                    if task_id in self.scraper.task_file_map:
                                        del self.scraper.task_file_map[task_id]
                                elif match.get("state") == "IN_PROGRESS":
                                    self.update_task_status(
                                        task_id, "DOWNLOADING", progress, ctx=ctx
                                    )
                                    eta_time = match.get("eta")
                                    if eta_time and eta_time > 0:
                                        pass

                self.calc_speed(folder)
            except Exception as e:
                self.log(f"CONTROLLER ERROR in wait loop: {e}")

            time.sleep(2)

        self.log(f"CONTROLLER: Finished waiting for {folder_name}.")

    def calc_speed(self, folder):
        try:
            temp_exts = (".crdownload", ".part", ".tmp")
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(temp_exts)
            ]
            if not files:
                self.current_speed = "0.0 MB/s"
                events.emit("speed_update", self.current_speed)
                return

            try:
                s1 = sum(os.path.getsize(f) for f in files)
                time.sleep(0.8)
                s2 = sum(os.path.getsize(f) for f in files)

                speed_mb = (s2 - s1) / (0.8 * 1024 * 1024)
                if speed_mb < 0:
                    speed_mb = 0

                self.current_speed = f"{speed_mb:.1f} MB/s"
                events.emit("speed_update", self.current_speed)
            except (OSError, FileNotFoundError):
                pass
        except Exception:
            pass

    def clean_subtitles(self, folder):
        try:
            files = os.listdir(folder)
            videos = [f for f in files if f.lower().endswith((".mp4", ".mkv"))]
            subs = [
                f
                for f in files
                if f.lower().endswith(".srt") and ".en.srt" not in f.lower()
            ]
            if not videos:
                return
            for v in videos:
                v_name = os.path.splitext(v)[0]
                v_match = re.search(r"S(\d+)\s*E(\d+)", v, re.IGNORECASE)
                for s in subs:
                    s_path = os.path.join(folder, s)
                    if not os.path.exists(s_path):
                        continue
                    target_path = os.path.join(folder, f"{v_name}.en.srt")
                    if v_match:
                        s_match = re.search(r"S(\d+)\s*E(\d+)", s, re.IGNORECASE)
                        if s_match and v_match.groups() == s_match.groups():
                            if not os.path.exists(target_path):
                                os.rename(s_path, target_path)
                                break
                    else:
                        if not re.search(r"S(\d+)\s*E(\d+)", s, re.IGNORECASE):
                            if not os.path.exists(target_path):
                                os.rename(s_path, target_path)
                                break
        except Exception as e:
            self.log(f"CLEANER ERROR: {e}")

    def cleanup_empty_folders(self, folder_path):
        try:
            if not os.path.exists(folder_path):
                return False

            has_media = False
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith((".mp4", ".mkv")):
                        has_media = True
                        break
                if has_media:
                    break

            if not has_media:
                shutil.rmtree(folder_path)
                return True
        except Exception as e:
            self.log(f"CLEANUP ERROR: {e}")
        return False

    async def send_discord_notification(self, name, year, poster_path):
        webhook = self.config.get("discord_webhook")
        if not webhook:
            return
        try:
            embed = {
                "title": f"Download Complete: {name} ({year})",
                "color": 3066993,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if poster_path:
                embed["image"] = {
                    "url": f"https://image.tmdb.org/t/p/w500{poster_path}"
                }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook, json={"embeds": [embed]}) as res:
                    pass
        except:
            pass

    def update_local_storage_status(self):
        try:
            root = (
                self.config.get("show_path")
                if self.config.get("mode") == "TV Show"
                else self.config.get("movie_path")
            )
            if not root:
                return 0

            # Find the closest existing parent folder to check disk usage without creating the path
            check_path = os.path.abspath(root)
            while not os.path.exists(check_path):
                parent = os.path.dirname(check_path)
                if parent == check_path:
                    break
                check_path = parent

            if os.path.exists(check_path):
                usage = shutil.disk_usage(check_path)
                free_gb = usage.free / (1024**3)
                events.emit("local_storage_update", free_gb)
                return free_gb
            else:
                return 0
        except:
            return 0
