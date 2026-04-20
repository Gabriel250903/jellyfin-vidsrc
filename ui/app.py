import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import time
import os
import sys
import re
import queue
import asyncio
import aiohttp
import webbrowser

VERSION = "1.0.0"
REPO = "Gabriel250903/jellyfin-vidsrc"

from core.utils import sanitize_path
from core.queue_manager import DownloadQueueManager
from core.download_controller import DownloadController
from core.event_system import events
from core.config_manager import config
from api.jellyfin_api import JellyfinAPI
from api.tmdb_api import TMDBAPI
from ui.jellyfin_dashboard import JellyfinDashboard
from ui.rpc_settings import RPCSettingsWindow
from ui.settings_window import SettingsWindow
from api.discord_rpc import DiscordRPCManager
from ui.components.item_card import ItemCard
from ui.components.sidebar_mixin import SidebarMixin
from ui.components.main_view_mixin import MainViewMixin


class VidSrcJellyfin(SidebarMixin, MainViewMixin, ctk.CTk):
    def __init__(self):
        ctk.CTk.__init__(self)

        self.title("VidSrc Jellyfin")
        self.geometry("1350x1050")
        self.minsize(1000, 800)
        ctk.set_appearance_mode("dark")

        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.loop_thread.start()

        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.current_speed = "0.0 MB/s"
        self.current_status = "IDLE"
        self.eta_text = "ETA: --:--"
        self.season_data = {}

        self.history = config.get("history")
        self.tmdb_api_key = config.get("api_key")
        self.discord_webhook = config.get("discord_webhook")
        self.jellyfin_url = config.get("jellyfin_url")
        self.jellyfin_api_key = config.get("jellyfin_api_key")
        self.show_path = config.get("show_path")
        self.movie_path = config.get("movie_path")
        self.rpc_enabled = config.get("rpc_enabled")
        self.rpc_client_id = config.get("rpc_client_id")
        self.rpc_target_user = config.get("rpc_target_user")
        self.rpc_show_time = config.get("rpc_show_time")
        self.rpc_show_server = config.get("rpc_show_server")
        self.jellyfin_managed_user = config.get("jellyfin_managed_user")

        self.active_tasks = {}
        self.selection_map = {}
        self.selected_tid = None
        self.selected_name = None
        self.selected_year = None
        self.selected_poster = None
        self.current_accent = "Blue"
        self.last_jelly_check = 0
        self.last_jelly_sessions = {}
        self.jellyfin_free_gb = 9999
        self.local_free_gb = 9999
        self.missing_links = []
        self.current_poster_ptr = None

        self._last_vals = {}
        self._last_discover_data = None
        self._last_search_data = None

        self.discover_cards = []
        self.search_cards = []

        self.tmdb_api = TMDBAPI(self)
        self.jellyfin_api = JellyfinAPI(self)

        self.queue_manager = DownloadQueueManager()
        self.controller = DownloadController(
            app=self,
            tmdb_api=self.tmdb_api,
            jellyfin_api=self.jellyfin_api,
            queue_manager=self.queue_manager,
            config=config.config,
        )
        self.queue_manager.controller = self.controller
        self.jelly_dashboard = None
        self.last_missing_episodes = None
        self.rpc_settings_window = None
        self.settings_window = None

        self.grid_columnconfigure(0, minsize=350)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_main_view()
        self.load_settings()

        self.discord_rpc = DiscordRPCManager(self)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_event_handlers()

        self.after(0, lambda: self.state("zoomed"))
        self.after(2000, lambda: self.run_async(self.check_for_updates()))
        self.after(3000, lambda: self.jellyfin_api.start_websocket(self.loop))

    def get_config(self):
        return config.config

    def setup_event_handlers(self):
        events.subscribe("log", self.log)
        events.subscribe("task_status_update", self.update_task_status)
        events.subscribe("task_added", self.add_task_ui)
        events.subscribe("speed_update", self._update_speed_ui)
        events.subscribe("status_update", self._update_status_ui)
        events.subscribe("queue_size_update", self._update_queue_ui)
        events.subscribe("eta_update", self._update_eta_ui)
        events.subscribe("show_missing_links", self.show_missing_links)
        events.subscribe("clear_tasks_ui", self.clear_finished_tasks_ui)
        events.subscribe("local_storage_update", self._update_local_storage_ui)
        events.subscribe("process_finished", self._on_process_finished)

        events.subscribe(
            "search_started", lambda: self.after(0, self.show_search_loading)
        )
        events.subscribe(
            "results_rendered",
            lambda r, c, p: self.after(0, lambda: self.render_results(r, c, p)),
        )
        events.subscribe(
            "mode_change_request",
            lambda m: self.after(0, lambda: self._handle_mode_change_request(m)),
        )
        events.subscribe(
            "season_data_loaded",
            lambda d: self.after(0, lambda: self._handle_season_data_loaded(d)),
        )
        events.subscribe(
            "jellyfin_status_update",
            lambda d: self.after(0, lambda: self._handle_jellyfin_status_update(d)),
        )
        events.subscribe(
            "jellyfin_storage_update",
            lambda d: self.after(0, lambda: self._handle_jellyfin_storage_update(d)),
        )
        events.subscribe(
            "jellyfin_sessions_update",
            lambda d: self.after(0, lambda: self._handle_jellyfin_sessions_update(d)),
        )
        events.subscribe(
            "jellyfin_streams_count",
            lambda c: self.after(0, lambda: self._handle_jellyfin_streams_count(c)),
        )
        events.subscribe(
            "api_callback",
            lambda cb, *args, **kwargs: self.after(0, lambda: cb(*args, **kwargs)),
        )
        events.subscribe(
            "show_info", lambda h, m: self.after(0, lambda: messagebox.showinfo(h, m))
        )
        events.subscribe(
            "show_error", lambda h, m: self.after(0, lambda: messagebox.showerror(h, m))
        )
        events.subscribe(
            "config_updated",
            lambda k, v: self.after(0, lambda: self._on_config_updated(k, v)),
        )

    def log(self, msg):
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
        self.after(0, lambda: self._update_log_box(formatted_msg))

    def _update_log_box(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg)
        total_lines = int(self.log_box.index("end-1c").split(".")[0])
        if total_lines > 500:
            self.log_box.delete("1.0", f"{total_lines - 500}.0")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _on_config_updated(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)

        if key == "show_jellyfin":
            self.toggle_jellyfin_ui()
        elif key == "history":
            self.render_history()

    def _handle_mode_change_request(self, mode):
        self.after(0, lambda: self.mode_switch.set(mode))

    def _handle_season_data_loaded(self, data):
        self.season_data = data
        if self.season_data:
            max_s = max(self.season_data.keys())
            self.after(
                0,
                lambda: (
                    self.end_season.delete(0, "end"),
                    self.end_season.insert(0, str(max_s)),
                ),
            )

    def _handle_jellyfin_status_update(self, data):
        status = data.get("status")
        version = data.get("version", "?")
        if status == "Online":
            self.after(
                0,
                lambda: self.lbl_jelly_info.configure(
                    text=f"Status: Online ({version})",
                    text_color="#2ecc71",
                ),
            )
        else:
            self.after(
                0,
                lambda: self.lbl_jelly_info.configure(
                    text="Status: Offline", text_color="#e74c3c"
                ),
            )

    def _handle_jellyfin_storage_update(self, data):
        free_gb = data.get("free_gb")
        percent = data.get("percent")
        self.jellyfin_free_gb = free_gb
        self.after(
            0,
            lambda: (
                self.lbl_storage_info.configure(text=f"Storage: {free_gb:.1f} GB Free"),
                self.storage_prog.set(percent),
            ),
        )

    def _handle_jellyfin_sessions_update(self, curr_sessions):
        for sid, info in curr_sessions.items():
            if sid not in self.last_jelly_sessions:
                self.log(
                    f"JELLYFIN: {info['user']} started watching '{info['title']}' on {info['client']}"
                )
        self.last_jelly_sessions = curr_sessions

    def _handle_jellyfin_streams_count(self, count):
        self.after(
            0,
            lambda: self.lbl_jelly_streams.configure(text=f"Active Streams: {count}"),
        )

    def _update_speed_ui(self, speed):
        self.current_speed = speed
        self.after(
            0, lambda: self._safe_configure(self.lbl_speed, "text", f"Speed: {speed}")
        )

    def _update_status_ui(self, status):
        self.current_status = status
        self.after(
            0,
            lambda: self._safe_configure(self.lbl_status, "text", f"STATUS: {status}"),
        )

    def _update_queue_ui(self, size):
        self.after(
            0, lambda: self._safe_configure(self.lbl_queue, "text", f"Queue: {size}")
        )

    def _update_eta_ui(self, eta):
        self.eta_text = eta
        self.after(0, lambda: self._safe_configure(self.lbl_eta, "text", eta))

    def _update_local_storage_ui(self, free_gb):
        self.local_free_gb = free_gb

    def _on_process_finished(self):
        self.after(0, lambda: self.btn_run.configure(state="normal"))

    def _safe_configure(self, widget, key, val):
        cache_key = f"{id(widget)}_{key}"
        if self._last_vals.get(cache_key) != val:
            widget.configure(**{key: val})
            self._last_vals[cache_key] = val

    def run_async(self, coro, callback=None):
        def _task_done(fut):
            try:
                res = fut.result()
                if callback is not None:
                    cb = callback
                    self.after(0, lambda: cb(res))
            except Exception as e:
                self.log(f"ASYNC ERROR: {e}")

        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        fut.add_done_callback(_task_done)
        return fut

    async def check_for_updates(self):
        try:
            async with aiohttp.ClientSession(trust_env=False) as session:
                url = f"https://api.github.com/repos/{REPO}/releases/latest"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        latest_version = data.get("tag_name", "").replace("v", "")
                        if latest_version and latest_version != VERSION:
                            html_url = data.get("html_url")
                            is_frozen = getattr(sys, "frozen", False)
                            exe_asset = next(
                                (
                                    a
                                    for a in data.get("assets", [])
                                    if a["name"].endswith(".exe")
                                ),
                                None,
                            )

                            if is_frozen and exe_asset:
                                self.log(
                                    f"Updater: Downloading v{latest_version} in background..."
                                )
                                download_url = exe_asset["browser_download_url"]
                                temp_exe = os.path.join(
                                    os.environ.get("TEMP", "."),
                                    "jellyfin-vidsrc-update.exe",
                                )

                                async with session.get(download_url) as file_resp:
                                    if file_resp.status == 200:
                                        with open(temp_exe, "wb") as f:
                                            while True:
                                                chunk = await file_resp.content.read(
                                                    1024 * 1024
                                                )
                                                if not chunk:
                                                    break
                                                f.write(chunk)
                                        self.after(
                                            0,
                                            lambda: self._show_restart_button(
                                                temp_exe, latest_version
                                            ),
                                        )
                                    else:
                                        self.after(
                                            0,
                                            lambda: self._show_update_dialog(
                                                latest_version, html_url
                                            ),
                                        )
                            else:
                                self.after(
                                    0,
                                    lambda: self._show_update_dialog(
                                        latest_version, html_url
                                    ),
                                )
        except Exception as e:
            self.log(f"Update check failed: {e}")

    def _show_restart_button(self, temp_exe_path, latest_version):
        self.btn_update = ctk.CTkButton(
            self.status_bar,
            text=f"RESTART TO UPDATE (v{latest_version})",
            font=("Segoe UI", 10, "bold"),
            fg_color="#e67e22",
            hover_color="#d35400",
            text_color="#ffffff",
            height=20,
            command=lambda: self._apply_update(temp_exe_path),
        )
        self.btn_update.pack(side="left", padx=20)
        self.log("Updater: Ready to install.")

    def _apply_update(self, temp_exe_path):
        import subprocess

        current_exe = sys.executable
        bat_path = os.path.join(
            os.environ.get("TEMP", "."), "update_jellyfin_vidsrc.bat"
        )

        with open(bat_path, "w") as f:
            f.write("@echo off\n")
            f.write("timeout /t 2 /nobreak >nul\n")
            f.write(f'move /y "{temp_exe_path}" "{current_exe}"\n')
            f.write(f'start "" "{current_exe}"\n')
            f.write(f'del "%~f0"\n')

        subprocess.Popen(bat_path, shell=True)
        self.on_closing()
        sys.exit(0)

    def _show_update_dialog(self, latest_version, html_url):
        if messagebox.askyesno(
            "Update Available",
            f"A new version ({latest_version}) is available!\n\n"
            f"Current version: {VERSION}\n\n"
            f"Would you like to go to the download page?",
            parent=self,
        ):
            webbrowser.open(html_url)

    def on_closing(self):
        if hasattr(self, "discord_rpc") and self.discord_rpc:
            self.discord_rpc.stop()

        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(timeout=1)

        asyncio.run_coroutine_threadsafe(self.tmdb_api.close(), self.loop)
        asyncio.run_coroutine_threadsafe(self.jellyfin_api.close(), self.loop)

        self.destroy()

    def _refresh_status_uis(self):
        if self.jelly_dashboard and self.jelly_dashboard.winfo_exists():
            self.jelly_dashboard.refresh_ui()

    def update_local_storage_status(self):
        self.local_free_gb = self.controller.update_local_storage_status()

    def load_settings(self):
        self.tmdb_api_key = config.get("api_key", "")
        self.show_path = config.get("show_path", "")
        self.movie_path = config.get("movie_path", "")
        self.history = config.get("history") or []
        self.discord_webhook = config.get("discord_webhook", "")
        self.jellyfin_url = config.get("jellyfin_url", "")
        self.jellyfin_api_key = config.get("jellyfin_api_key", "")

        if hasattr(self, "quality_var"):
            self.quality_var.set(str(config.get("quality") or "1080p"))
        if hasattr(self, "video_only_var"):
            val = config.get("video_only")
            self.video_only_var.set(bool(val) if val is not None else False)
        if hasattr(self, "sub_only_var"):
            val = config.get("sub_only")
            self.sub_only_var.set(bool(val) if val is not None else False)
        if hasattr(self, "open_folder_var"):
            val = config.get("open_folder")
            self.open_folder_var.set(bool(val) if val is not None else True)
        if hasattr(self, "show_jellyfin_var"):
            val = config.get("show_jellyfin")
            self.show_jellyfin_var.set(bool(val) if val is not None else True)
        if hasattr(self, "browser_var"):
            self.browser_var.set(str(config.get("browser") or "Edge"))

        self.rpc_enabled = bool(config.get("rpc_enabled") or False)
        self.rpc_client_id = str(config.get("rpc_client_id") or "")
        self.rpc_target_user = str(config.get("rpc_target_user") or "")
        self.rpc_show_time = bool(
            config.get("rpc_show_time")
            if config.get("rpc_show_time") is not None
            else True
        )
        self.rpc_show_server = bool(
            config.get("rpc_show_server")
            if config.get("rpc_show_server") is not None
            else True
        )
        self.jellyfin_managed_user = str(config.get("jellyfin_managed_user") or "")

        self.toggle_jellyfin_ui()
        self.render_history()

    def save_settings(self):
        data = {
            "api_key": self.tmdb_api_key,
            "show_path": self.show_path,
            "movie_path": self.movie_path,
            "history": self.history,
            "quality": self.quality_var.get(),
            "discord_webhook": self.discord_webhook,
            "jellyfin_url": self.jellyfin_url,
            "jellyfin_api_key": self.jellyfin_api_key,
            "video_only": self.video_only_var.get(),
            "sub_only": self.sub_only_var.get(),
            "open_folder": self.open_folder_var.get(),
            "show_jellyfin": self.show_jellyfin_var.get(),
            "browser": self.browser_var.get(),
            "rpc_enabled": self.rpc_enabled,
            "rpc_client_id": self.rpc_client_id,
            "rpc_target_user": self.rpc_target_user,
            "rpc_show_time": self.rpc_show_time,
            "rpc_show_server": self.rpc_show_server,
            "jellyfin_managed_user": self.jellyfin_managed_user,
        }
        config.update(data)

        self.controller.config = config.config

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()


if __name__ == "__main__":
    app = VidSrcJellyfin()
    app.mainloop()
