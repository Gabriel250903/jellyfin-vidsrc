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


class ItemCard(ctk.CTkFrame):
    def __init__(self, container, app):
        super().__init__(
            container,
            fg_color=("#fdfdfd", "#1c1c1c"),
            corner_radius=0,
            border_width=0,
            width=180,
        )
        self.app = app

        self.img_label = ctk.CTkLabel(
            self,
            text="No Poster",
            width=160,
            height=240,
            fg_color=("#eeeeee", "#252525"),
            corner_radius=0,
        )
        self.img_label.pack(pady=(10, 5), padx=10)

        self.rating_lbl = ctk.CTkLabel(
            self.img_label,
            text="",
            font=("Segoe UI", 10, "bold"),
            text_color="white",
            corner_radius=0,
            width=40,
            height=20,
        )

        self.info_f = ctk.CTkFrame(self, fg_color="transparent")
        self.info_f.pack(fill="x", padx=12, pady=(0, 5))

        self.title_lbl = ctk.CTkLabel(
            self.info_f,
            text="",
            font=("Segoe UI", 13, "bold"),
            wraplength=150,
            anchor="w",
            justify="left",
        )
        self.title_lbl.pack(fill="x")

        self.sub_lbl = ctk.CTkLabel(
            self.info_f, text="", font=("Segoe UI", 11), text_color="#3498db"
        )
        self.sub_lbl.pack(side="left")

        self.btn_select = ctk.CTkButton(
            self,
            text="SELECT",
            height=32,
            font=("Segoe UI", 12, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            corner_radius=0,
        )
        self.btn_select.pack(fill="x", padx=10, pady=(5, 12))

    def update_data(self, item, cat, preloaded_poster=None):
        name = item.get("name") if cat == "tv" else item.get("title")
        year = (item.get("first_air_date") or item.get("release_date") or "0000")[:4]
        tid, p_path = item.get("id"), item.get("poster_path")
        rating = item.get("vote_average", 0)

        ctk_poster = None
        if preloaded_poster:
            ctk_poster = ctk.CTkImage(
                light_image=preloaded_poster,
                dark_image=preloaded_poster,
                size=(160, 240),
            )

        self.img_label.configure(
            image=ctk_poster,
            text="No Poster" if not ctk_poster else "",
            fg_color=("#eeeeee", "#252525") if not ctk_poster else "transparent",
        )

        if not ctk_poster and p_path:
            self.app.run_async(
                self.app.tmdb_api.get_poster_image(p_path, size=(160, 240)),
                lambda img: self.app.after(
                    0,
                    lambda: (
                        self.img_label.configure(
                            image=ctk.CTkImage(img, img, (160, 240)),
                            text="",
                            fg_color="transparent",
                        )
                        if img
                        else None
                    ),
                ),
            )

        if rating > 0:
            badge_color = (
                "#2ecc71" if rating >= 7 else "#f1c40f" if rating >= 5 else "#e74c3c"
            )
            self.rating_lbl.configure(text=f"★ {rating:.1f}", fg_color=badge_color)
            self.rating_lbl.place(relx=0.92, rely=0.08, anchor="ne")
        else:
            self.rating_lbl.place_forget()

        display_name = name if len(name) < 40 else name[:37] + "..."
        self.title_lbl.configure(text=display_name)

        self.sub_lbl.configure(
            text=f"{year} • {cat.replace('movie', 'Movie').replace('tv', 'TV')}"
        )

        self.btn_select.configure(
            command=lambda: self.app.select_title(name, year, tid, p_path, cat=cat)
        )


class VidSrcJellyfin(ctk.CTk):
    def __init__(self):
        super().__init__()

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

    def show_search_loading(self):
        for w in self.results_container.winfo_children():
            getattr(w, "grid_remove", lambda: None)()
        self.results_container.pack(
            fill="both", expand=True, padx=10, before=self.exec_frame
        )
        self.tabview.set("Search")

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

    def _handle_api_callback(self, callback, *args, **kwargs):
        self.after(0, lambda: callback(*args, **kwargs))

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

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self,
            width=350,
            corner_radius=0,
            fg_color=("#ebebeb", "#111111"),
            border_width=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(7, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="VidSrc Jellyfin",
            font=("Segoe UI", 22, "bold"),
            text_color="#3498db",
        )
        self.logo_label.grid(row=0, column=0, pady=(30, 15))

        self.mode_switch = ctk.CTkSegmentedButton(
            self.sidebar,
            values=["TV Show", "Movie"],
            command=self.on_mode_change,
            height=35,
            selected_color="#3498db",
        )
        self.mode_switch.grid(row=3, column=0, pady=15, padx=20, sticky="ew")
        self.mode_switch.set("TV Show")

        self.poster_label = ctk.CTkLabel(
            self.sidebar,
            text="No Preview",
            width=240,
            height=340,
            fg_color=("#d1d1d1", "#1a1a1a"),
            corner_radius=12,
        )
        self.poster_label.grid(row=4, column=0, pady=15)

        history_header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        history_header.grid(row=5, column=0, sticky="ew", padx=20, pady=(10, 0))
        ctk.CTkLabel(
            history_header, text="HISTORY", font=("Segoe UI", 11, "bold")
        ).pack(side="left")
        self.btn_clear_history = ctk.CTkButton(
            history_header,
            text="CLEAR",
            width=50,
            height=20,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.clear_history,
        )
        self.btn_clear_history.pack(side="right")

        self.history_search = ctk.CTkEntry(
            self.sidebar,
            placeholder_text="Filter history...",
            height=25,
            font=("Segoe UI", 11),
        )
        self.history_search.grid(row=6, column=0, sticky="ew", padx=20, pady=(5, 0))
        self.history_search.bind("<KeyRelease>", lambda e: self.render_history())

        self.history_frame = ctk.CTkScrollableFrame(
            self.sidebar, height=180, fg_color=("#f5f5f5", "#0a0a0a")
        )
        self.history_frame.grid(row=7, column=0, sticky="nsew", padx=15, pady=5)

        self.btn_queue = ctk.CTkButton(
            self.sidebar,
            text="⏳ PENDING QUEUE",
            font=("Segoe UI", 12, "bold"),
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_queue_window,
        )
        self.btn_queue.grid(row=8, column=0, sticky="ew", padx=20)

        self.btn_jelly_dashboard = ctk.CTkButton(
            self.sidebar,
            text="📺 JELLYFIN DASHBOARD",
            font=("Segoe UI", 12, "bold"),
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_jellyfin_dashboard,
        )
        self.btn_jelly_dashboard.grid(
            row=9, column=0, sticky="ew", padx=20, pady=(10, 15)
        )

        self.lbl_jelly_info = ctk.CTkLabel(self, text="Status: Disconnected")
        self.lbl_jelly_streams = ctk.CTkLabel(self, text="Active Streams: 0")
        self.lbl_storage_info = ctk.CTkLabel(self, text="Storage: -- GB Free")
        self.storage_prog = ctk.CTkProgressBar(self, progress_color="#3498db")

        self.bottom_sidebar = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.bottom_sidebar.grid(row=10, column=0, sticky="ew", pady=10)
        self.btn_rpc_settings = ctk.CTkButton(
            self.bottom_sidebar,
            text="🎮 Discord RPC",
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_rpc_settings,
        )
        self.btn_rpc_settings.pack(fill="x", padx=20, pady=5)
        self.btn_choose_root = ctk.CTkButton(
            self.bottom_sidebar,
            text="📁 Library Path",
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.choose_root,
        )
        self.btn_choose_root.pack(fill="x", padx=20, pady=5)
        self.btn_settings = ctk.CTkButton(
            self.bottom_sidebar,
            text="⚙ Settings",
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_settings,
        )
        self.btn_settings.pack(fill="x", padx=20, pady=5)

    def setup_main_view(self):
        self.main_view = ctk.CTkFrame(
            self, fg_color=("#ffffff", "#1a1a1a"), corner_radius=0
        )
        self.main_view.grid(row=0, column=1, sticky="nsew")

        self.tabview = ctk.CTkTabview(
            self.main_view,
            fg_color="transparent",
            segmented_button_selected_color="#3498db",
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_search = self.tabview.add("Search")
        self.tab_discover = self.tabview.add("Discover")
        self.tab_downloads = self.tabview.add("Downloads")

        search_f = ctk.CTkFrame(self.tab_search, fg_color="transparent")
        search_f.pack(fill="x", padx=20, pady=(10, 10))

        self.search_entry = ctk.CTkEntry(
            search_f,
            placeholder_text="Search TMDB...",
            height=35,
            font=("Segoe UI", 14),
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind(
            "<Return>",
            lambda e: self.run_async(
                self.tmdb_api.perform_search(
                    self.search_entry.get(), self.search_year.get()
                )
            ),
        )

        self.search_year = ctk.CTkEntry(
            search_f,
            placeholder_text="Year",
            width=70,
            height=35,
            font=("Segoe UI", 14),
        )
        self.search_year.pack(side="left", padx=10)

        ctk.CTkButton(
            search_f,
            text="SEARCH",
            width=100,
            height=35,
            fg_color="#3498db",
            hover_color="#2980b9",
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.run_async(
                self.tmdb_api.perform_search(
                    self.search_entry.get(), self.search_year.get()
                )
            ),
        ).pack(side="left")

        self.results_container = ctk.CTkScrollableFrame(
            self.tab_search, height=450, fg_color=("#f0f0f0", "#0a0a0a")
        )
        self.results_container.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.exec_frame = ctk.CTkFrame(
            self.tab_search, fg_color=("#f9f9f9", "#151515"), corner_radius=8
        )
        self.exec_frame.pack(fill="x", padx=10, pady=10)
        self.title_display = ctk.CTkLabel(
            self.exec_frame, text="Select Media", font=("Segoe UI", 18, "bold")
        )
        self.title_display.pack(pady=5)

        input_f = ctk.CTkFrame(self.exec_frame, fg_color="transparent")
        input_f.pack(pady=5)
        self.start_season = ctk.CTkEntry(input_f, placeholder_text="S-Start", width=60)
        self.start_season.pack(side="left", padx=5)
        self.end_season = ctk.CTkEntry(input_f, placeholder_text="S-End", width=60)
        self.end_season.pack(side="left", padx=5)
        self.resume_ep = ctk.CTkEntry(input_f, placeholder_text="Ep-Start", width=60)
        self.resume_ep.pack(side="left", padx=5)
        ctk.CTkButton(
            input_f,
            text="SELECT EPS",
            width=80,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_ep_selector,
        ).pack(side="left", padx=5)

        self.quality_var = ctk.StringVar(value=config.get("quality"))
        self.sub_only_var = ctk.BooleanVar(value=config.get("sub_only"))
        self.video_only_var = ctk.BooleanVar(value=config.get("video_only"))
        self.open_folder_var = ctk.BooleanVar(value=config.get("open_folder"))
        self.show_jellyfin_var = ctk.BooleanVar(value=config.get("show_jellyfin"))
        self.browser_var = ctk.StringVar(value=config.get("browser"))

        switches_f = ctk.CTkFrame(self.exec_frame, fg_color="transparent")
        switches_f.pack(pady=5)
        ctk.CTkSwitch(
            switches_f,
            text="Subtitles Only",
            variable=self.sub_only_var,
            progress_color="#3498db",
        ).pack(side="left", padx=10)
        ctk.CTkSwitch(
            switches_f,
            text="Videos Only",
            variable=self.video_only_var,
            progress_color="#3498db",
        ).pack(side="left", padx=10)

        self.setup_discover_tab()

        monitor_header = ctk.CTkFrame(self.tab_downloads, fg_color="transparent")
        monitor_header.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(
            monitor_header,
            text="ACTIVE TASKS",
            font=("Segoe UI", 11, "bold"),
            text_color="#3498db",
        ).pack(side="left")
        ctk.CTkButton(
            monitor_header,
            text="REMOVE FINISHED",
            width=110,
            height=22,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.clear_finished_tasks,
        ).pack(side="right")

        self.task_monitor = ctk.CTkScrollableFrame(
            self.tab_downloads, height=300, fg_color=("#f0f0f0", "#0a0a0a")
        )
        self.task_monitor.pack(fill="both", expand=True, padx=10, pady=5)

        btn_f = ctk.CTkFrame(self.tab_downloads, fg_color="transparent")
        btn_f.pack(fill="x", padx=10, pady=10)
        self.btn_run = ctk.CTkButton(
            btn_f,
            text="START PROCESS",
            fg_color="#3498db",
            hover_color="#2980b9",
            font=("Segoe UI", 14, "bold"),
            height=45,
            command=self.start_process,
        )
        self.btn_run.pack(side="left", expand=True, fill="x", padx=(0, 10))
        self.btn_stop = ctk.CTkButton(
            btn_f,
            text="STOP",
            fg_color="#e74c3c",
            width=120,
            height=45,
            command=self.stop_process,
        )
        self.btn_stop.pack(side="right")

        self.log_box = ctk.CTkTextbox(
            self.tab_downloads, height=200, font=("Consolas", 12), state="disabled"
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_bar = ctk.CTkFrame(self, height=25, fg_color=("#ebebeb", "#000"))
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.lbl_speed = ctk.CTkLabel(
            self.status_bar,
            text="0.0 MB/s",
            font=("Segoe UI", 10),
            text_color="#2ecc71",
        )
        self.lbl_speed.pack(side="left", padx=20)
        self.lbl_queue = ctk.CTkLabel(
            self.status_bar,
            text="Queue: 0",
            font=("Segoe UI", 10, "bold"),
            text_color="#9b59b6",
        )
        self.lbl_queue.pack(side="left", padx=20)
        self.lbl_eta = ctk.CTkLabel(
            self.status_bar,
            text="ETA: --:--",
            font=("Segoe UI", 10),
            text_color="#e67e22",
        )
        self.lbl_eta.pack(side="left", padx=20)
        self.lbl_status = ctk.CTkLabel(
            self.status_bar,
            text="STATUS: IDLE",
            font=("Segoe UI", 10, "bold"),
            text_color="#3498db",
        )
        self.lbl_status.pack(side="right", padx=20)

    def setup_discover_tab(self):
        self.discover_page = 1
        self.discover_total_pages = 1
        self.loading_more = False
        self.all_discover_results = []
        self.discover_cards = []

        disc_f = ctk.CTkFrame(self.tab_discover, fg_color="transparent")
        disc_f.pack(fill="both", expand=True, padx=10, pady=10)

        ctrl_f = ctk.CTkFrame(disc_f, fg_color="transparent")
        ctrl_f.pack(fill="x", pady=(0, 10))

        self.disc_type = ctk.CTkSegmentedButton(
            ctrl_f,
            values=["Trending", "Popular"],
            command=lambda v: self.refresh_discover(),
            selected_color="#3498db",
        )
        self.disc_type.pack(side="left", padx=10)
        self.disc_type.set("Trending")

        ctk.CTkButton(
            ctrl_f,
            text="Refresh",
            width=80,
            height=30,
            fg_color="#3498db",
            command=self.refresh_discover,
        ).pack(side="right", padx=10)

        self.discover_container = ctk.CTkScrollableFrame(
            disc_f, fg_color=("#f0f0f0", "#0a0a0a")
        )
        self.discover_container.pack(fill="both", expand=True)
        self.discover_container.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.lbl_loading_more = ctk.CTkLabel(
            self.discover_container,
            text="Loading more results...",
            font=("Segoe UI", 13, "italic"),
            text_color="#3498db",
        )
        self.btn_load_more = ctk.CTkButton(
            self.discover_container,
            text="LOAD MORE CONTENT",
            font=("Segoe UI", 12, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.load_more_discover,
            height=40,
        )

        self.discover_container._parent_canvas.bind(
            "<MouseWheel>", self._on_discover_scroll
        )
        self.discover_container._parent_canvas.bind(
            "<Button-4>", self._on_discover_scroll
        )
        self.discover_container._parent_canvas.bind(
            "<Button-5>", self._on_discover_scroll
        )

        self.after(1000, self.refresh_discover)
        self.after(2000, self._check_discover_scroll)

    def _check_discover_scroll(self):
        try:
            if self.tabview.get() == "Discover":
                self._on_discover_scroll()
        except:
            pass
        self.after(1000, self._check_discover_scroll)

    def _get_discover_columns(self):
        try:
            width = self.discover_container.winfo_width()
            if width < 400:
                width = 1100
            return max(1, (width - 40) // 200)
        except:
            return 5

    def _update_discover_footer(self):
        if not hasattr(self, "lbl_loading_more"):
            return
        self.lbl_loading_more.grid_forget()
        self.btn_load_more.grid_forget()

        columns = self._get_discover_columns()
        total_items = len(self.all_discover_results)
        next_row = (total_items + columns - 1) // columns if total_items > 0 else 0

        if self.loading_more:
            self.lbl_loading_more.grid(
                row=next_row, column=0, columnspan=columns, pady=30
            )
        elif self.discover_page < self.discover_total_pages:
            self.btn_load_more.grid(
                row=next_row, column=0, columnspan=columns, pady=30, padx=100
            )

    def _on_discover_scroll(self, event=None):
        if self.loading_more or self.discover_page >= self.discover_total_pages:
            return

        try:
            pos = self.discover_container._parent_canvas.yview()
            if pos[1] > 0.8:
                self.load_more_discover()
        except:
            pass

    def load_more_discover(self):
        if self.loading_more:
            return
        self.loading_more = True
        self.discover_page += 1
        self._update_discover_footer()

        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"
        if self.disc_type.get() == "Trending":
            self.run_async(
                self.tmdb_api.fetch_trending(cat, page=self.discover_page),
                self._append_discover_results,
            )
        else:
            self.run_async(
                self.tmdb_api.fetch_popular(cat, page=self.discover_page),
                self._append_discover_results,
            )

    def _append_discover_results(self, data):
        results, posters, total_pages = data
        self.discover_total_pages = total_pages
        self.all_discover_results.extend(results)
        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"

        def _ui_render():
            columns = self._get_discover_columns()
            start_idx = len(self.all_discover_results) - len(results)

            for i, item in enumerate(results):
                idx = start_idx + i
                card = ItemCard(self.discover_container, self)
                self.discover_cards.append(card)
                poster_pil = posters[i] if posters and i < len(posters) else None
                card.update_data(item, cat, poster_pil)
                card.grid(
                    row=idx // columns,
                    column=idx % columns,
                    padx=10,
                    pady=10,
                    sticky="nsew",
                )

            self.loading_more = False
            self._update_discover_footer()

        self.after(0, _ui_render)

    def refresh_discover(self):
        self.discover_page = 1
        self.all_discover_results = []
        self.loading_more = False

        for card in self.discover_cards:
            try:
                card.destroy()
            except:
                pass
        self.discover_cards = []

        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"

        for w in self.discover_container.winfo_children():
            getattr(w, "grid_remove", lambda: None)()

        if self.disc_type.get() == "Trending":
            self.run_async(
                self.tmdb_api.fetch_trending(cat), self._render_discover_first_page
            )
        else:
            self.run_async(
                self.tmdb_api.fetch_popular(cat), self._render_discover_first_page
            )

    def _render_discover_first_page(self, data):
        results, posters, total_pages = data
        self.discover_total_pages = total_pages
        self.all_discover_results = results.copy()
        self._render_discover(
            results, "tv" if self.mode_switch.get() == "TV Show" else "movie", posters
        )

    def _render_discover(self, results, cat, posters=None):
        self._last_discover_data = (results, cat, posters)

        def _ui_render():
            for w in self.discover_container.winfo_children():
                getattr(w, "grid_forget", lambda: None)()

            width = self.discover_container.winfo_width()
            if width < 400:
                width = 1100

            columns = max(1, (width - 40) // 200)

            for i in range(10):
                self.discover_container.grid_columnconfigure(i, weight=0)

            for i in range(columns):
                self.discover_container.grid_columnconfigure(i, weight=1)

            for i, item in enumerate(results[:20]):
                if i < len(self.discover_cards):
                    card = self.discover_cards[i]
                else:
                    card = ItemCard(self.discover_container, self)
                    self.discover_cards.append(card)

                poster_pil = posters[i] if posters and i < len(posters) else None
                card.update_data(item, cat, poster_pil)
                card.grid(
                    row=i // columns,
                    column=i % columns,
                    padx=10,
                    pady=10,
                    sticky="nsew",
                )

        self.after(0, _ui_render)

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

    def update_task_status(self, task_id, status, progress=None, retry=0):
        def _ui_action():
            if task_id not in self.active_tasks:
                if retry < 10:
                    self.after(
                        100,
                        lambda: self.update_task_status(
                            task_id, status, progress, retry + 1
                        ),
                    )
                return
            t = self.active_tasks[task_id]
            if (
                t.get("done")
                and status != "FINISHED"
                and status != "ALREADY FOUND"
                and status != "NOT FOUND"
            ):
                return
            if not t.get("stat"):
                if retry < 10:
                    self.after(
                        100,
                        lambda: self.update_task_status(
                            task_id, status, progress, retry + 1
                        ),
                    )
                return

            t["stat"].configure(text=status.upper())
            if status == "FINISHED":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#2ecc71")
                t["progress_val"] = 1.0
                t["prog"].set(1.0)
            elif status == "NOT FOUND":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#e74c3c")
                t["progress_val"] = 1.0
                t["prog"].set(1.0)
            elif status == "ALREADY FOUND":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#f1c40f")
                t["progress_val"] = 1.0
                t["prog"].set(1.0)
            elif progress is not None:
                t["progress_val"] = progress
                t["prog"].set(progress)

        self.after(0, _ui_action)

    def add_task_ui(self, task_id, folder=None, display_name=None):
        if task_id in self.active_tasks:
            if folder:
                self.active_tasks[task_id]["folder"] = folder
            return

        label_text = display_name if display_name else task_id

        row = ctk.CTkFrame(
            self.task_monitor,
            fg_color=("#e0e0e0", "#181818"),
            height=40,
            corner_radius=0,
            border_width=0,
        )
        row.pack(fill="x", pady=1, padx=2)
        ctk.CTkLabel(
            row, text=label_text, width=250, anchor="w", font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=15)

        prog = ctk.CTkProgressBar(row, width=380, height=8, progress_color="#3498db")
        prog.pack(side="left", padx=10)
        prog.set(0.05)
        stat = ctk.CTkLabel(
            row, text="WAITING", text_color="#777", font=("Consolas", 10, "bold")
        )
        stat.pack(side="right", padx=15)
        self.active_tasks[task_id] = {
            "row": row,
            "prog": prog,
            "stat": stat,
            "done": False,
            "progress_val": 0.05,
            "folder": folder,
        }

        self.after(10, lambda: self.task_monitor._parent_canvas.yview_moveto(1.0))

    def clear_finished_tasks(self):
        try:
            for tid in list(self.active_tasks.keys()):
                if self.active_tasks[tid]["done"]:
                    self.active_tasks[tid]["row"].destroy()
                    del self.active_tasks[tid]
            self.log("UI: Cleared finished tasks.")
            self.after(10, lambda: self.task_monitor._parent_canvas.yview_moveto(0.0))
        except Exception as e:
            self.log(f"ERROR clearing tasks: {e}")

    def _refresh_status_uis(self):
        if self.jelly_dashboard and self.jelly_dashboard.winfo_exists():
            self.jelly_dashboard.refresh_ui()

    def start_process(self):
        try:
            if getattr(self, "selected_tid", None) is None:
                self.log(
                    "ERROR: No media selected. Please search and select a title first."
                )
                messagebox.showwarning("Warning", "Please select a media title first.")
                return

            local_free = self.controller.update_local_storage_status()
            if local_free < 5:
                self.log(
                    f"CRITICAL: Low local disk space ({local_free:.1f} GB left). Process blocked."
                )
                messagebox.showerror(
                    "Error",
                    f"Low local disk space ({local_free:.1f} GB left). Download blocked.",
                )
                return

            if self.jellyfin_free_gb < 2:
                self.log(
                    f"WARNING: Low Jellyfin space ({self.jellyfin_free_gb:.1f} GB left)."
                )
                if not messagebox.askyesno(
                    "Warning",
                    f"Low space on Jellyfin server ({self.jellyfin_free_gb:.1f} GB left). Continue?",
                ):
                    return

            task_data = {
                "name": self.selected_name,
                "year": self.selected_year,
                "tid": self.selected_tid,
                "poster": self.selected_poster,
                "mode": self.mode_switch.get(),
                "selection_map": (
                    self.selection_map.copy() if self.selection_map else None
                ),
                "season_data": self.season_data.copy() if self.season_data else {},
                "start_season": self.start_season.get(),
                "end_season": self.end_season.get(),
                "resume_ep": self.resume_ep.get(),
                "quality": self.quality_var.get(),
                "sub_only": self.sub_only_var.get(),
                "video_only": self.video_only_var.get(),
            }

            is_idle = self.queue_manager.get_queue_size() == 0

            if is_idle:
                self.controller.missing_links = []

            self.queue_manager.add_to_queue(task_data)
            self.selection_map = {}
            self.controller.stop_event.clear()

            if not is_idle:
                messagebox.showinfo(
                    "Queued",
                    f"'{task_data['name']}' has been added to the download queue.",
                )

        except Exception as e:
            self.log(f"ERROR starting process: {e}")

    def stop_process(self):
        self.controller.stop_process()
        self.btn_run.configure(state="normal")

    def clear_finished_tasks_ui(self):
        for tid in list(self.active_tasks.keys()):
            if self.active_tasks[tid]["done"]:
                self.active_tasks[tid]["row"].destroy()
                del self.active_tasks[tid]

    def show_missing_links(self):
        try:
            win = ctk.CTkToplevel(self)
            win.title("Missing Download Links")
            win.geometry("500x400")
            win.attributes("-topmost", True)
            ctk.CTkLabel(
                win,
                text="The following items have no download links available:",
                font=("Segoe UI", 12, "bold"),
                wraplength=450,
            ).pack(pady=15)

            scroll = ctk.CTkScrollableFrame(win, width=450, height=250)
            scroll.pack(padx=20, pady=10, fill="both", expand=True)

            for item in self.controller.missing_links:
                ctk.CTkLabel(
                    scroll, text=f"• {item}", anchor="w", font=("Consolas", 11)
                ).pack(fill="x", pady=2)

            ctk.CTkButton(
                win,
                text="CLOSE",
                fg_color="#3498db",
                hover_color="#2980b9",
                command=win.destroy,
            ).pack(pady=15)
        except:
            pass

    def update_local_storage_status(self):
        self.local_free_gb = self.controller.update_local_storage_status()

    def render_results(self, results, cat, posters=None):
        self._last_search_data = (results, cat, posters)

        def _ui_render():
            try:
                for w in self.results_container.winfo_children():
                    getattr(w, "grid_forget", lambda: None)()

                if results:
                    self.results_container.pack(
                        fill="both", expand=True, padx=10, before=self.exec_frame
                    )
                    self.tabview.set("Search")
                else:
                    self.results_container.pack_forget()
                    return

                width = self.results_container.winfo_width()
                if width < 400:
                    width = 1100

                columns = max(1, (width - 40) // 200)

                for i in range(10):
                    self.results_container.grid_columnconfigure(i, weight=0)

                for i in range(columns):
                    self.results_container.grid_columnconfigure(i, weight=1)

                if results:
                    for i, item in enumerate(results[:20]):
                        if i < len(self.search_cards):
                            card = self.search_cards[i]
                        else:
                            card = ItemCard(self.results_container, self)
                            self.search_cards.append(card)

                        poster_pil = (
                            posters[i] if posters and i < len(posters) else None
                        )
                        card.update_data(item, cat, poster_pil)
                        card.grid(
                            row=i // columns,
                            column=i % columns,
                            padx=10,
                            pady=10,
                            sticky="nsew",
                        )

            except Exception as e:
                self.log(f"ERROR rendering results: {e}")

        self.after(0, _ui_render)

    def select_title(self, name, year, tid, poster_path, save_hist=True, cat=None):
        try:
            if cat:
                target_mode = "TV Show" if cat == "tv" else "Movie"
                if self.mode_switch.get() != target_mode:
                    self.mode_switch.set(target_mode)
                    self.log(f"UI: Auto-switched mode to {target_mode}")

            self.log(f"UI: Selected '{name} ({year})'")
            (
                self.selected_tid,
                self.selected_name,
                self.selected_year,
                self.selected_poster,
            ) = (tid, name, year, poster_path)
            self.title_display.configure(text=f"{name} ({year})", text_color="#3498db")
            self.results_container.pack_forget()
            self.start_season.delete(0, "end")
            self.start_season.insert(0, "1")
            self.resume_ep.delete(0, "end")
            self.resume_ep.insert(0, "1")
            self.selection_map = {}
            if poster_path:

                def _on_loaded(img):
                    if img and self.selected_tid == tid:
                        self.current_poster_ptr = ctk.CTkImage(
                            light_image=img, dark_image=img, size=(240, 340)
                        )
                        self.poster_label.configure(
                            image=self.current_poster_ptr,
                            text="",
                            fg_color="transparent",
                        )

                self.run_async(self.tmdb_api.load_poster(poster_path), _on_loaded)

            if self.mode_switch.get() == "TV Show":
                self.run_async(self.tmdb_api.fetch_seasons(tid))

            if save_hist:
                self.history = [i for i in (self.history or []) if i["tid"] != tid]
                self.history.insert(
                    0,
                    {
                        "name": name,
                        "year": year,
                        "tid": tid,
                        "poster": poster_path,
                        "cat": "tv" if self.mode_switch.get() == "TV Show" else "movie",
                    },
                )
                self.history = self.history[:15]
                self.render_history()
                self.save_settings()
        except:
            pass

    def render_history(self):
        try:
            for w in self.history_frame.winfo_children():
                w.destroy()
            query = getattr(self, "history_search", None)
            search_term = query.get().lower() if query else ""
            for i in self.history or []:
                if search_term and search_term not in i["name"].lower():
                    continue
                row = ctk.CTkFrame(self.history_frame, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkButton(
                    row,
                    text=f"{i['name']} ({i['year']})",
                    fg_color="transparent",
                    anchor="w",
                    height=24,
                    command=lambda x=i: self.select_title(
                        x["name"],
                        x["year"],
                        x["tid"],
                        x["poster"],
                        False,
                        cat=x.get("cat"),
                    ),
                ).pack(side="left", fill="x", expand=True)
                ctk.CTkButton(
                    row,
                    text="🗑",
                    width=24,
                    height=24,
                    fg_color="transparent",
                    hover_color="#e74c3c",
                    command=lambda x=i: self.handle_history_delete(x),
                ).pack(side="right", padx=5)
        except:
            pass

    def handle_history_delete(self, item):
        try:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Delete Options")
            dialog.geometry("400x200")
            dialog.attributes("-topmost", True)
            ctk.CTkLabel(
                dialog,
                text=f"How would you like to remove '{item['name']}'?",
                wraplength=350,
            ).pack(pady=20)
            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)

            def remove_history():
                self.history = [
                    i for i in (self.history or []) if i["tid"] != item["tid"]
                ]
                self.render_history()
                self.save_settings()
                dialog.destroy()

            ctk.CTkButton(
                btn_frame,
                text="History Only",
                fg_color="#3498db",
                hover_color="#2980b9",
                command=remove_history,
            ).pack(side="left", padx=10)
            ctk.CTkButton(
                btn_frame,
                text="Delete from Server",
                fg_color="#e74c3c",
                command=lambda: (
                    self.run_async(
                        self.jellyfin_api.delete_item(item, on_success=remove_history)
                    ),
                    dialog.destroy(),
                ),
            ).pack(side="left", padx=10)
        except:
            pass

    def toggle_jellyfin_ui(self, *args):
        try:
            if self.show_jellyfin_var.get():
                self.btn_jelly_dashboard.grid()
            else:
                self.btn_jelly_dashboard.grid_forget()
            self.save_settings()
        except:
            pass

    def open_queue_window(self):
        try:
            win = ctk.CTkToplevel(self)
            win.title("Pending Download Queue")
            win.geometry("600x500")
            win.attributes("-topmost", True)

            ctk.CTkLabel(
                win,
                text="PENDING TASKS",
                font=("Segoe UI", 16, "bold"),
                text_color="#3498db",
            ).pack(pady=15)

            scroll = ctk.CTkScrollableFrame(win, width=550, height=350)
            scroll.pack(padx=20, pady=10, fill="both", expand=True)

            def refresh_list():
                for w in scroll.winfo_children():
                    w.destroy()

                active = self.queue_manager.active_tasks
                if active:
                    ctk.CTkLabel(
                        scroll,
                        text="ACTIVE (DOWNLOADING)",
                        font=("Segoe UI", 11, "bold"),
                        text_color="#2ecc71",
                    ).pack(pady=(5, 2), padx=10, anchor="w")
                    for tid, task in active.items():
                        row = ctk.CTkFrame(scroll, fg_color=("#d0d0d0", "#222222"))
                        row.pack(fill="x", pady=2, padx=5)
                        ctk.CTkLabel(
                            row,
                            text=f"▶ {task['name']} ({task['year']})",
                            anchor="w",
                            font=("Segoe UI", 12, "bold"),
                        ).pack(side="left", padx=15, pady=10)
                        ctk.CTkLabel(
                            row,
                            text="PROCESSING",
                            text_color="#2ecc71",
                            font=("Consolas", 10),
                        ).pack(side="right", padx=15)

                tasks = self.queue_manager.get_pending_tasks()
                if tasks:
                    ctk.CTkLabel(
                        scroll,
                        text="PENDING (IN QUEUE)",
                        font=("Segoe UI", 11, "bold"),
                        text_color="#3498db",
                    ).pack(pady=(15, 2), padx=10, anchor="w")
                    for idx, task in enumerate(tasks):
                        row = ctk.CTkFrame(scroll, fg_color=("#e0e0e0", "#181818"))
                        row.pack(fill="x", pady=2, padx=5)

                        ctk.CTkLabel(
                            row,
                            text=f"{task['name']} ({task['year']})",
                            anchor="w",
                            font=("Segoe UI", 12),
                        ).pack(side="left", padx=15, pady=10, expand=True, fill="x")

                        btn_f = ctk.CTkFrame(row, fg_color="transparent")
                        btn_f.pack(side="right", padx=10)

                        ctk.CTkButton(
                            btn_f,
                            text="🔝",
                            width=30,
                            height=28,
                            fg_color="#3498db",
                            hover_color="#2980b9",
                            command=lambda i=idx: (
                                self.queue_manager.move_to_top(i),
                                refresh_list(),
                            ),
                        ).pack(side="left", padx=2)

                        ctk.CTkButton(
                            btn_f,
                            text="▲",
                            width=30,
                            height=28,
                            fg_color="#3498db",
                            hover_color="#2980b9",
                            command=lambda i=idx: (
                                self.queue_manager.move_up(i),
                                refresh_list(),
                            ),
                        ).pack(side="left", padx=2)

                        ctk.CTkButton(
                            btn_f,
                            text="▼",
                            width=30,
                            height=28,
                            fg_color="#3498db",
                            hover_color="#2980b9",
                            command=lambda i=idx: (
                                self.queue_manager.move_down(i),
                                refresh_list(),
                            ),
                        ).pack(side="left", padx=2)

                        ctk.CTkButton(
                            btn_f,
                            text="DELETE",
                            width=60,
                            height=28,
                            fg_color="#e74c3c",
                            command=lambda i=idx: (
                                self.queue_manager.remove_from_queue(i),
                                refresh_list(),
                            ),
                        ).pack(side="left", padx=(10, 2))

                if not active and not tasks:
                    ctk.CTkLabel(
                        scroll, text="Queue is empty.", font=("Segoe UI", 12, "italic")
                    ).pack(pady=20)

            refresh_list()

            ctk.CTkButton(
                win,
                text="CLOSE",
                fg_color="#3498db",
                hover_color="#2980b9",
                command=win.destroy,
            ).pack(pady=15)
        except Exception as e:
            self.log(f"ERROR opening queue window: {e}")

    def open_jellyfin_dashboard(self):
        if self.jelly_dashboard is None or not self.jelly_dashboard.winfo_exists():
            self.jelly_dashboard = JellyfinDashboard(self)
        else:
            self.jelly_dashboard.focus()

    def on_mode_change(self, v):
        self.log(f"UI: Mode set to {v}")

        if hasattr(self, "refresh_discover"):
            self.refresh_discover()
        if hasattr(self, "results_container"):
            for w in self.results_container.winfo_children():
                getattr(w, "grid_forget", lambda: None)()
            self.results_container.pack_forget()

        if hasattr(self, "title_display"):
            self.title_display.configure(
                text="Select Media", text_color=("#000000", "#ffffff")
            )

        self.selected_tid = None
        self.selected_name = None
        self.selected_year = None
        self.selected_poster = None
        self.season_data = {}
        self.current_poster_ptr = None
        try:
            self.poster_label.configure(image=None, text="No Preview")
        except:
            pass

    def clear_history(self):
        try:
            self.history = []
            self.render_history()
            self.save_settings()
            self.log("UI: History cleared.")
        except:
            pass

    def choose_root(self):
        try:
            p = filedialog.askdirectory(title="Select Jellyfin Media Root Folder")
            if p:
                p = os.path.normpath(p)
                dirname = os.path.basename(p)

                if dirname.lower() in ["movies", "shows"]:
                    p = os.path.dirname(p)

                self.show_path = os.path.join(p, "Shows")
                self.movie_path = os.path.join(p, "Movies")

                self.save_settings()
                self.log(
                    f"UI: Media Root updated. Shows -> {self.show_path}, Movies -> {self.movie_path}"
                )
                messagebox.showinfo(
                    "Success",
                    f"Media Root verified:\n\n{p}\n\nFolders will be created when a download starts.",
                )
        except Exception as e:
            self.log(f"ERROR choosing root path: {e}")
            messagebox.showerror("Error", f"Failed to set media root: {e}")

    def get_existing_episodes(self, name, year):
        existing = {}
        try:
            root = (
                self.show_path
                if self.mode_switch.get() == "TV Show"
                else self.movie_path
            )
            if not root or not name or not year:
                return existing

            show_dir = os.path.join(root, f"{sanitize_path(name)} ({year})")
            if not os.path.exists(show_dir):
                return existing
            for root_dir, _, files in os.walk(show_dir):
                for f in files:
                    match = re.search(r"S(\d+)\s*E(\d+)", f, re.IGNORECASE)
                    if match:
                        s_num, e_num = int(match.group(1)), int(match.group(2))
                        if s_num not in existing:
                            existing[s_num] = []
                        existing[s_num].append(e_num)
        except:
            pass
        return existing

    def open_ep_selector(self):
        try:
            if not self.season_data:
                messagebox.showwarning(
                    "Warning", "Please search and select a TV Show first."
                )
                return
            selector = ctk.CTkToplevel(self)
            selector.title(f"Episode Selection - {self.selected_name}")
            selector.geometry("700x800")
            selector.attributes("-topmost", True)
            existing = self.get_existing_episodes(
                self.selected_name or "", self.selected_year or ""
            )
            scroll = ctk.CTkScrollableFrame(selector)
            scroll.pack(fill="both", expand=True, padx=10, pady=10)

            checks = {}
            for s_num in sorted(self.season_data.keys()):
                s_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                s_frame.pack(fill="x", pady=5)
                ctk.CTkLabel(
                    s_frame, text=f"Season {s_num}", font=("Segoe UI", 14, "bold")
                ).pack(side="top", anchor="w", padx=5)
                ep_frame = ctk.CTkFrame(s_frame, fg_color="transparent")
                ep_frame.pack(fill="x", pady=2)
                checks[s_num] = {}
                for e_idx in range(1, self.season_data[s_num] + 1):
                    is_dup = e_idx in existing.get(s_num, [])
                    var = ctk.BooleanVar(
                        value=(
                            s_num in self.selection_map
                            and e_idx in self.selection_map[s_num]
                        )
                    )
                    cb = ctk.CTkCheckBox(
                        ep_frame,
                        text=f"{e_idx}✔" if is_dup else str(e_idx),
                        variable=var,
                        width=60,
                        text_color="#2ecc71" if is_dup else None,
                        fg_color="#3498db",
                        hover_color="#2980b9",
                    )
                    cb.grid(
                        row=(e_idx - 1) // 8, column=(e_idx - 1) % 8, padx=2, pady=2
                    )
                    checks[s_num][e_idx] = var

            def save_selection():
                self.selection_map = {
                    s: sorted([e for e, v in eps.items() if v.get()])
                    for s, eps in checks.items()
                    if any(v.get() for v in eps.values())
                }
                self.log(
                    f"UI: Selected {sum(len(eps) for eps in self.selection_map.values())} episodes."
                )
                selector.destroy()

            footer = ctk.CTkFrame(selector)
            footer.pack(fill="x", pady=10)
            ctk.CTkButton(
                footer,
                text="SELECT MISSING",
                fg_color="#3498db",
                hover_color="#2980b9",
                command=lambda: [
                    v.set(e not in existing.get(s, []))
                    for s, eps in checks.items()
                    for e, v in eps.items()
                ],
            ).pack(side="left", padx=10)
            ctk.CTkButton(
                footer,
                text="SAVE",
                fg_color="#3498db",
                hover_color="#2980b9",
                command=save_selection,
            ).pack(side="right", padx=20)
        except:
            pass

    def open_settings(self):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsWindow(self)
        else:
            self.settings_window.focus()

    def open_rpc_settings(self):
        if (
            self.rpc_settings_window is None
            or not self.rpc_settings_window.winfo_exists()
        ):
            self.rpc_settings_window = RPCSettingsWindow(self)
        else:
            self.rpc_settings_window.focus()

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
