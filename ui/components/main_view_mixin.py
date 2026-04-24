import customtkinter as ctk
from tkinter import messagebox
import time
import os
import re
from core.config_manager import config
from core.utils import sanitize_path
from ui.components.item_card import ItemCard
from ui.jellyfin_dashboard import JellyfinDashboard
from ui.rpc_settings import RPCSettingsWindow
from ui.settings_window import SettingsWindow
from ui.details_window import DetailsWindow

from typing import List, Any, Optional

class MainViewMixin:
    def open_details(self: Any, item_data, cat):
        DetailsWindow(self, item_data, cat)

    def select_title(self: Any, name, year, tid, poster_path, save_hist=True, cat=None):
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
                    if not img:
                        return

                    def _do_config():
                        try:
                            if self.selected_tid != tid or not self.poster_label.winfo_exists():
                                return

                            new_img = ctk.CTkImage(
                                light_image=img, dark_image=img, size=(240, 340)
                            )
                            
                            if not hasattr(self, "_img_buffer"):
                                self._img_buffer = []
                            
                            if hasattr(self, "current_poster_ptr") and self.current_poster_ptr:
                                self._img_buffer.append(self.current_poster_ptr)
                                if len(self._img_buffer) > 5:
                                    self._img_buffer.pop(0)

                            self.current_poster_ptr = new_img
                            self.poster_label.configure(
                                image=new_img,
                                text=" ",
                                text_color=self.poster_label.cget("fg_color"),
                                compound="center"
                            )
                            try:
                                if hasattr(self.poster_label, "_label"):
                                    self.poster_label._label.configure(text="", foreground=self.poster_label.cget("fg_color")[1])
                            except:
                                pass
                        except Exception as e:
                            if "doesn't exist" not in str(e):
                                self.log(f"UI ERROR: Failed to load poster: {e}")

                    self.after(10, _do_config)

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
        except Exception as e:
            self.log(f"UI ERROR in select_title: {e}")

    def get_existing_episodes(self: Any, name, year):
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

    def setup_main_view(self: Any):
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

        self.tab_discover = self.tabview.add("Discover")
        self.tab_search = self.tabview.add("Search")
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

    def setup_discover_tab(self: Any):
        self.discover_page = 1
        self.discover_total_pages = 1
        self.loading_more = False
        self.all_discover_results = []
        self.discover_cards = []
        self._genres_cache = {"movie": [], "tv": []}
        self._genre_map = {}

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

        self.genre_filter = ctk.CTkComboBox(
            ctrl_f,
            values=["All Genres"],
            command=lambda v: self.refresh_discover(),
            width=200,
            state="readonly",
        )
        self.genre_filter.pack(side="left", padx=10)
        self.genre_filter.set("All Genres")

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

    def _update_genre_dropdown(self: Any):
        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"
        if self._genres_cache[cat]:
            self._populate_genres(self._genres_cache[cat])
        else:
            self.run_async(self.tmdb_api.fetch_genres(cat), self._on_genres_loaded)

    def _on_genres_loaded(self: Any, genres):
        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"
        self._genres_cache[cat] = genres
        self.after(0, lambda: self._populate_genres(genres))

    def _populate_genres(self: Any, genres):
        self._genre_map = {g["name"]: g["id"] for g in genres}
        genre_names = ["All Genres"] + sorted(self._genre_map.keys())
        self.genre_filter.configure(values=genre_names)
        if self.genre_filter.get() not in genre_names:
            self.genre_filter.set("All Genres")

    def _check_discover_scroll(self: Any):
        try:
            if self.tabview.get() == "Discover":
                self._on_discover_scroll()
        except:
            pass
        self.after(1000, self._check_discover_scroll)

    def _get_discover_columns(self: Any):
        try:
            width = self.discover_container.winfo_width()
            if width < 400:
                width = 1100
            return max(1, (width - 40) // 200)
        except:
            return 5

    def _update_discover_footer(self: Any):
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

    def _on_discover_scroll(self: Any, event=None):
        if self.loading_more or self.discover_page >= self.discover_total_pages:
            return

        try:
            pos = self.discover_container._parent_canvas.yview()
            if pos[1] > 0.8:
                self.load_more_discover()
        except:
            pass

    def load_more_discover(self: Any):
        if self.loading_more:
            return
        self.loading_more = True
        self.discover_page += 1
        self._update_discover_footer()

        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"
        genre_name = self.genre_filter.get()
        genre_id = self._genre_map.get(genre_name)

        if genre_id:
            self.run_async(
                self.tmdb_api.fetch_discover(cat, page=self.discover_page, genre_id=genre_id),
                self._append_discover_results,
            )
        elif self.disc_type.get() == "Trending":
            self.run_async(
                self.tmdb_api.fetch_trending(cat, page=self.discover_page),
                self._append_discover_results,
            )
        else:
            self.run_async(
                self.tmdb_api.fetch_popular(cat, page=self.discover_page),
                self._append_discover_results,
            )

    def _append_discover_results(self: Any, data):
        results, posters, total_pages = data
        self.discover_total_pages = total_pages
        self.all_discover_results.extend(results)
        cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"

        def _ui_render():
            columns = self._get_discover_columns()
            
            for i in range(10):
                self.discover_container.grid_columnconfigure(i, weight=0)
            for i in range(columns):
                self.discover_container.grid_columnconfigure(i, weight=1)

            for i, item in enumerate(results):
                card = ItemCard(self.discover_container, self)
                self.discover_cards.append(card)
                poster_pil = posters[i] if posters and i < len(posters) else None
                card.update_data(item, cat, poster_pil)

            for i, card in enumerate(self.discover_cards):
                card.grid(
                    row=i // columns,
                    column=i % columns,
                    padx=10,
                    pady=10,
                    sticky="nsew",
                )

            self.loading_more = False
            self._update_discover_footer()

        self.after(0, _ui_render)

    def refresh_discover(self: Any):
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

        genre_name = self.genre_filter.get()
        genre_id = self._genre_map.get(genre_name)

        if genre_id:
            if self.disc_type.get() == "Trending":
                self.disc_type.set("Popular")
            self.run_async(
                self.tmdb_api.fetch_discover(cat, genre_id=genre_id), self._render_discover_first_page
            )
        elif self.disc_type.get() == "Trending":
            self.run_async(
                self.tmdb_api.fetch_trending(cat), self._render_discover_first_page
            )
        else:
            self.run_async(
                self.tmdb_api.fetch_popular(cat), self._render_discover_first_page
            )
        
        self._update_genre_dropdown()

    def _render_discover_first_page(self: Any, data):
        results, posters, total_pages = data
        self.discover_total_pages = total_pages
        self.all_discover_results = results.copy()
        self._render_discover(
            results, "tv" if self.mode_switch.get() == "TV Show" else "movie", posters
        )

    def _render_discover(self: Any, results, cat, posters=None):
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

    def update_task_status(self: Any, task_id, status, progress=None, retry=0):
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
            
            final_states = ["FINISHED", "NOT FOUND", "ALREADY FOUND", "SKIPPED", "CANCELED", "FAILED"]
            
            if status in final_states:
                if not t.get("done"):
                    t["done"] = True
                    
                    if status == "FINISHED":
                        t["stat"].configure(text_color="#2ecc71")
                    elif status == "ALREADY FOUND":
                        t["stat"].configure(text_color="#f1c40f")
                    elif status in ["NOT FOUND", "SKIPPED"]:
                        t["stat"].configure(text_color="#e67e22")
                    elif status in ["CANCELED", "FAILED"]:
                        t["stat"].configure(text_color="#e74c3c")
                
                if status not in ["CANCELED", "FAILED"]:
                    t["progress_val"] = 1.0
                    t["prog"].set(1.0)
                    
            elif progress is not None:
                t["progress_val"] = progress
                t["prog"].set(progress)

        self.after(0, _ui_action)

    def add_task_ui(self: Any, task_id, folder=None, display_name=None):
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

    def clear_finished_tasks(self: Any):
        try:
            for tid in list(self.active_tasks.keys()):
                if self.active_tasks[tid]["done"]:
                    self.active_tasks[tid]["row"].destroy()
                    del self.active_tasks[tid]
            self.log("UI: Cleared finished tasks.")
            self.after(10, lambda: self.task_monitor._parent_canvas.yview_moveto(0.0))
        except Exception as e:
            self.log(f"ERROR clearing tasks: {e}")

    def start_process(self: Any):
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

    def stop_process(self: Any):
        self.controller.stop_process()
        self.btn_run.configure(state="normal")

    def clear_finished_tasks_ui(self: Any):
        for tid in list(self.active_tasks.keys()):
            if self.active_tasks[tid]["done"]:
                self.active_tasks[tid]["row"].destroy()
                del self.active_tasks[tid]

    def show_missing_links(self: Any):
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

    def open_queue_window(self: Any):
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

    def open_jellyfin_dashboard(self: Any):
        if self.jelly_dashboard is None or not self.jelly_dashboard.winfo_exists():
            self.jelly_dashboard = JellyfinDashboard(self)
        else:
            self.jelly_dashboard.focus()

    def on_mode_change(self: Any, v):
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
        
        try:
            if not hasattr(self, "_img_buffer"):
                self._img_buffer = []
            
            if hasattr(self, "current_poster_ptr") and self.current_poster_ptr:
                self._img_buffer.append(self.current_poster_ptr)
                if len(self._img_buffer) > 5:
                    self._img_buffer.pop(0)

            if hasattr(self, "poster_label") and self.poster_label.winfo_exists():
                self.poster_label.configure(image=None, text="No Preview")
        except Exception as e:
            self.log(f"UI ERROR in on_mode_change: {e}")
            
        self.current_poster_ptr = None

    def open_ep_selector(self: Any):
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

    def open_settings(self: Any):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsWindow(self)
        else:
            self.settings_window.focus()

    def open_rpc_settings(self: Any):
        if (
            self.rpc_settings_window is None
            or not self.rpc_settings_window.winfo_exists()
        ):
            self.rpc_settings_window = RPCSettingsWindow(self)
        else:
            self.rpc_settings_window.focus()

    def toggle_jellyfin_ui(self: Any, *args):
        try:
            if self.show_jellyfin_var.get():
                self.btn_jelly_dashboard.grid()
            else:
                self.btn_jelly_dashboard.grid_forget()
            self.save_settings()
        except:
            pass

    def render_results(self: Any, results, cat, posters=None):
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

    def show_search_loading(self: Any):
        for w in self.results_container.winfo_children():
            getattr(w, "grid_remove", lambda: None)()
        self.results_container.pack(
            fill="both", expand=True, padx=10, before=self.exec_frame
        )
        self.tabview.set("Search")
