import customtkinter as ctk


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
        self.item_data = None
        self.cat = None
        self._img_ref = None

        self.img_label = ctk.CTkLabel(
            self,
            text="No Poster",
            width=160,
            height=240,
            fg_color=("#eeeeee", "#252525"),
            corner_radius=0,
            cursor="hand2",
        )
        self.img_label.pack(pady=(10, 5), padx=10)
        self.img_label.bind("<Button-1>", lambda e: self._on_clicked())

        self.rating_lbl = ctk.CTkLabel(
            self.img_label,
            text="",
            font=("Segoe UI", 10, "bold"),
            text_color="white",
            corner_radius=0,
            width=40,
            height=20,
            cursor="hand2",
        )

        self.info_f = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        self.info_f.pack(fill="x", padx=12, pady=(0, 5))
        self.info_f.bind("<Button-1>", lambda e: self._on_clicked())

        self.title_lbl = ctk.CTkLabel(
            self.info_f,
            text="",
            font=("Segoe UI", 13, "bold"),
            wraplength=150,
            anchor="w",
            justify="left",
            cursor="hand2",
        )
        self.title_lbl.pack(fill="x")
        self.title_lbl.bind("<Button-1>", lambda e: self._on_clicked())

        self.sub_lbl = ctk.CTkLabel(
            self.info_f,
            text="",
            font=("Segoe UI", 11),
            text_color="#3498db",
            cursor="hand2",
        )
        self.sub_lbl.pack(side="left")
        self.sub_lbl.bind("<Button-1>", lambda e: self._on_clicked())

        self.btn_select = ctk.CTkButton(
            self,
            text="SELECT",
            height=32,
            font=("Segoe UI", 12, "bold"),
            fg_color="#3498db",
            hover_color="#2980b9",
            corner_radius=0,
            cursor="hand2",
        )
        self.btn_select.pack(fill="x", padx=10, pady=(5, 12))

        self.configure(cursor="hand2")
        self.bind("<Button-1>", lambda e: self._on_clicked())

    def update_data(self, item, cat, preloaded_poster=None):
        self.item_data = item
        self.cat = cat
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

            def _on_item_poster_loaded(img):
                if img and self.winfo_exists():
                    try:
                        new_img = ctk.CTkImage(img, img, (160, 240))
                        self._img_ref = new_img
                        self.img_label.configure(
                            image=new_img,
                            text="",
                            fg_color="transparent",
                        )
                    except Exception:
                        pass

            self.app.run_async(
                self.app.tmdb_api.get_poster_image(p_path, size=(160, 240)),
                _on_item_poster_loaded,
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

    def _on_clicked(self):
        if self.item_data and self.cat:
            self.app.open_details(self.item_data, self.cat)
