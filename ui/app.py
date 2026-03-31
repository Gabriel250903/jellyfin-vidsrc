import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import time
import os
import sys
import re
import json
import requests
import queue
import shutil
from watchdog.observers import Observer

from core.utils import resource_path, sanitize_path, notify
from core.file_handler import DownloadHandler
from core.scraper import VidSrcScraper
from core.queue_manager import DownloadQueueManager
from api.jellyfin_api import JellyfinAPI
from api.tmdb_api import TMDBAPI
from ui.jellyfin_dashboard import JellyfinDashboard
from ui.rpc_settings import RPCSettingsWindow
from ui.settings_window import SettingsWindow
from api.discord_rpc import DiscordRPCManager


class VidSrcJellyfin(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VidSrc Jellyfin")
        self.geometry("1350x1050")
        self.minsize(1000, 800)
        ctk.set_appearance_mode("dark")

        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.current_speed = "0.0 MB/s"
        self.current_status = "IDLE"
        self.eta_text = "ETA: --:--"
        self.driver = None
        self.season_data = {}
        self.history = []
        self.active_tasks = {}
        self.selection_map = {}
        self.batch_start_time = 0
        self.items_completed = 0
        self.total_items = 0
        self.current_target_folder = None
        self.failed_tasks = []
        self.selected_tid = None
        self.selected_name = None
        self.selected_year = None
        self.selected_poster = None
        self.discord_webhook = ""
        self.tmdb_api_key = ""
        self.current_accent = "Blue"
        self.jellyfin_url = ""
        self.jellyfin_api_key = ""
        self.last_jelly_check = 0
        self.last_jelly_sessions = {}
        self.jellyfin_free_gb = 9999
        self.local_free_gb = 9999
        self.missing_links = []

        self._last_vals = {}
        self._is_resizing = False
        self._resize_timer = None

        self.rpc_enabled = False
        self.rpc_client_id = ""
        self.rpc_target_user = ""
        self.rpc_show_time = True
        self.rpc_show_server = True

        if getattr(sys, 'frozen', False):
            self.config_file = os.path.join(os.path.dirname(sys.executable), "jellyfin_config.json")
        else:
            self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jellyfin_config.json")

        self.show_path = r"C:\Jellyfin\Shows"
        self.movie_path = r"C:\Jellyfin\Movies"
        self.observer = Observer()

        self.tmdb_api = TMDBAPI(self)
        self.jellyfin_api = JellyfinAPI(self)
        self.scraper = VidSrcScraper(self)
        self.queue_manager = DownloadQueueManager(self)

        self.jelly_dashboard = None
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
        
        self.update_loop()
        self.after(0, lambda: self.state("zoomed"))
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if event.widget == self:
            if not self._is_resizing:
                self._is_resizing = True
                self.sidebar.grid_remove()
                self.main_view.grid_remove()

            if self._resize_timer:
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(400, self._stop_resize_flag)

    def _stop_resize_flag(self):
        self._is_resizing = False
        self._resize_timer = None
        self.sidebar.grid()
        self.main_view.grid()

    def _safe_configure(self, widget, key, val):
        cache_key = f"{id(widget)}_{key}"
        if self._last_vals.get(cache_key) != val:
            widget.configure(**{key: val})
            self._last_vals[cache_key] = val

    def on_closing(self):
        if hasattr(self, 'discord_rpc') and self.discord_rpc:
            self.discord_rpc.stop()
        self.destroy()

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=350, corner_radius=0, fg_color=("#ebebeb", "#111111"), border_width=0
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
            self.sidebar, values=["TV Show", "Movie"], command=self.on_mode_change,
            height=35, selected_color="#3498db"
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
        self.content_inner = ctk.CTkFrame(self.main_view, fg_color="transparent")
        self.content_inner.pack(fill="both", expand=True, padx=30, pady=20)
        self.content_inner.grid_columnconfigure(0, weight=1)

        search_f = ctk.CTkFrame(self.content_inner, fg_color="transparent")
        search_f.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        search_f.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_f,
            placeholder_text="Search TMDB or enter TMDB ID...",
            height=30,
            font=("Segoe UI", 14),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind(
            "<Return>",
            lambda e: self.tmdb_api.perform_search(
                self.search_entry.get(), self.search_year.get()
            ),
        )

        self.search_year = ctk.CTkEntry(
            search_f,
            placeholder_text="Year",
            width=70,
            height=30,
            font=("Segoe UI", 14),
        )
        self.search_year.grid(row=0, column=1, padx=(10, 0))
        self.search_year.bind(
            "<Return>",
            lambda e: self.tmdb_api.perform_search(
                self.search_entry.get(), self.search_year.get()
            ),
        )

        self.btn_search = ctk.CTkButton(
            search_f,
            text="SEARCH",
            width=100,
            height=30,
            fg_color="#3498db",
            hover_color="#2980b9",
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.tmdb_api.perform_search(
                self.search_entry.get(), self.search_year.get()
            ),
        )
        self.btn_search.grid(row=0, column=2, padx=(10, 0))

        self.results_container = ctk.CTkScrollableFrame(
            self.content_inner, height=300, fg_color=("#f0f0f0", "#0a0a0a"),
            corner_radius=0, border_width=0
        )
        self.results_container.grid(row=1, column=0, sticky="ew")
        self.results_container.grid_remove()

        self.exec_frame = ctk.CTkFrame(
            self.content_inner,
            fg_color=("#f9f9f9", "#151515"),
            corner_radius=0,
            border_width=0,
        )
        self.exec_frame.grid(row=2, column=0, sticky="ew", pady=10)
        self.title_display = ctk.CTkLabel(
            self.exec_frame, text="Select Media", font=("Segoe UI", 20, "bold")
        )
        self.title_display.pack(pady=10)

        input_f = ctk.CTkFrame(self.exec_frame, fg_color="transparent")
        input_f.pack(pady=5)
        self.start_season = ctk.CTkEntry(input_f, placeholder_text="S-Start", width=60)
        self.start_season.pack(side="left", padx=5)
        self.end_season = ctk.CTkEntry(input_f, placeholder_text="S-End", width=60)
        self.end_season.pack(side="left", padx=5)
        self.resume_ep = ctk.CTkEntry(input_f, placeholder_text="Ep-Start", width=60)
        self.resume_ep.pack(side="left", padx=5)
        self.btn_select_eps = ctk.CTkButton(
            input_f,
            text="SELECT EPS",
            width=80,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_ep_selector,
        )
        self.btn_select_eps.pack(side="left", padx=5)

        self.quality_var = ctk.StringVar(value="1080p")
        self.sub_only_var = ctk.BooleanVar(value=False)
        self.video_only_var = ctk.BooleanVar(value=False)
        self.open_folder_var = ctk.BooleanVar(value=True)
        self.show_jellyfin_var = ctk.BooleanVar(value=True)

        switches_f = ctk.CTkFrame(self.exec_frame, fg_color="transparent")
        switches_f.pack(pady=5)

        ctk.CTkSwitch(
            switches_f, text="Subtitles Only Mode", variable=self.sub_only_var,
            progress_color="#3498db"
        ).pack(side="left", padx=10)

        ctk.CTkSwitch(
            switches_f, text="Videos Only Mode", variable=self.video_only_var,
            progress_color="#3498db"
        ).pack(side="left", padx=10)

        monitor_header = ctk.CTkFrame(self.content_inner, fg_color="transparent")
        monitor_header.grid(row=3, column=0, sticky="ew", padx=5, pady=(10, 0))
        self.tasks_header_lbl = ctk.CTkLabel(
            monitor_header,
            text="ACTIVE TASKS",
            font=("Segoe UI", 11, "bold"),
            text_color="#3498db",
        )
        self.tasks_header_lbl.pack(side="left")
        self.btn_remove_finished = ctk.CTkButton(
            monitor_header,
            text="REMOVE FINISHED",
            width=110,
            height=22,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.clear_finished_tasks,
        )
        self.btn_remove_finished.pack(side="right")

        self.task_monitor = ctk.CTkScrollableFrame(
            self.content_inner, height=220, fg_color=("#f0f0f0", "#0a0a0a"),
            corner_radius=0, border_width=0
        )
        self.task_monitor.grid(row=4, column=0, sticky="nsew", pady=5)

        btn_f = ctk.CTkFrame(self.content_inner, fg_color="transparent")
        btn_f.grid(row=5, column=0, sticky="ew", pady=10)
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
            self.content_inner, height=180, font=("Consolas", 12), state="disabled"
        )
        self.log_box.grid(row=6, column=0, sticky="nsew", pady=(10, 0))

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

    def log(self, msg):
        self.log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def update_task_status(self, task_id, status, progress=None, retry=0):
        def _ui_action():
            if task_id not in self.active_tasks:
                if retry < 10:
                    self.after(100, lambda: self.update_task_status(task_id, status, progress, retry + 1))
                return
            t = self.active_tasks[task_id]
            if t.get("done") and status != "FINISHED" and status != "ALREADY FOUND" and status != "NOT FOUND":
                return
            if not t.get("stat"):
                if retry < 10:
                    self.after(100, lambda: self.update_task_status(task_id, status, progress, retry + 1))
                return
            
            t["stat"].configure(text=status.upper())
            if status == "FINISHED":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#2ecc71")
                    self.items_completed += 1
                    self.update_eta()
                t["progress_val"] = 1.0
                t["prog"].set(1.0)
            elif status == "NOT FOUND":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#e74c3c")
                    self.items_completed += 1
                    self.update_eta()
                t["progress_val"] = 1.0
                t["prog"].set(1.0)
            elif status == "ALREADY FOUND":
                if not t.get("done"):
                    t["done"] = True
                    t["stat"].configure(text_color="#f1c40f")
                    self.items_completed += 1
                    self.update_eta()
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
            self.task_monitor, fg_color=("#e0e0e0", "#181818"), height=40,
            corner_radius=0, border_width=0
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

    def update_loop(self):
        if self._is_resizing:
            self.after(500, self.update_loop)
            return

        logs_to_add = []
        count = 0
        while not self.log_queue.empty() and count < 15:
            logs_to_add.append(self.log_queue.get_nowait())
            count += 1
        
        if logs_to_add:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "".join(logs_to_add))
            
            total_lines = int(self.log_box.index("end-1c").split(".")[0])
            if total_lines > 500:
                self.log_box.delete("1.0", f"{total_lines - 500}.0")
                
            self.log_box.configure(state="disabled")
            self.log_box.see("end")

        for tid, t in list(self.active_tasks.items()):
            if not t["done"]:
                curr_stat = t["stat"].cget("text")
                if curr_stat == "DOWNLOADING":
                    if t["progress_val"] < 0.98:
                        t["progress_val"] += 0.002
                        t["prog"].set(t["progress_val"])
                elif curr_stat == "FETCHING":
                    if t["progress_val"] < 0.4:
                        t["progress_val"] += 0.001
                        t["prog"].set(t["progress_val"])

        self._safe_configure(self.lbl_speed, "text", f"Speed: {self.current_speed}")
        self._safe_configure(self.lbl_queue, "text", f"Queue: {self.queue_manager.get_queue_size()}")
        self._safe_configure(self.lbl_status, "text", f"STATUS: {self.current_status}")
        self._safe_configure(self.lbl_eta, "text", self.eta_text)

        if time.time() - self.last_jelly_check > 10:
            self.last_jelly_check = time.time()
            threading.Thread(target=self.update_status_background, daemon=True).start()

        self.after(1000, self.update_loop)


    def update_status_background(self):
        try:
            self.jellyfin_api.update_status()
            self.update_local_storage_status()
            
            self.after(0, self._refresh_status_uis)
        except Exception as e:
            print(f"Background status update error: {e}")

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
            if self.local_free_gb < 5:
                self.log(
                    f"CRITICAL: Low local disk space ({self.local_free_gb:.1f} GB left). Process blocked."
                )
                messagebox.showerror(
                    "Error",
                    f"Low local disk space on your laptop ({self.local_free_gb:.1f} GB left). Download blocked.",
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

            is_idle = (
                self.queue_manager.get_queue_size() == 0
                and not self.queue_manager.current_task
            )

            if is_idle:
                self.missing_links = []

            self.queue_manager.add_to_queue(task_data)
            self.selection_map = {}
            self.stop_event.clear()

            if not is_idle:
                messagebox.showinfo(
                    "Queued", f"'{task_data['name']}' has been added to the download queue."
                )

        except Exception as e:
            self.log(f"ERROR starting process: {e}")

    def stop_process(self):
        self.stop_event.set()
        self.log("STOP: Process killed by user. Queue will halt.")
        self.current_status = "IDLE"
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except:
                pass
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join()
            except:
                pass
        self.btn_run.configure(state="normal")

    def process_queued_item(self, task):
        name, year, tid, poster = (
            sanitize_path(task["name"]),
            task["year"],
            task["tid"],
            task["poster"],
        )
        mode = task["mode"]
        selection_map = task["selection_map"]

        self.log(f"UI: Processing '{name} ({year})' from queue.")
        self.batch_start_time = time.time()
        self.items_completed = 0
        self.current_status = "DOWNLOADING"
        self.failed_tasks = []

        self.after(0, self.clear_finished_tasks_ui)

        season_data = task["season_data"]

        if mode == "Movie":
            self.total_items = 1
        else:
            if selection_map:
                self.total_items = sum(len(eps) for eps in selection_map.values())
            else:
                sf, st = int(task["start_season"] or 1), int(task["end_season"] or 1)
                self.total_items = sum(
                    season_data.get(s, 20) for s in range(sf, st + 1)
                )

        root = self.show_path if mode == "TV Show" else self.movie_path
        if not os.path.exists(root):
            os.makedirs(root)

        if self.observer and self.observer.is_alive():
            try:
                self.observer.stop()
                self.observer.join()
            except:
                pass
        self.observer = Observer()
        self.observer.schedule(
            DownloadHandler(self, media_name=name, media_year=year),
            root,
            recursive=True,
        )
        self.observer.start()

        try:
            main_folder = os.path.join(root, f"{name} ({year})")
            if not os.path.exists(main_folder):
                os.makedirs(main_folder)

            self.tmdb_api.download_metadata(name, year, tid, mode, main_folder)

            if mode == "Movie":
                self.scraper.trigger_downloads(
                    main_folder,
                    tid,
                    "movie",
                    media_name=name,
                    quality=task["quality"],
                    sub_only=task["sub_only"],
                    video_only=task["video_only"],
                )
                self.wait_for_done(main_folder)
                self.clean_subtitles(main_folder)
                if not self.stop_event.is_set() and self.show_jellyfin_var.get():
                    self.jellyfin_api.trigger_scan(main_folder)
                    self.jellyfin_api.send_message(
                        "Download Complete", f"'{name} ({year})' is ready!"
                    )
            else:
                if selection_map:
                    for s in sorted(selection_map.keys()):
                        if self.stop_event.is_set():
                            break
                        folder = os.path.join(main_folder, f"Season {s}")
                        if not os.path.exists(folder):
                            os.makedirs(folder)
                        self.scraper.trigger_selected_episodes(
                            folder,
                            tid,
                            s,
                            selection_map[s],
                            media_name=name,
                            quality=task["quality"],
                            sub_only=task["sub_only"],
                            video_only=task["video_only"],
                        )
                        self.wait_for_done(folder)
                        self.clean_subtitles(folder)
                        if (
                            not self.stop_event.is_set()
                            and self.show_jellyfin_var.get()
                        ):
                            self.jellyfin_api.trigger_scan(folder)
                            self.jellyfin_api.send_message(
                                "Season Ready", f"{name} - Season {s} is now available!"
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
                            os.makedirs(folder)
                        self.scraper.trigger_downloads(
                            folder,
                            tid,
                            "tv",
                            s,
                            season_data.get(s, 50),
                            start_ep if s == sf else 1,
                            media_name=name,
                            quality=task["quality"],
                            sub_only=task["sub_only"],
                            video_only=task["video_only"],
                        )
                        self.wait_for_done(folder)
                        self.clean_subtitles(folder)
                        if (
                            not self.stop_event.is_set()
                            and self.show_jellyfin_var.get()
                        ):
                            self.jellyfin_api.trigger_scan(folder)
                            self.jellyfin_api.send_message(
                                "Season Ready", f"{name} - Season {s} is now available!"
                            )

            if self.failed_tasks and not self.stop_event.is_set():
                self.log(
                    f"RETRY: Waiting for disk to settle before attempting {len(self.failed_tasks)} failed episodes..."
                )
                time.sleep(5)

                for f_task in list(self.failed_tasks):
                    if self.stop_event.is_set():
                        break
                    f, t, m, s, e = f_task

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
                        )
                        continue

                    self.scraper.trigger_downloads(f, t, m, s, e, e, is_retry=True, media_name=name)
                    self.wait_for_done(f)
                    self.clean_subtitles(f)

            if not self.stop_event.is_set():
                if self.cleanup_empty_folders(main_folder):
                    self.log(
                        f"UI: Cleaned up empty folder for '{name} ({year})' as no media was found."
                    )
                else:
                    notify("Download Complete", f"All tasks for {name} have finished.")
                    self.send_discord_notification(name, year, poster)
                    self.jellyfin_api.trigger_scan(main_folder)
                    if self.open_folder_var.get():
                        os.startfile(main_folder)

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            self.after(0, lambda: self.btn_run.configure(state="normal"))
            self.current_status = "IDLE"
            if self.observer:
                try:
                    self.observer.stop()
                    self.observer.join()
                except:
                    pass

    def clear_finished_tasks_ui(self):
        for tid in list(self.active_tasks.keys()):
            self.active_tasks[tid]["row"].destroy()
        self.active_tasks = {}

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

            for item in self.missing_links:
                ctk.CTkLabel(
                    scroll, text=f"• {item}", anchor="w", font=("Consolas", 11)
                ).pack(fill="x", pady=2)

            ctk.CTkButton(win, text="CLOSE", fg_color="#3498db", hover_color="#2980b9", command=win.destroy).pack(pady=15)
        except:
            pass

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

    def wait_for_done(self, folder, quit_driver=True):
        while not self.stop_event.is_set() and [
            f for f in os.listdir(folder) if f.endswith(".crdownload")
        ]:
            self.calc_speed(folder)
            time.sleep(1)
        if quit_driver and self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except:
                pass

    def calc_speed(self, folder):
        try:
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.endswith(".crdownload")
            ]
            if not files:
                self.current_speed = "0.0 MB/s"
                return
            s1 = sum(os.path.getsize(f) for f in files)
            time.sleep(0.5)
            self.current_speed = (
                f"{(sum(os.path.getsize(f) for f in files)-s1)*2/1024/1024:.1f} MB/s"
            )
        except:
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

    def update_local_storage_status(self):
        try:
            root = (
                self.show_path
                if self.mode_switch.get() == "TV Show"
                else self.movie_path
            )
            if not os.path.exists(root):
                os.makedirs(root, exist_ok=True)
            import shutil

            usage = shutil.disk_usage(os.path.abspath(root))
            self.local_free_gb = usage.free / (1024**3)
        except:
            pass

    def send_discord_notification(self, name, year, poster_path):
        if not self.discord_webhook:
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
            requests.post(self.discord_webhook, json={"embeds": [embed]}, timeout=10)
        except:
            pass

    def render_results(self, results, cat):
        try:
            for w in self.results_container.winfo_children():
                w.destroy()

            if results:
                self.results_container.grid()
            else:
                self.results_container.grid_remove()
                return

            for item in results[:20]:
                name = item.get("name") if cat == "tv" else item.get("title")
                year = (
                    item.get("first_air_date") or item.get("release_date") or "0000"
                )[:4]
                tid, p_path = item.get("id"), item.get("poster_path")
                f = ctk.CTkFrame(
                    self.results_container, fg_color=("#e0e0e0", "#151515")
                )
                f.pack(fill="x", pady=1, padx=5)
                ctk.CTkLabel(f, text=f"{name} ({year})").pack(side="left", padx=10)
                ctk.CTkButton(
                    f,
                    text="SELECT",
                    width=60,
                    height=24,
                    fg_color="#3498db",
                    hover_color="#2980b9",
                    command=lambda n=name, y=year, i=tid, p=p_path: self.select_title(
                        n, y, i, p
                    ),
                ).pack(side="right", padx=5, pady=3)
        except Exception as e:
            self.log(f"ERROR rendering results: {e}")

    def select_title(self, name, year, tid, poster_path, save_hist=True):
        try:
            self.log(f"UI: Selected '{name} ({year})'")
            (
                self.selected_tid,
                self.selected_name,
                self.selected_year,
                self.selected_poster,
            ) = (tid, name, year, poster_path)
            self.title_display.configure(text=f"{name} ({year})", text_color="#3498db")
            self.results_container.grid_remove()
            self.start_season.delete(0, "end")
            self.start_season.insert(0, "1")
            self.resume_ep.delete(0, "end")
            self.resume_ep.insert(0, "1")
            self.selection_map = {}
            if poster_path:
                threading.Thread(
                    target=self.tmdb_api.load_poster, args=(poster_path,), daemon=True
                ).start()
            if self.mode_switch.get() == "TV Show":
                self.tmdb_api.fetch_seasons(tid)
            if save_hist:
                self.history = [i for i in self.history if i["tid"] != tid]
                self.history.insert(
                    0,
                    {
                        "name": name,
                        "year": year,
                        "tid": tid,
                        "poster": poster_path,
                        "cat": self.mode_switch.get(),
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
            for i in self.history:
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
                        x["name"], x["year"], x["tid"], x["poster"], False
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
                self.history = [i for i in self.history if i["tid"] != item["tid"]]
                self.render_history()
                self.save_settings()
                dialog.destroy()

            ctk.CTkButton(btn_frame, text="History Only", fg_color="#3498db", hover_color="#2980b9", command=remove_history).pack(
                side="left", padx=10
            )
            ctk.CTkButton(
                btn_frame,
                text="Delete from Server",
                fg_color="#e74c3c",
                command=lambda: (
                    self.jellyfin_api.delete_item(item, on_success=remove_history),
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
                self.btn_jelly_dashboard.grid_remove()
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

                tasks = self.queue_manager.get_pending_tasks()
                if not tasks:
                    ctk.CTkLabel(
                        scroll, text="Queue is empty.", font=("Segoe UI", 12, "italic")
                    ).pack(pady=20)
                    return

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

            refresh_list()
            ctk.CTkButton(win, text="CLOSE", fg_color="#3498db", hover_color="#2980b9", command=win.destroy).pack(pady=15)
        except Exception as e:
            self.log(f"ERROR opening queue window: {e}")

    def open_jellyfin_dashboard(self):
        if self.jelly_dashboard is None or not self.jelly_dashboard.winfo_exists():
            self.jelly_dashboard = JellyfinDashboard(self)
        else:
            self.jelly_dashboard.focus()

    def update_eta(self):
        try:
            if self.items_completed == 0 or self.total_items <= self.items_completed:
                return
            rem = (self.total_items - self.items_completed) * (
                (time.time() - self.batch_start_time) / self.items_completed
            )
            m, s = divmod(int(rem), 60)
            self.eta_text = f"ETA: {m}m {s}s"
        except:
            pass

    def on_mode_change(self, v):
        self.log(f"UI: Mode set to {v}")

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

                if not os.path.exists(self.show_path):
                    os.makedirs(self.show_path)
                if not os.path.exists(self.movie_path):
                    os.makedirs(self.movie_path)

                self.save_settings()
                self.log(
                    f"UI: Media Root updated. Shows -> {self.show_path}, Movies -> {self.movie_path}"
                )
                messagebox.showinfo(
                    "Success",
                    f"Media Root verified:\n\n{p}\n\nShows and Movies folders are ready.",
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
                self.selected_name, self.selected_year
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
                        hover_color="#2980b9"
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
            ctk.CTkButton(footer, text="SAVE", fg_color="#3498db", hover_color="#2980b9", command=save_selection).pack(
                side="right", padx=20
            )
        except:
            pass

    def open_settings(self):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsWindow(self)
        else:
            self.settings_window.focus()

    def open_rpc_settings(self):
        if self.rpc_settings_window is None or not self.rpc_settings_window.winfo_exists():
            self.rpc_settings_window = RPCSettingsWindow(self)
        else:
            self.rpc_settings_window.focus()

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    s = json.load(f)
                    self.tmdb_api_key = s.get("api_key", "")
                    self.show_path = s.get("show_path", self.show_path)
                    self.movie_path = s.get("movie_path", self.movie_path)
                    self.history = s.get("history", [])
                    self.discord_webhook = s.get("discord_webhook", "")
                    self.jellyfin_url = s.get("jellyfin_url", "")
                    self.jellyfin_api_key = s.get("jellyfin_api_key", "")
                    self.current_accent = "Blue" # Force blue
                    self.quality_var.set(s.get("quality", "1080p"))
                    self.video_only_var.set(s.get("video_only", False))
                    self.open_folder_var.set(s.get("open_folder", True))
                    self.show_jellyfin_var.set(s.get("show_jellyfin", True))
                    self.rpc_enabled = s.get("rpc_enabled", False)
                    self.rpc_client_id = s.get("rpc_client_id", "")
                    self.rpc_target_user = s.get("rpc_target_user", "")
                    self.rpc_show_time = s.get("rpc_show_time", True)
                    self.rpc_show_server = s.get("rpc_show_server", True)
                    self.toggle_jellyfin_ui()
                    self.render_history()
            except:
                pass

    def save_settings(self):
        try:
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
                "open_folder": self.open_folder_var.get(),
                "show_jellyfin": self.show_jellyfin_var.get(),
                "rpc_enabled": self.rpc_enabled,
                "rpc_client_id": self.rpc_client_id,
                "rpc_target_user": self.rpc_target_user,
                "rpc_show_time": self.rpc_show_time,
                "rpc_show_server": self.rpc_show_server,
            }
            with open(self.config_file, "w") as f:
                json.dump(data, f)
        except:
            pass
