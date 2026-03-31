import customtkinter as ctk
import json
import os
import threading


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Settings")
        self.geometry("500x850")

        self.minsize(450, 600)
        self.maxsize(450, 1250)
        self.attributes("-topmost", True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._is_resizing = False
        self._resize_timer = None

        self.setup_ui()
        self.bind("<Configure>", self._on_configure)

    def setup_ui(self):
        for child in self.winfo_children():
            child.grid_forget()
            child.pack_forget()

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=0, border_width=0)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.scroll, text="TMDB API KEY", font=("Segoe UI", 12, "bold")
        ).pack(pady=(10, 5), padx=20, anchor="w")
        self.api_entry = ctk.CTkEntry(self.scroll, width=400, show="*")
        self.api_entry.pack(pady=5, padx=20, fill="x")
        self.api_entry.insert(0, self.parent.tmdb_api_key)

        ctk.CTkLabel(self.scroll, text="Or select a public key:").pack(
            padx=20, anchor="w"
        )

        tmdb_keys = [
            "fb7bb23f03b6994dafc674c074d01761",
            "e55425032d3d0f371fc776f302e7c09b",
            "8301a21598f8b45668d5711a814f01f6",
            "8cf43ad9c085135b9479ad5cf6bbcbda",
            "da63548086e399ffc910fbc08526df05",
            "13e53ff644a8bd4ba37b3e1044ad24f3",
            "269890f657dddf4635473cf4cf456576",
            "a2f888b27315e62e471b2d587048f32e",
            "8476a7ab80ad76f0936744df0430e67c",
            "5622cafbfe8f8cfe358a29c53e19bba0",
            "ae4bd1b6fce2a5648671bfc171d15ba4",
            "257654f35e3dff105574f97fb4b97035",
            "2f4038e83265214a0dcd6ec2eb3276f5",
            "9e43f45f94705cc8e1d5a0400d19a7b7",
            "af6887753365e14160254ac7f4345dd2",
            "06f10fc8741a672af455421c239a1ffc",
            "09ad8ace66eec34302943272db0e8d2c",
        ]

        def set_key(val):
            if val != "Select a key...":
                self.api_entry.delete(0, "end")
                self.api_entry.insert(0, val)

        self.key_menu = ctk.CTkOptionMenu(
            self.scroll,
            values=["Select a key..."] + tmdb_keys,
            command=set_key,
            fg_color="#3498db",
            button_color="#3498db",
        )
        self.key_menu.pack(pady=5, padx=20, fill="x")
        self.key_menu.set("Select a key...")

        ctk.CTkLabel(
            self.scroll, text="DISCORD WEBHOOK", font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        self.discord_entry = ctk.CTkEntry(
            self.scroll, placeholder_text="https://discord.com/api/webhooks/..."
        )
        self.discord_entry.pack(pady=5, padx=20, fill="x")
        self.discord_entry.insert(0, self.parent.discord_webhook)

        self.j_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        if self.parent.show_jellyfin_var.get():
            self.j_frame.pack(fill="x")

        ctk.CTkLabel(
            self.j_frame, text="JELLYFIN INTEGRATION", font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        self.j_url = ctk.CTkEntry(self.j_frame, placeholder_text="Server URL")
        self.j_url.pack(pady=5, padx=20, fill="x")
        self.j_url.insert(0, self.parent.jellyfin_url)
        self.j_key = ctk.CTkEntry(self.j_frame, show="*", placeholder_text="API Key")
        self.j_key.pack(pady=5, padx=20, fill="x")
        self.j_key.insert(0, self.parent.jellyfin_api_key)

        ctk.CTkLabel(
            self.scroll, text="APPEARANCE", font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        
        ctk.CTkLabel(self.scroll, text="Theme:").pack(padx=20, anchor="w")
        theme_var = ctk.StringVar(value=ctk.get_appearance_mode())
        ctk.CTkOptionMenu(
            self.scroll,
            values=["Dark", "Light", "System"],
            variable=theme_var,
            command=lambda v: ctk.set_appearance_mode(v),
            fg_color="#3498db",
            button_color="#3498db",
        ).pack(pady=5, padx=20, fill="x")

        ctk.CTkLabel(
            self.scroll, text="DEFAULT QUALITY", font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        ctk.CTkOptionMenu(
            self.scroll,
            values=["1080p", "720p", "480p"],
            variable=self.parent.quality_var,
            fg_color="#3498db",
            button_color="#3498db",
        ).pack(pady=5, padx=20, fill="x")

        ctk.CTkLabel(
            self.scroll, text="INTEGRATIONS", font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        ctk.CTkSwitch(
            self.scroll,
            text="Open folder after download",
            variable=self.parent.open_folder_var,
            progress_color="#3498db",
        ).pack(pady=5, padx=20, anchor="w")
        ctk.CTkSwitch(
            self.scroll,
            text="Show Jellyfin features",
            variable=self.parent.show_jellyfin_var,
            command=self.parent.toggle_jellyfin_ui,
            progress_color="#3498db",
        ).pack(pady=5, padx=20, anchor="w")

        self.btn_save = ctk.CTkButton(
            self,
            text="SAVE SETTINGS",
            fg_color="#3498db",
            height=45,
            font=("Segoe UI", 14, "bold"),
            command=self.save,
        )
        self.btn_save.grid(row=1, column=0, sticky="ew", padx=20, pady=20)

    def _on_configure(self, event):
        if event.widget == self:
            if not self._is_resizing:
                self._is_resizing = True
                self.scroll.grid_remove()
                self.btn_save.grid_remove()

            if self._resize_timer:
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(300, self._stop_resize_flag)

    def _stop_resize_flag(self):
        self._is_resizing = False
        self._resize_timer = None
        self.scroll.grid()
        self.btn_save.grid()

    def save(self):
        self.parent.tmdb_api_key = self.api_entry.get()
        self.parent.discord_webhook = self.discord_entry.get().strip()
        self.parent.jellyfin_url = self.j_url.get().strip().rstrip("/")
        self.parent.jellyfin_api_key = self.j_key.get().strip()
        self.parent.save_settings()
        self.destroy()
