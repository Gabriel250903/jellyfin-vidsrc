import customtkinter as ctk


class RPCSettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Discord RPC Settings")
        self.geometry("450x550")
        self.minsize(400, 500)
        self.attributes("-topmost", True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=0, border_width=0)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.scroll.grid_columnconfigure(0, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self.scroll,
            text="Discord RPC Settings",
            font=("Segoe UI", 20, "bold"),
            text_color="#3498db",
        )
        self.lbl_title.pack(pady=20)

        self.rpc_var = ctk.BooleanVar(value=self.parent.rpc_enabled)
        self.switch_rpc = ctk.CTkSwitch(
            self.scroll,
            text="Enable Discord RPC",
            variable=self.rpc_var,
            progress_color="#3498db",
        )
        self.switch_rpc.pack(pady=10, padx=20, anchor="w")

        ctk.CTkLabel(
            self.scroll, text="Client ID:", font=("Segoe UI", 12, "bold")
        ).pack(pady=(15, 5), padx=20, anchor="w")
        self.client_id_entry = ctk.CTkEntry(
            self.scroll, placeholder_text="Default ID used if empty"
        )
        self.client_id_entry.pack(pady=5, padx=20, fill="x")
        self.client_id_entry.insert(0, self.parent.rpc_client_id)

        ctk.CTkLabel(
            self.scroll,
            text="Filter by User (Optional):",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(15, 5), padx=20, anchor="w")
        self.user_entry = ctk.CTkEntry(
            self.scroll, placeholder_text="Only show presence for this user"
        )
        self.user_entry.pack(pady=5, padx=20, fill="x")
        self.user_entry.insert(0, self.parent.rpc_target_user)

        ctk.CTkLabel(self.scroll, text="Features:", font=("Segoe UI", 12, "bold")).pack(
            pady=(15, 5), padx=20, anchor="w"
        )

        self.show_time_var = ctk.BooleanVar(value=self.parent.rpc_show_time)
        self.switch_time = ctk.CTkSwitch(
            self.scroll,
            text="Show Elapsed/Remaining Time",
            variable=self.show_time_var,
            progress_color="#3498db",
        )
        self.switch_time.pack(pady=5, padx=20, anchor="w")

        self.show_server_var = ctk.BooleanVar(value=self.parent.rpc_show_server)
        self.switch_server = ctk.CTkSwitch(
            self.scroll,
            text="Show Server Name",
            variable=self.show_server_var,
            progress_color="#3498db",
        )
        self.switch_server.pack(pady=5, padx=20, anchor="w")

        self.btn_save = ctk.CTkButton(
            self,
            text="SAVE & RESTART RPC",
            height=45,
            font=("Segoe UI", 13, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self.save,
        )
        self.btn_save.grid(row=1, column=0, sticky="ew", padx=20, pady=20)

    def save(self):
        self.parent.rpc_enabled = self.rpc_var.get()
        self.parent.rpc_client_id = self.client_id_entry.get().strip()
        self.parent.rpc_target_user = self.user_entry.get().strip()
        self.parent.rpc_show_time = self.show_time_var.get()
        self.parent.rpc_show_server = self.show_server_var.get()

        self.parent.save_settings()

        if self.parent.discord_rpc:
            self.parent.discord_rpc.restart()

        self.destroy()
