import customtkinter as ctk
from tkinter import messagebox
from core.config_manager import config


class JellyfinDashboard(ctk.CTkToplevel):
    lbl_jelly_info: ctk.CTkLabel
    lbl_jelly_streams: ctk.CTkLabel
    lbl_storage_info: ctk.CTkLabel
    storage_prog: ctk.CTkProgressBar

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Jellyfin Dashboard")
        self.geometry("700x950")
        self.minsize(600, 800)
        self.attributes("-topmost", True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.current_watched_items = []
        self.selected_items = set()
        self.item_checkboxes = {}
        self.group_checkboxes = {}
        self.current_visible_ids = set()
        self.current_show_filter = None

        self.setup_ui_layout()

        self.refresh_ui()
        self.after(200, self.scan_watched)
        if self.app.last_missing_episodes:
            self.after(300, lambda: self.display_gaps(self.app.last_missing_episodes))

    def setup_ui_layout(self):
        for child in self.winfo_children():
            getattr(child, "grid_forget", lambda: None)()
            getattr(child, "pack_forget", lambda: None)()

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 10))
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="Jellyfin Server Status",
            font=("Segoe UI", 28, "bold"),
            text_color="#3498db",
        )
        self.lbl_title.grid(row=0, column=0, sticky="w")

        self.stats_frame = ctk.CTkFrame(
            self, corner_radius=0, border_width=0, fg_color=("#ebebeb", "#1a1a1a")
        )
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=30, pady=10)
        self.stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        def create_stat(parent, row, col, label, val_attr):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=row, column=col, sticky="nsew", padx=10, pady=15)
            ctk.CTkLabel(
                f, text=label, font=("Segoe UI", 11, "bold"), text_color="gray"
            ).pack()
            lbl = ctk.CTkLabel(f, text="...", font=("Segoe UI", 15, "bold"))
            lbl.pack()
            setattr(self, val_attr, lbl)
            return f

        create_stat(self.stats_frame, 0, 0, "CONNECTION", "lbl_jelly_info")
        create_stat(self.stats_frame, 0, 1, "ACTIVE STREAMS", "lbl_jelly_streams")
        create_stat(self.stats_frame, 0, 2, "SERVER STORAGE", "lbl_storage_info")

        self.storage_prog = ctk.CTkProgressBar(
            self.stats_frame, height=8, corner_radius=4, progress_color="#3498db"
        )
        self.storage_prog.grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 15)
        )
        self.storage_prog.set(0)

        self.tabview = ctk.CTkTabview(self, segmented_button_selected_color="#3498db")
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=30, pady=10)

        self.tab_streams = self.tabview.add("Active Streams")
        self.tab_gaps = self.tabview.add("Missing Episodes")
        self.tab_watched = self.tabview.add("Watched & Cleanup")

        self.tab_streams.grid_columnconfigure(0, weight=1)
        self.tab_streams.grid_rowconfigure(0, weight=1)
        self.streams_scroll = ctk.CTkScrollableFrame(
            self.tab_streams, fg_color="transparent"
        )
        self.streams_scroll.grid(row=0, column=0, sticky="nsew")

        self.tab_gaps.grid_columnconfigure(0, weight=1)
        self.tab_gaps.grid_rowconfigure(1, weight=1)

        gaps_ctrl = ctk.CTkFrame(self.tab_gaps, fg_color="transparent")
        gaps_ctrl.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.btn_scan_gaps = ctk.CTkButton(
            gaps_ctrl,
            text="🔍 SCAN FOR GAPS",
            fg_color="#3498db",
            font=("Segoe UI", 12, "bold"),
            command=self.scan_gaps,
        )
        self.btn_scan_gaps.pack(side="left", padx=5)
        self.lbl_scan_progress = ctk.CTkLabel(
            gaps_ctrl, text="", font=("Segoe UI", 11), text_color="gray"
        )
        self.lbl_scan_progress.pack(side="left", padx=10)
        self.gaps_scroll = ctk.CTkScrollableFrame(self.tab_gaps, fg_color="transparent")
        self.gaps_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.watched_container = ctk.CTkFrame(self.tab_watched, fg_color="transparent")
        self.watched_container.pack(fill="both", expand=True)
        self.watched_container.grid_columnconfigure(0, weight=1)
        self.watched_container.grid_rowconfigure(3, weight=1)

        self.retention_frame = ctk.CTkFrame(
            self.watched_container, fg_color=("#f9f9f9", "#151515"), corner_radius=8
        )
        self.retention_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15), padx=5)
        ctk.CTkLabel(
            self.retention_frame,
            text="AUTOMATED RETENTION POLICIES",
            font=("Segoe UI", 12, "bold"),
            text_color="#3498db",
        ).pack(pady=5)

        policy_inputs = ctk.CTkFrame(self.retention_frame, fg_color="transparent")
        policy_inputs.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(policy_inputs, text="Target User:", font=("Segoe UI", 11)).grid(
            row=0, column=0, padx=5, sticky="e"
        )
        self.retention_user = ctk.CTkEntry(
            policy_inputs, placeholder_text="Username", width=120, height=28
        )
        self.retention_user.grid(row=0, column=1, padx=5)
        self.retention_user.insert(0, config.get("retention_target_user", ""))

        ctk.CTkLabel(policy_inputs, text="Min Free GB:", font=("Segoe UI", 11)).grid(
            row=0, column=2, padx=5, sticky="e"
        )
        self.retention_free = ctk.CTkEntry(
            policy_inputs, placeholder_text="50", width=60, height=28
        )
        self.retention_free.grid(row=0, column=3, padx=5)
        self.retention_free.insert(0, str(config.get("retention_free_space_gb", 50)))

        self.btn_run_policies = ctk.CTkButton(
            self.retention_frame,
            text="⚡ RUN CLEANUP POLICIES",
            height=35,
            fg_color="#e67e22",
            hover_color="#d35400",
            font=("Segoe UI", 12, "bold"),
            command=self.run_policies,
        )
        self.btn_run_policies.pack(pady=10, padx=20, fill="x")

        self.watched_header = ctk.CTkFrame(
            self.watched_container, fg_color="transparent"
        )
        self.watched_header.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            self.watched_header, text="WATCHED CONTENT", font=("Segoe UI", 14, "bold")
        ).pack(side="left")
        self.btn_check_watched = ctk.CTkButton(
            self.watched_header,
            text="🔍 REFRESH SCAN",
            width=140,
            height=32,
            fg_color="#3498db",
            hover_color="#2980b9",
            font=("Segoe UI", 12, "bold"),
            command=self.scan_watched,
        )
        self.btn_check_watched.pack(side="right")

        self.filter_var = ctk.StringVar(value="All")
        self.filter_segmented = ctk.CTkSegmentedButton(
            self.watched_header,
            values=["All", "Movies", "Shows"],
            variable=self.filter_var,
            command=self.on_filter_changed,
            height=32,
            fg_color=("#ebebeb", "#2b2b2b"),
            selected_color="#3498db",
            selected_hover_color="#2980b9",
            font=("Segoe UI", 11, "bold"),
        )
        self.filter_segmented.pack(side="right", padx=15)

        self.selection_bar = ctk.CTkFrame(
            self.watched_container, fg_color="transparent"
        )
        self.selection_bar.grid(row=2, column=0, sticky="ew")

        self.watched_scroll = ctk.CTkScrollableFrame(
            self.watched_container,
            fg_color=("#f0f0f0", "#111111"),
            corner_radius=0,
            border_width=0,
        )
        self.watched_scroll.grid(row=3, column=0, sticky="nsew")

        self.footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=3, column=0, sticky="ew", padx=30, pady=20)
        self.footer_frame.grid_columnconfigure(0, weight=1)

        self.btn_close = ctk.CTkButton(
            self.footer_frame,
            text="CLOSE DASHBOARD",
            height=45,
            fg_color="#3498db",
            text_color="white",
            hover_color="#2980b9",
            font=("Segoe UI", 13, "bold"),
            command=self.destroy,
        )
        self.btn_close.grid(row=0, column=0, sticky="ew")

    def run_policies(self):
        user = self.retention_user.get().strip()
        if not user:
            messagebox.showwarning(
                "Input Required",
                "Please enter a Target User to run retention policies.\n\nThis user is used to identify watched content for deletion.",
                parent=self,
            )
            return

        free_gb = 50
        try:
            free_gb = int(self.retention_free.get())
        except:
            pass

        if messagebox.askyesno(
            "Confirm Cleanup",
            f"Run retention policies now?\n\nTarget User: {user}\nMin Free Space: {free_gb}GB\n\nThis may permanently delete watched items!",
            parent=self,
        ):
            self.btn_run_policies.configure(state="disabled", text="RUNNING CLEANUP...")
            self.app.run_async(
                self.app.jellyfin_api.execute_policies(
                    user, free_gb, on_complete=self.on_policies_complete
                )
            )
            config.set("retention_target_user", user)
            config.set("retention_free_space_gb", free_gb)

    def on_policies_complete(self):
        if self.winfo_exists():
            self.btn_run_policies.configure(
                state="normal", text="⚡ RUN CLEANUP POLICIES"
            )
            self.scan_watched()

    def scan_gaps(self):
        if not self.winfo_exists():
            return
        self.btn_scan_gaps.configure(state="disabled", text="SCANNING...")
        for w in self.gaps_scroll.winfo_children():
            w.destroy()

        def on_p(c, t, n):
            if self.winfo_exists():
                self.lbl_scan_progress.configure(text=f"Checking {c}/{t}: {n}...")

        self.app.run_async(
            self.app.jellyfin_api.scan_missing_episodes(on_p, self.display_gaps)
        )

    def display_gaps(self, results):
        if not self.winfo_exists():
            return
        self.app.last_missing_episodes = results
        self.btn_scan_gaps.configure(state="normal", text="🔍 SCAN FOR GAPS")
        self.lbl_scan_progress.configure(
            text=f"Scan complete. Found gaps in {len(results)} shows."
        )
        for res in results:
            card = ctk.CTkFrame(
                self.gaps_scroll, fg_color=("#ffffff", "#1a1a1a"), corner_radius=8
            )
            card.pack(fill="x", pady=5, padx=5)
            card.grid_columnconfigure(0, weight=1)
            info_f = ctk.CTkFrame(card, fg_color="transparent")
            info_f.grid(row=0, column=0, sticky="nsew", padx=15, pady=10)
            ctk.CTkLabel(
                info_f, text=res["name"], font=("Segoe UI", 14, "bold"), anchor="w"
            ).pack(fill="x")
            gap_text = ""
            for s, eps in res["gaps"].items():
                gap_text += f"S{str(s).zfill(2)}: {eps}\n"
            ctk.CTkLabel(
                info_f,
                text=gap_text.strip(),
                font=("Consolas", 11),
                text_color="#3498db",
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=(5, 0))
            ctk.CTkButton(
                card,
                text="Queue Missing",
                width=120,
                height=32,
                fg_color="#3498db",
                hover_color="#2980b9",
                font=("Segoe UI", 12, "bold"),
                command=lambda r=res: self.queue_gaps(r),
            ).grid(row=0, column=1, padx=15)

    def queue_gaps(self, res):
        selection_map = {int(s): eps for s, eps in res["gaps"].items()}
        task_data = {
            "name": res["name"],
            "year": str(res["year"]),
            "tid": res["tid"],
            "mode": "TV Show",
            "selection_map": selection_map,
            "quality": self.app.quality_var.get(),
            "sub_only": self.app.sub_only_var.get(),
            "video_only": self.app.video_only_var.get(),
        }
        self.app.queue_manager.add_to_queue(task_data)
        messagebox.showinfo(
            "Queued", f"Missing episodes for '{res['name']}' added to queue."
        )

    def scan_watched(self):
        if not self.winfo_exists():
            return
        self.btn_check_watched.configure(state="disabled", text="SCANNING...")
        self.selected_items.clear()
        self.item_checkboxes.clear()
        self.current_show_filter = None
        self.selection_bar.grid_remove()
        self.watched_scroll.grid_remove()
        for w in self.watched_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.watched_scroll,
            text="Searching server for watched items...",
            font=("Segoe UI", 13, "italic"),
            text_color="gray",
        ).pack(pady=60)
        self.watched_scroll.grid()
        self.app.run_async(
            self.app.jellyfin_api.fetch_watched_content(self.display_watched)
        )

    def on_filter_changed(self, value):
        self.selected_items.clear()
        self.current_show_filter = None
        self.render_watched_items()
        self.update_selection_ui()

    def display_watched(self, items):
        if not self.winfo_exists():
            return
        self.btn_check_watched.configure(state="normal", text="🔍 REFRESH SCAN")
        self.current_watched_items = items
        self.render_watched_items()

    def render_watched_items(self):
        if not self.winfo_exists():
            return

        self.selection_bar.grid_remove()
        self.watched_scroll.grid_remove()
        for w in self.watched_scroll.winfo_children():
            w.destroy()

        items = self.current_watched_items
        if not items:
            ctk.CTkLabel(
                self.watched_scroll,
                text="No watched items found.\nGo watch something!",
                font=("Segoe UI", 15),
                justify="center",
            ).pack(pady=80)
            self.watched_scroll.grid()
            return

        filter_val = self.filter_var.get()
        self.item_checkboxes.clear()
        self.group_checkboxes.clear()
        self.current_visible_ids.clear()

        # Drill-down view: Single Show episodes
        if self.current_show_filter:
            # Add Back Button
            back_btn = ctk.CTkButton(
                self.watched_scroll,
                text=f"🔙 BACK TO {filter_val.upper()}",
                height=32,
                fg_color="transparent",
                text_color="#3498db",
                hover_color=("#ebebeb", "#2b2b2b"),
                font=("Segoe UI", 12, "bold"),
                anchor="w",
                command=self.clear_show_filter
            )
            back_btn.pack(fill="x", padx=10, pady=(10, 5))
            
            show_items = [i for i in items if i.get("SeriesName") == self.current_show_filter]
            for item in show_items:
                self.current_visible_ids.add(item["Id"])
                self.render_item_card(item)
            
            self.setup_selection_bar_content()
            self.selection_bar.grid()
            self.watched_scroll.grid()
            self.update_selection_ui()
            return

        # Regular view with grouping
        filtered_items = []
        if filter_val == "All":
            filtered_items = items
        elif filter_val == "Movies":
            filtered_items = [i for i in items if i["Type"] == "Movie"]
        elif filter_val == "Shows":
            filtered_items = [i for i in items if i["Type"] == "Episode"]

        if not filtered_items:
            ctk.CTkLabel(
                self.watched_scroll,
                text=f"No {filter_val.lower()} found.",
                font=("Segoe UI", 14),
                text_color="gray",
            ).pack(pady=80)
            self.watched_scroll.grid()
            return

        for item in filtered_items:
            self.current_visible_ids.add(item["Id"])

        # Grouping Logic
        movies = [i for i in filtered_items if i["Type"] == "Movie"]
        episodes = [i for i in filtered_items if i["Type"] == "Episode"]
        
        shows_groups = {}
        for ep in episodes:
            sname = ep.get("SeriesName") or "Unknown Series"
            if sname not in shows_groups:
                shows_groups[sname] = []
            shows_groups[sname].append(ep)

        # Render Movies
        for item in movies:
            self.render_item_card(item)
            
        # Render Show Groups
        for sname, eps in sorted(shows_groups.items()):
            self.render_show_group_card(sname, eps)

        self.setup_selection_bar_content()
        self.selection_bar.grid()
        self.watched_scroll.grid()
        self.update_selection_ui()

    def clear_show_filter(self):
        self.current_show_filter = None
        self.render_watched_items()

    def set_show_filter(self, sname):
        self.current_show_filter = sname
        self.render_watched_items()

    def render_item_card(self, item):
        item_id = item["Id"]
        card = ctk.CTkFrame(
            self.watched_scroll,
            fg_color=("#ffffff", "#1a1a1a"),
            corner_radius=0,
            border_width=0,
        )
        card.pack(fill="x", pady=1, padx=2)
        card.grid_columnconfigure(1, weight=1)
        
        cb_var = ctk.BooleanVar(value=item_id in self.selected_items)
        cb = ctk.CTkCheckBox(
            card,
            text="",
            width=24,
            variable=cb_var,
            command=lambda i=item_id, v=cb_var: self.toggle_selection(i, v),
            fg_color="#3498db",
            hover_color="#2980b9",
        )
        cb.grid(row=0, column=0, padx=(15, 5), pady=15, sticky="w")
        self.item_checkboxes[item_id] = cb
        
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        type_badge = "🎬" if item["Type"] == "Movie" else "📺"
        name_text = item["Name"]
        if item["Type"] == "Episode" and item.get("SeasonNumber") is not None:
            s = str(item.get("SeasonNumber")).zfill(2)
            e = str(item.get("EpisodeNumber")).zfill(2)
            name_text = f"S{s}E{e} - {name_text}"
            
        ctk.CTkLabel(
            info,
            text=f"{type_badge}  {name_text}",
            anchor="w",
            font=("Segoe UI", 15, "bold"),
            justify="left",
            wraplength=400,
        ).pack(fill="x")
        
        ctk.CTkLabel(
            info,
            text=f"Watched by: {', '.join(item['WatchedBy'])}",
            anchor="w",
            font=("Segoe UI", 11),
            text_color="#3498db",
        ).pack(fill="x", pady=(2, 0))
        
        ctk.CTkLabel(
            info,
            text=item["Path"],
            anchor="w",
            font=("Consolas", 10),
            text_color="gray",
            justify="left",
            wraplength=400,
        ).pack(fill="x", pady=(5, 0))
        
        ctk.CTkButton(
            card,
            text="🗑",
            width=38,
            height=38,
            fg_color="transparent",
            text_color="#e74c3c",
            hover_color=("#ffebec", "#2d1a1a"),
            font=("Segoe UI", 20),
            command=lambda i=item["Id"], n=item["Name"], r=card: self.confirm_delete(i, n, r),
        ).grid(row=0, column=2, padx=15, pady=10, sticky="e")

    def render_show_group_card(self, sname, episodes):
        ep_ids = [e["Id"] for e in episodes]
        card = ctk.CTkFrame(
            self.watched_scroll,
            fg_color=("#f9f9f9", "#151515"),
            corner_radius=4,
            border_width=1,
            border_color=("#e0e0e0", "#2b2b2b")
        )
        card.pack(fill="x", pady=4, padx=5)
        card.grid_columnconfigure(1, weight=1)
        
        # Checkbox selects all episodes
        all_selected = all(eid in self.selected_items for eid in ep_ids)
        cb_var = ctk.BooleanVar(value=all_selected)
        cb = ctk.CTkCheckBox(
            card,
            text="",
            width=24,
            variable=cb_var,
            command=lambda ids=ep_ids, v=cb_var: self.toggle_group_selection(ids, v),
            fg_color="#3498db",
            hover_color="#2980b9",
        )
        cb.grid(row=0, column=0, padx=(15, 5), pady=20, sticky="w")
        self.group_checkboxes[sname] = cb
        
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew", padx=10, pady=15)
        
        ctk.CTkLabel(
            info,
            text=f"📺 {sname}",
            anchor="w",
            font=("Segoe UI", 16, "bold"),
            text_color="#3498db"
        ).pack(fill="x")
        
        count = len(episodes)
        ctk.CTkLabel(
            info,
            text=f"{count} watched episode{'s' if count > 1 else ''}",
            anchor="w",
            font=("Segoe UI", 11),
            text_color="gray"
        ).pack(fill="x")
        
        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.grid(row=0, column=2, padx=15)
        
        ctk.CTkButton(
            btn_f,
            text="VIEW EPISODES",
            width=120,
            height=32,
            fg_color="#3498db",
            hover_color="#2980b9",
            font=("Segoe UI", 11, "bold"),
            command=lambda s=sname: self.set_show_filter(s)
        ).pack(pady=5)

    def toggle_group_selection(self, ep_ids, var):
        if var.get():
            for eid in ep_ids:
                self.selected_items.add(eid)
        else:
            for eid in ep_ids:
                self.selected_items.discard(eid)
        self.update_selection_ui()


    def setup_selection_bar_content(self):
        for w in self.selection_bar.winfo_children():
            w.destroy()
        self.check_all_var = ctk.BooleanVar(value=False)
        self.cb_all = ctk.CTkCheckBox(
            self.selection_bar,
            text="Select All",
            font=("Segoe UI", 12, "bold"),
            variable=self.check_all_var,
            command=self.toggle_select_all,
            fg_color="#3498db",
            hover_color="#2980b9",
        )
        self.cb_all.pack(side="left", padx=5)
        self.btn_delete_selected = ctk.CTkButton(
            self.selection_bar,
            text="🗑 DELETE SELECTED (0)",
            height=32,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            font=("Segoe UI", 12, "bold"),
            state="disabled",
            command=self.delete_selected,
        )
        self.btn_delete_selected.pack(side="right", padx=5)

    def toggle_select_all(self):
        is_selected = self.check_all_var.get()
        if is_selected:
            for item_id in self.current_visible_ids:
                self.selected_items.add(item_id)
            for cb in self.item_checkboxes.values():
                cb.select()
            for cb in self.group_checkboxes.values():
                cb.select()
        else:
            for item_id in self.current_visible_ids:
                self.selected_items.discard(item_id)
            for cb in self.item_checkboxes.values():
                cb.deselect()
            for cb in self.group_checkboxes.values():
                cb.deselect()
        self.update_selection_ui()

    def toggle_selection(self, item_id, var):
        if var.get():
            self.selected_items.add(item_id)
        else:
            self.selected_items.discard(item_id)
            self.check_all_var.set(False)
        self.update_selection_ui()

    def update_selection_ui(self):
        count = len(self.selected_items)
        if count > 0:
            self.btn_delete_selected.configure(
                state="normal", text=f"🗑 DELETE SELECTED ({count})"
            )
        else:
            self.btn_delete_selected.configure(
                state="disabled", text="🗑 DELETE SELECTED (0)"
            )
        
        if self.current_visible_ids and self.current_visible_ids.issubset(self.selected_items):
            self.check_all_var.set(True)
        else:
            self.check_all_var.set(False)


    def delete_selected(self):
        count = len(self.selected_items)
        if count == 0:
            return
        if messagebox.askyesno(
            "Confirm Batch Delete",
            f"Delete {count} items from server?\n\nThis will permanently delete the files!",
            parent=self,
        ):
            items_to_del = [
                i for i in self.current_watched_items if i["Id"] in self.selected_items
            ]
            self.btn_delete_selected.configure(state="disabled", text="DELETING...")

            def on_p(c, t):
                if self.winfo_exists():
                    self.btn_delete_selected.configure(text=f"DELETING ({c}/{t})...")

            self.app.run_async(
                self.app.jellyfin_api.delete_items_batch(
                    items_to_del, on_progress=on_p, on_complete=self.scan_watched
                )
            )

    def confirm_delete(self, item_id, name, row):
        if messagebox.askyesno(
            "Confirm Delete", f"Delete '{name}' from server?", parent=self
        ):

            def on_s():
                if self.winfo_exists() and row.winfo_exists():
                    row.destroy()

            self.app.run_async(
                self.app.jellyfin_api.delete_item_by_id(item_id, name, on_success=on_s)
            )

    def update_sessions_list(self):
        if not self.winfo_exists():
            return
        for w in self.streams_scroll.winfo_children():
            w.destroy()
        
        sessions = self.app.last_jelly_sessions
        managed_user = getattr(self.app, "jellyfin_managed_user", "")
        
        your_sessions = {}
        server_sessions = {}
        
        for sid, info in sessions.items():
            if managed_user and info["user"].lower() == managed_user.lower():
                your_sessions[sid] = info
            else:
                server_sessions[sid] = info

        if your_sessions:
            ctk.CTkLabel(
                self.streams_scroll,
                text="YOUR ACTIVITY",
                font=("Segoe UI", 12, "bold"),
                text_color="#3498db",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(10, 5))
            for sid, info in your_sessions.items():
                self.render_session_card(sid, info, is_managed=True)
        
        if server_sessions:
            ctk.CTkLabel(
                self.streams_scroll,
                text="SERVER ACTIVITY",
                font=("Segoe UI", 12, "bold"),
                text_color="gray",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(15, 5))
            for sid, info in server_sessions.items():
                self.render_session_card(sid, info, is_managed=False)

        if not sessions:
            ctk.CTkLabel(
                self.streams_scroll,
                text="No active streams.",
                font=("Segoe UI", 13, "italic"),
                text_color="gray",
            ).pack(pady=40)

    def render_session_card(self, sid, info, is_managed=False):
        card = ctk.CTkFrame(
            self.streams_scroll, fg_color=("#ffffff", "#1a1a1a"), corner_radius=8
        )
        card.pack(fill="x", pady=5, padx=5)
        card.grid_columnconfigure(0, weight=1)
        
        info_f = ctk.CTkFrame(card, fg_color="transparent")
        info_f.grid(row=0, column=0, sticky="nsew", padx=15, pady=10)
        
        ctk.CTkLabel(
            info_f, text=info["title"], font=("Segoe UI", 14, "bold"), anchor="w"
        ).pack(fill="x")
        
        ctk.CTkLabel(
            info_f,
            text=f"User: {info['user']} • Client: {info['client']}",
            font=("Segoe UI", 11),
            text_color="#3498db",
            anchor="w",
        ).pack(fill="x")

        # Remote Controls for Managed User
        if is_managed:
            ctrl_f = ctk.CTkFrame(info_f, fg_color="transparent")
            ctrl_f.pack(fill="x", pady=(8, 0))
            
            btn_style = {"width": 35, "height": 30, "font": ("Segoe UI", 12, "bold")}
            
            ctk.CTkButton(
                ctrl_f, text="⏯", **btn_style,
                command=lambda s=sid: self.app.run_async(self.app.jellyfin_api.send_command(s, "PlayPause"))
            ).pack(side="left", padx=2)
            
            ctk.CTkButton(
                ctrl_f, text="⏹", **btn_style, fg_color="#e74c3c", hover_color="#c0392b",
                command=lambda s=sid: self.app.run_async(self.app.jellyfin_api.send_command(s, "Stop"))
            ).pack(side="left", padx=2)
            
            ctk.CTkLabel(ctrl_f, text=" Vol: ", font=("Segoe UI", 11)).pack(side="left", padx=(10, 0))
            
            ctk.CTkButton(
                ctrl_f, text="-", width=25, height=30,
                command=lambda s=sid: self.app.run_async(self.app.jellyfin_api.send_command(s, "VolumeDown"))
            ).pack(side="left", padx=2)
            
            ctk.CTkButton(
                ctrl_f, text="+", width=25, height=30,
                command=lambda s=sid: self.app.run_async(self.app.jellyfin_api.send_command(s, "VolumeUp"))
            ).pack(side="left", padx=2)

        # Admin Controls (Kill)
        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.grid(row=0, column=1, padx=15)
        
        ctk.CTkButton(
            btn_f,
            text="Kill Now",
            width=80,
            height=28,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            font=("Segoe UI", 11, "bold"),
            command=lambda s=sid: self.app.run_async(self.app.jellyfin_api.kill_session(s)),
        ).pack(side="left", padx=5)
        
        if not is_managed:
            ctk.CTkButton(
                btn_f,
                text="5m Warning & Kill",
                width=130,
                height=28,
                fg_color="#e67e22",
                hover_color="#d35400",
                font=("Segoe UI", 11, "bold"),
                command=lambda s=sid: self.app.run_async(
                    self.app.jellyfin_api.timed_kill(
                        s, 5, "Admin: This stream will be terminated in 5 minutes for maintenance."
                    )
                ),
            ).pack(side="left", padx=5)

    def refresh_ui(self):
        status_text = self.app.lbl_jelly_info.cget("text")
        status_color = self.app.lbl_jelly_info.cget("text_color")
        self.lbl_jelly_info.configure(
            text=status_text.replace("Status: ", ""), text_color=status_color
        )
        self.lbl_jelly_streams.configure(
            text=self.app.lbl_jelly_streams.cget("text").replace("Active Streams: ", "")
        )
        self.lbl_storage_info.configure(
            text=self.app.lbl_storage_info.cget("text").replace("Storage: ", "")
        )
        self.storage_prog.set(self.app.storage_prog.get())
        self.update_sessions_list()
        self.lbl_title.configure(text_color="#3498db")
        self.btn_check_watched.configure(fg_color="#3498db")
        self.btn_close.configure(fg_color="#3498db", text_color="white")
        if hasattr(self, "cb_all") and self.cb_all:
            self.cb_all.configure(fg_color="#3498db", hover_color="#2980b9")
        for cb in self.item_checkboxes.values():
            cb.configure(fg_color="#3498db", hover_color="#2980b9")
        for card in self.watched_scroll.winfo_children():
            if isinstance(card, ctk.CTkFrame):
                for child in card.winfo_children():
                    if isinstance(child, ctk.CTkFrame):
                        for subchild in child.winfo_children():
                            if isinstance(subchild, ctk.CTkLabel) and subchild.cget(
                                "text"
                            ).startswith("Watched by:"):
                                subchild.configure(text_color="#3498db")
        if self.app.jellyfin_free_gb < 10:
            self.storage_prog.configure(progress_color="#e74c3c")
        elif self.app.jellyfin_free_gb < 30:
            self.storage_prog.configure(progress_color="#f39c12")
        else:
            self.storage_prog.configure(progress_color="#3498db")
