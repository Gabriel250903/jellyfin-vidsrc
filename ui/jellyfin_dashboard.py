import customtkinter as ctk


class JellyfinDashboard(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Jellyfin Dashboard")
        self.geometry("500x600")
        self.attributes("-topmost", True)

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Jellyfin Server Status",
            font=("Segoe UI", 20, "bold"),
            text_color="#3498db",
        ).pack(pady=20)

        mon_frame = ctk.CTkFrame(self, fg_color="transparent")
        mon_frame.pack(fill="both", expand=True, padx=30)

        ctk.CTkLabel(
            mon_frame, text="SERVER CONNECTION", font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        self.lbl_jelly_info = ctk.CTkLabel(
            mon_frame, text="Status: Checking...", font=("Segoe UI", 13)
        )
        self.lbl_jelly_info.pack(anchor="w", pady=(0, 10))

        self.lbl_jelly_streams = ctk.CTkLabel(
            mon_frame, text="Active Streams: 0", font=("Segoe UI", 13)
        )
        self.lbl_jelly_streams.pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(
            mon_frame, text="SERVER STORAGE", font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        self.lbl_storage_info = ctk.CTkLabel(
            mon_frame, text="Storage: -- GB Free", font=("Segoe UI", 12)
        )
        self.lbl_storage_info.pack(anchor="w")
        self.storage_prog = ctk.CTkProgressBar(mon_frame, height=12)
        self.storage_prog.pack(fill="x", pady=(5, 20))
        self.storage_prog.set(0)

        ctk.CTkLabel(
            mon_frame, text="LOCAL DISK (LAPTOP)", font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        self.lbl_local_info = ctk.CTkLabel(
            mon_frame, text="Local: -- GB Free", font=("Segoe UI", 12)
        )
        self.lbl_local_info.pack(anchor="w")
        self.local_prog = ctk.CTkProgressBar(mon_frame, height=12)
        self.local_prog.pack(fill="x", pady=(5, 20))
        self.local_prog.set(0)

        ctk.CTkButton(self, text="CLOSE DASHBOARD", command=self.destroy).pack(pady=20)

        self.refresh_ui()

    def refresh_ui(self):
        status_text = self.app.lbl_jelly_info.cget("text")
        status_color = self.app.lbl_jelly_info.cget("text_color")
        self.lbl_jelly_info.configure(text=status_text, text_color=status_color)

        self.lbl_jelly_streams.configure(text=self.app.lbl_jelly_streams.cget("text"))

        self.lbl_storage_info.configure(text=self.app.lbl_storage_info.cget("text"))
        self.storage_prog.set(self.app.storage_prog.get())
        self.storage_prog.configure(
            progress_color=self.app.storage_prog.cget("progress_color")
        )

        self.lbl_local_info.configure(text=self.app.lbl_local_info.cget("text"))
        self.local_prog.set(self.app.local_prog.get())
        self.local_prog.configure(
            progress_color=self.app.local_prog.cget("progress_color")
        )
