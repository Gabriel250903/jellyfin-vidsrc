import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
from PIL import Image
from typing import List, Any, Optional
from core.utils import resource_path


class SidebarMixin:
    def setup_sidebar(self: Any):
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

        # Brand Logo with Icon
        try:
            logo_path = resource_path("icon_sidebar.png")
            if not os.path.exists(logo_path):
                logo_path = "icon_sidebar.png"

            img = Image.open(logo_path)
            self.logo_image = ctk.CTkImage(img, size=(120, 120))
            self.logo_label = ctk.CTkLabel(
                self.sidebar,
                text="VidSrc Jellyfin",
                image=self.logo_image,
                compound="top",
                font=("Segoe UI", 24, "bold"),
                text_color="#3498db",
            )
        except Exception:
            self.logo_label = ctk.CTkLabel(
                self.sidebar,
                text="VidSrc Jellyfin",
                font=("Segoe UI", 24, "bold"),
                text_color="#3498db",
            )

        self.logo_label.grid(row=0, column=0, pady=(30, 15))

        self.mode_switch = ctk.CTkSegmentedButton(
            self.sidebar,
            values=["TV Show", "Movie"],
            command=lambda v: self.on_mode_change(v),
            height=40,
            font=("Segoe UI", 13, "bold"),
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
            cursor="hand2",
        )
        self.poster_label.grid(row=4, column=0, pady=15)
        self.poster_label.bind("<Button-1>", lambda e: self._on_preview_clicked())

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
            font=("Segoe UI", 13, "bold"),
            height=40,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_queue_window,
        )
        self.btn_queue.grid(row=8, column=0, sticky="ew", padx=20)

        self.btn_jelly_dashboard = ctk.CTkButton(
            self.sidebar,
            text="📺 JELLYFIN DASHBOARD",
            font=("Segoe UI", 13, "bold"),
            height=40,
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
            height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_rpc_settings,
        )
        self.btn_rpc_settings.pack(fill="x", padx=20, pady=5)
        self.btn_choose_root = ctk.CTkButton(
            self.bottom_sidebar,
            text="📁 Library Path",
            height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.choose_root,
        )
        self.btn_choose_root.pack(fill="x", padx=20, pady=5)
        self.btn_settings = ctk.CTkButton(
            self.bottom_sidebar,
            text="⚙ Settings",
            height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.open_settings,
        )
        self.btn_settings.pack(fill="x", padx=20, pady=5)

    def render_history(self: Any, event: Optional[Any] = None):
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

    def handle_history_delete(self: Any, item: Any):
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

    def clear_history(self: Any):
        try:
            self.history = []
            self.render_history()
            self.save_settings()
            self.log("UI: History cleared.")
        except:
            pass

    def choose_root(self: Any):
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

    def _on_preview_clicked(self: Any):
        if hasattr(self, "selected_tid") and self.selected_tid:
            cat = "tv" if self.mode_switch.get() == "TV Show" else "movie"
            item_data = {
                "id": self.selected_tid,
                "name" if cat == "tv" else "title": self.selected_name,
                "poster_path": self.selected_poster,
            }
            self.open_details(item_data, cat)
