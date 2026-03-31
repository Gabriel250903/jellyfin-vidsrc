import customtkinter as ctk
from tkinter import messagebox


class JellyfinDashboard(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Jellyfin Dashboard")
        self.geometry("700x900")
        self.minsize(600, 700)
        self.attributes("-topmost", True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        self.current_watched_items = []
        self.selected_items = set()
        self.item_checkboxes = {}
        
        self.setup_ui_layout()
        
        self.refresh_ui()
        self.after(200, self.scan_watched)
        
        self._is_resizing = False
        self._resize_timer = None
        self.bind("<Configure>", self._on_configure)

    def setup_ui_layout(self):
        # Clear existing to allow re-layout
        for child in self.winfo_children():
            child.grid_forget()
            child.pack_forget()

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

        self.stats_frame = ctk.CTkFrame(self, corner_radius=0, border_width=0, fg_color=("#ebebeb", "#1a1a1a"))
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=30, pady=10)
        self.stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        def create_stat(parent, row, col, label, val_attr):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=row, column=col, sticky="nsew", padx=10, pady=15)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 11, "bold"), text_color="gray").pack()
            lbl = ctk.CTkLabel(f, text="...", font=("Segoe UI", 15, "bold"))
            lbl.pack()
            setattr(self, val_attr, lbl)
            return f

        create_stat(self.stats_frame, 0, 0, "CONNECTION", "lbl_jelly_info")
        create_stat(self.stats_frame, 0, 1, "ACTIVE STREAMS", "lbl_jelly_streams")
        create_stat(self.stats_frame, 0, 2, "SERVER STORAGE", "lbl_storage_info")

        self.storage_prog = ctk.CTkProgressBar(self.stats_frame, height=8, corner_radius=4, progress_color="#3498db")
        self.storage_prog.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 15))
        self.storage_prog.set(0)

        self.watched_container = ctk.CTkFrame(self, fg_color="transparent")
        self.watched_container.grid(row=2, column=0, sticky="nsew", padx=30, pady=10)
        self.watched_container.grid_columnconfigure(0, weight=1)
        self.watched_container.grid_rowconfigure(2, weight=1)

        self.watched_header = ctk.CTkFrame(self.watched_container, fg_color="transparent")
        self.watched_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(self.watched_header, text="WATCHED CONTENT", font=("Segoe UI", 14, "bold")).pack(side="left")
        self.btn_check_watched = ctk.CTkButton(
            self.watched_header, text="🔍 REFRESH SCAN", width=140, height=32,
            fg_color="#3498db", hover_color="#2980b9", font=("Segoe UI", 12, "bold"),
            command=self.scan_watched
        )
        self.btn_check_watched.pack(side="right")

        self.selection_bar = ctk.CTkFrame(self.watched_container, fg_color="transparent")
        self.selection_bar.grid(row=1, column=0, sticky="ew")

        self.watched_scroll = ctk.CTkScrollableFrame(
            self.watched_container, fg_color=("#f0f0f0", "#111111"), 
            corner_radius=0, border_width=0
        )
        self.watched_scroll.grid(row=2, column=0, sticky="nsew")

        self.footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=3, column=0, sticky="ew", padx=30, pady=20)
        self.footer_frame.grid_columnconfigure(0, weight=1)

        self.btn_close = ctk.CTkButton(
            self.footer_frame, text="CLOSE DASHBOARD", height=45,
            fg_color="#3498db", text_color="white",
            hover_color="#2980b9", font=("Segoe UI", 13, "bold"),
            command=self.destroy
        )
        self.btn_close.grid(row=0, column=0, sticky="ew")

    def _on_configure(self, event):
        """Throttle UI drawing during resize for smooth window movement."""
        if event.widget == self:
            if not self._is_resizing:
                self._is_resizing = True
                self.header_frame.grid_remove()
                self.stats_frame.grid_remove()
                self.watched_container.grid_remove()
                self.footer_frame.grid_remove()
            
            if self._resize_timer:
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(400, self._stop_resize_flag)

    def _stop_resize_flag(self):
        self._is_resizing = False
        self._resize_timer = None
        self.header_frame.grid()
        self.stats_frame.grid()
        self.watched_container.grid()
        self.footer_frame.grid()

    def scan_watched(self):
        self.btn_check_watched.configure(state="disabled", text="SCANNING...")
        self.selected_items.clear()
        self.item_checkboxes.clear()
        
        self.selection_bar.grid_remove()
        self.watched_scroll.grid_remove()

        for w in self.watched_scroll.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self.watched_scroll, text="Searching server for watched items...",
            font=("Segoe UI", 13, "italic"), text_color="gray"
        ).pack(pady=60)
        
        self.watched_scroll.grid()

        self.app.jellyfin_api.fetch_watched_content(self.display_watched)

    def display_watched(self, items):
        self.btn_check_watched.configure(state="normal", text="🔍 REFRESH SCAN")
        self.current_watched_items = items

        self.selection_bar.grid_remove()
        self.watched_scroll.grid_remove()

        for w in self.watched_scroll.winfo_children():
            w.destroy()

        if not items:
            ctk.CTkLabel(
                self.watched_scroll, text="No watched items found.\nGo watch something!",
                font=("Segoe UI", 15), justify="center"
            ).pack(pady=80)
            self.watched_scroll.grid()
            return

        self.setup_selection_bar_content()
        self.selection_bar.grid()
        self.watched_scroll.grid()

        for item in items:
            item_id = item["Id"]
            card = ctk.CTkFrame(self.watched_scroll, fg_color=("#ffffff", "#1a1a1a"), corner_radius=0, border_width=0)
            card.pack(fill="x", pady=1, padx=2)
            card.grid_columnconfigure(1, weight=1)

            cb_var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(card, text="", width=24, variable=cb_var, command=lambda i=item_id, v=cb_var: self.toggle_selection(i, v), fg_color="#3498db", hover_color="#2980b9")
            cb.grid(row=0, column=0, padx=(15, 5), pady=15, sticky="w")
            self.item_checkboxes[item_id] = cb

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
            
            type_badge = "🎬" if item["Type"] == "Movie" else "📺"
            title_lbl = ctk.CTkLabel(info, text=f"{type_badge}  {item['Name']}", anchor="w", font=("Segoe UI", 15, "bold"), justify="left", wraplength=450)
            title_lbl.pack(fill="x")

            ctk.CTkLabel(info, text=f"Watched by: {', '.join(item['WatchedBy'])}", anchor="w", font=("Segoe UI", 11), text_color="#3498db").pack(fill="x", pady=(2, 0))

            path_lbl = ctk.CTkLabel(info, text=item['Path'], anchor="w", font=("Consolas", 10), text_color="gray", justify="left", wraplength=450)
            path_lbl.pack(fill="x", pady=(5, 0))

            ctk.CTkButton(card, text="🗑", width=38, height=38, fg_color="transparent", text_color="#e74c3c", hover_color=("#ffebec", "#2d1a1a"), font=("Segoe UI", 20), command=lambda i=item["Id"], n=item["Name"], r=card: self.confirm_delete(i, n, r)).grid(row=0, column=2, padx=15, pady=10, sticky="e")

    def setup_selection_bar_content(self):
        for w in self.selection_bar.winfo_children():
            w.destroy()

        self.check_all_var = ctk.BooleanVar(value=False)
        self.cb_all = ctk.CTkCheckBox(self.selection_bar, text="Select All Watched", font=("Segoe UI", 12, "bold"), variable=self.check_all_var, command=self.toggle_select_all, fg_color="#3498db", hover_color="#2980b9")
        self.cb_all.pack(side="left", padx=5)

        self.btn_delete_selected = ctk.CTkButton(self.selection_bar, text="🗑 DELETE SELECTED (0)", height=32, fg_color="#e74c3c", hover_color="#c0392b", font=("Segoe UI", 12, "bold"), state="disabled", command=self.delete_selected)
        self.btn_delete_selected.pack(side="right", padx=5)

    def toggle_select_all(self):
        is_selected = self.check_all_var.get()
        if is_selected:
            for item in self.current_watched_items:
                self.selected_items.add(item['Id'])
                if item['Id'] in self.item_checkboxes: self.item_checkboxes[item['Id']].select()
        else:
            self.selected_items.clear()
            for cb in self.item_checkboxes.values(): cb.deselect()
        self.update_selection_ui()

    def toggle_selection(self, item_id, var):
        if var.get(): self.selected_items.add(item_id)
        else:
            self.selected_items.discard(item_id)
            self.check_all_var.set(False)
        self.update_selection_ui()

    def update_selection_ui(self):
        count = len(self.selected_items)
        if count > 0: self.btn_delete_selected.configure(state="normal", text=f"🗑 DELETE SELECTED ({count})")
        else: self.btn_delete_selected.configure(state="disabled", text="🗑 DELETE SELECTED (0)")
        if count > 0 and count == len(self.current_watched_items): self.check_all_var.set(True)

    def delete_selected(self):
        count = len(self.selected_items)
        if count == 0: return
        if messagebox.askyesno("Confirm Batch Delete", f"Delete {count} items from server?\n\nThis will permanently delete the files!", parent=self):
            items_to_del = [i for i in self.current_watched_items if i["Id"] in self.selected_items]
            self.btn_delete_selected.configure(state="disabled", text="DELETING...")
            self.app.jellyfin_api.delete_items_batch(items_to_del, on_progress=lambda curr, tot: self.btn_delete_selected.configure(text=f"DELETING ({curr}/{tot})..."), on_complete=self.scan_watched)

    def confirm_delete(self, item_id, name, row):
        if messagebox.askyesno("Confirm Delete", f"Delete '{name}' from server?", parent=self):
            self.app.jellyfin_api.delete_item_by_id(item_id, name, on_success=lambda: row.destroy())

    def refresh_ui(self):
        status_text = self.app.lbl_jelly_info.cget("text")
        status_color = self.app.lbl_jelly_info.cget("text_color")
        self.lbl_jelly_info.configure(text=status_text.replace("Status: ", ""), text_color=status_color)
        self.lbl_jelly_streams.configure(text=self.app.lbl_jelly_streams.cget("text").replace("Active Streams: ", ""))
        self.lbl_storage_info.configure(text=self.app.lbl_storage_info.cget("text").replace("Storage: ", ""))
        self.storage_prog.set(self.app.storage_prog.get())
        
        self.lbl_title.configure(text_color="#3498db")
        self.btn_check_watched.configure(fg_color="#3498db")
        self.btn_close.configure(fg_color="#3498db", text_color="white")

        if hasattr(self, "cb_all") and self.cb_all: self.cb_all.configure(fg_color="#3498db", hover_color="#2980b9")
        for cb in self.item_checkboxes.values(): cb.configure(fg_color="#3498db", hover_color="#2980b9")
        for card in self.watched_scroll.winfo_children():
            if isinstance(card, ctk.CTkFrame):
                for child in card.winfo_children():
                    if isinstance(child, ctk.CTkFrame):
                        for subchild in child.winfo_children():
                            if isinstance(subchild, ctk.CTkLabel) and subchild.cget("text").startswith("Watched by:"): subchild.configure(text_color="#3498db")
        
        if self.app.jellyfin_free_gb < 10: self.storage_prog.configure(progress_color="#e74c3c")
        elif self.app.jellyfin_free_gb < 30: self.storage_prog.configure(progress_color="#f39c12")
        else: self.storage_prog.configure(progress_color="#3498db")
