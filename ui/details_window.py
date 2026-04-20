import customtkinter as ctk
from PIL import Image, ImageOps
import webbrowser


class DetailsWindow(ctk.CTkToplevel):
    def __init__(self, app, item_data, cat):
        super().__init__(app)
        self.app = app
        self.item_data = item_data
        self.cat = cat
        self.tid = item_data.get("id")
        self._imdb_id = ""
        self._trailer_key = ""

        name = item_data.get("name") if cat == "tv" else item_data.get("title")
        self.title(f"Details - {name}")
        self.geometry("1100x950")
        self.minsize(1000, 800)
        self.attributes("-topmost", False)
        self.transient(app)
        self.focus_set()
        self.grab_set()
        self.lift()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.backdrop_container = ctk.CTkFrame(self, height=300, fg_color="black")
        self.backdrop_container.grid(row=0, column=0, sticky="ew")
        self.backdrop_container.grid_propagate(False)
        self.backdrop_label = ctk.CTkLabel(
            self.backdrop_container, text="", width=1100, height=300
        )
        self.backdrop_label.place(relx=0.5, rely=0.5, anchor="center")

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(
            self.main_container, fg_color="transparent", width=280
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        self.poster_label = ctk.CTkLabel(
            self.left_panel,
            text="Loading...",
            width=250,
            height=375,
            fg_color=("#eeeeee", "#252525"),
            corner_radius=10,
        )
        self.poster_label.pack(pady=5)

        self.btn_select = ctk.CTkButton(
            self.left_panel,
            text="SELECT FOR DOWNLOAD",
            font=("Segoe UI", 13, "bold"),
            height=40,
            fg_color="#3498db",
            hover_color="#2980b9",
            command=self._on_select_clicked,
        )
        self.btn_select.pack(fill="x", pady=5)

        self.links_f = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.links_f.pack(fill="x", pady=2)
        self.btn_trailer = ctk.CTkButton(
            self.links_f,
            text="▶ Watch Trailer",
            font=("Segoe UI", 12, "bold"),
            fg_color="#e74c3c",
            hover_color="#c0392b",
            height=32,
            command=self._open_trailer,
        )
        self.btn_trailer.pack(fill="x", pady=2)

        self.ext_links_f = ctk.CTkFrame(self.links_f, fg_color="transparent")
        self.ext_links_f.pack(fill="x", pady=2)
        self.btn_imdb = ctk.CTkButton(
            self.ext_links_f,
            text="IMDb",
            width=120,
            height=28,
            fg_color="#f1c40f",
            text_color="black",
            hover_color="#d4ac0d",
            font=("Segoe UI", 11, "bold"),
            command=lambda: self._open_url(
                f"https://www.imdb.com/title/{self._imdb_id}"
            ),
        )
        self.btn_imdb.pack(side="left", padx=(0, 5))
        self.btn_tmdb = ctk.CTkButton(
            self.ext_links_f,
            text="TMDB",
            width=120,
            height=28,
            fg_color="#01d277",
            hover_color="#019d58",
            font=("Segoe UI", 11, "bold"),
            command=lambda: self._open_url(
                f"https://www.themoviedb.org/{self.cat}/{self.tid}"
            ),
        )
        self.btn_tmdb.pack(side="right")

        self.info_scroll = ctk.CTkScrollableFrame(
            self.main_container, fg_color="transparent"
        )
        self.info_scroll.grid(row=0, column=1, sticky="nsew")

        self.lbl_title = ctk.CTkLabel(
            self.info_scroll,
            text=name,
            font=("Segoe UI", 32, "bold"),
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self.lbl_title.pack(fill="x", pady=(0, 5))
        self.lbl_tagline = ctk.CTkLabel(
            self.info_scroll,
            text="",
            font=("Segoe UI", 16, "italic"),
            text_color="#3498db",
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self.lbl_tagline.pack(fill="x", pady=(0, 15))

        self.meta_frame = ctk.CTkFrame(self.info_scroll, fg_color="transparent")
        self.meta_frame.pack(fill="x", pady=(0, 20))
        self.lbl_year = ctk.CTkLabel(
            self.meta_frame, text="", font=("Segoe UI", 14, "bold")
        )
        self.lbl_year.pack(side="left", padx=(0, 20))
        self.lbl_runtime = ctk.CTkLabel(self.meta_frame, text="", font=("Segoe UI", 14))
        self.lbl_runtime.pack(side="left", padx=(0, 20))
        self.lbl_rating = ctk.CTkLabel(
            self.meta_frame,
            text="",
            font=("Segoe UI", 14, "bold"),
            fg_color="#3498db",
            text_color="white",
            padx=12,
            corner_radius=6,
        )
        self.lbl_rating.pack(side="left", padx=(0, 10))
        self.lbl_cert = ctk.CTkLabel(
            self.meta_frame,
            text="",
            font=("Segoe UI", 12, "bold"),
            fg_color="#444",
            text_color="white",
            padx=8,
            corner_radius=4,
        )
        self.lbl_cert.pack(side="left")

        self.lbl_genres = ctk.CTkLabel(
            self.info_scroll,
            text="",
            font=("Segoe UI", 14),
            text_color="#777",
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self.lbl_genres.pack(fill="x", pady=(0, 20))

        self._add_section_header("OVERVIEW")
        ov = item_data.get("overview", "")
        self.lbl_overview = ctk.CTkLabel(
            self.info_scroll,
            text=ov,
            font=("Segoe UI", 15),
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self.lbl_overview.pack(fill="x", pady=(0, 25))

        if self.cat == "tv":
            self._add_section_header("SEASONS")
            self.season_scroll = ctk.CTkScrollableFrame(
                self.info_scroll,
                height=40,
                orientation="horizontal",
                fg_color="transparent",
            )
            self.season_scroll.pack(fill="x", pady=(0, 10))

            self.episodes_frame = ctk.CTkScrollableFrame(
                self.info_scroll,
                height=300,
                fg_color=("#f0f0f0", "#151515"),
                corner_radius=8,
            )
            self.episodes_frame.pack(fill="x", pady=(10, 25), padx=5)
            self.lbl_episodes_status = ctk.CTkLabel(
                self.episodes_frame,
                text="Select a season",
                font=("Segoe UI", 13, "italic"),
            )
            self.lbl_episodes_status.pack(pady=20, expand=True)

        self._add_section_header("PRODUCTION")
        self.prod_frame = ctk.CTkFrame(self.info_scroll, fg_color="transparent")
        self.prod_frame.pack(fill="x", pady=(0, 20))

        self._add_section_header("TOP CAST")
        self.cast_frame = ctk.CTkFrame(self.info_scroll, fg_color="transparent")
        self.cast_frame.pack(fill="x", pady=(0, 20))

        self._add_section_header("SIMILAR CONTENT")
        self.similar_scroll = ctk.CTkScrollableFrame(
            self.info_scroll,
            height=220,
            orientation="horizontal",
            fg_color="transparent",
        )
        self.similar_scroll.pack(fill="x", pady=(0, 20))

        self._load_data()

    def _add_section_header(self, text):
        ctk.CTkLabel(
            self.info_scroll,
            text=text,
            font=("Segoe UI", 13, "bold"),
            text_color="#3498db",
            anchor="w",
        ).pack(fill="x", pady=(10, 8))

    def _load_data(self):
        p_path = self.item_data.get("poster_path")
        if p_path:
            self.app.run_async(
                self.app.tmdb_api.get_poster_image(p_path, size=(250, 375)),
                self._on_poster_loaded,
            )
        self.app.run_async(
            self.app.tmdb_api.fetch_full_details(self.tid, self.cat),
            self._on_details_loaded,
        )

    def _on_poster_loaded(self, img):
        if img and self.winfo_exists():
            self.after(
                0,
                lambda: self.poster_label.configure(
                    image=ctk.CTkImage(img, img, (250, 375)), text=""
                ),
            )

    def _on_backdrop_loaded(self, img):
        if img and self.winfo_exists():
            img_fitted = ImageOps.fit(img, (1100, 300), Image.Resampling.LANCZOS)
            self.after(
                0,
                lambda: self.backdrop_label.configure(
                    image=ctk.CTkImage(img_fitted, img_fitted, (1100, 300)), text=""
                ),
            )

    def _on_details_loaded(self, data):
        if not data or not self.winfo_exists():
            return

        def _update_ui():
            if self.cat == "tv":
                self._imdb_id = data.get("external_ids", {}).get("imdb_id", "")
            else:
                self._imdb_id = data.get("imdb_id", "")

            if not self._imdb_id:
                self.btn_imdb.configure(state="disabled")

            videos = data.get("videos", {}).get("results", [])
            for v in videos:
                if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                    self._trailer_key = v.get("key")
                    break
            if not self._trailer_key:
                self.btn_trailer.configure(
                    state="disabled", text="Trailer Not Available"
                )

            if data.get("backdrop_path"):
                self.app.run_async(
                    self.app.tmdb_api.load_backdrop(data.get("backdrop_path")),
                    self._on_backdrop_loaded,
                )
            if data.get("tagline"):
                self.lbl_tagline.configure(text=f"\"{data.get('tagline')}\"")

            new_ov = data.get("overview", "")
            if new_ov:
                self.lbl_overview.configure(text=new_ov)

            self.lbl_year.configure(
                text=(
                    data.get("first_air_date" if self.cat == "tv" else "release_date")
                    or "0000"
                )[:4]
            )
            if self.cat == "movie":
                if data.get("runtime"):
                    self.lbl_runtime.configure(text=f"{data.get('runtime')} min")
            else:
                if data.get("number_of_seasons"):
                    self.lbl_runtime.configure(
                        text=f"{data.get('number_of_seasons')} Seasons • {data.get('number_of_episodes')} Episodes"
                    )

                    for w in self.season_scroll.winfo_children():
                        w.destroy()

                    first_btn = None
                    for s in data.get("seasons", []):
                        s_num = s.get("season_number", 0)
                        if s_num == 0:
                            continue

                        btn = ctk.CTkButton(
                            self.season_scroll,
                            text=f"Season {s_num}",
                            width=100,
                            height=30,
                            fg_color="#2c3e50",
                            hover_color="#34495e",
                            command=lambda n=s_num: self._on_season_selected(n),
                        )
                        btn.pack(side="left", padx=5)
                        if not first_btn:
                            first_btn = btn

                    if first_btn:
                        self.after(100, lambda: self._on_season_selected(1))

            rating = data.get("vote_average", 0)
            if rating > 0:
                self.lbl_rating.configure(text=f"★ {rating:.1f}")
            else:
                self.lbl_rating.pack_forget()

            cert = "NR"
            if self.cat == "movie":
                for r in data.get("release_dates", {}).get("results", []):
                    if r.get("iso_3166_1") == "US":
                        cert = (
                            r.get("release_dates", [{}])[0].get("certification") or "NR"
                        )
                        break
            else:
                for r in data.get("content_ratings", {}).get("results", []):
                    if r.get("iso_3166_1") == "US":
                        cert = r.get("rating") or "NR"
                        break
            self.lbl_cert.configure(text=cert)
            self.lbl_genres.configure(
                text=" • ".join([g["name"] for g in data.get("genres", [])])
            )

            prods = [p["name"] for p in data.get("production_companies", [])][:3]
            ctk.CTkLabel(
                self.prod_frame,
                text=" • ".join(prods) if prods else "N/A",
                font=("Segoe UI", 12),
            ).pack(anchor="w")
            for m in data.get("credits", {}).get("cast", [])[:10]:
                ctk.CTkLabel(
                    self.cast_frame,
                    text=f"• {m['name']} as {m['character']}",
                    font=("Segoe UI", 12),
                    anchor="w",
                ).pack(fill="x")

            similar = (
                data.get("recommendations", {}).get("results", [])
                or data.get("similar", {}).get("results", [])
            )[:10]
            for item in similar:
                f = ctk.CTkFrame(
                    self.similar_scroll,
                    fg_color="transparent",
                    width=120,
                    cursor="hand2",
                )
                f.pack(side="left", padx=10)
                f.bind("<Button-1>", lambda e, x=item: self._on_similar_clicked(x))

                img_lbl = ctk.CTkLabel(
                    f,
                    text="Poster",
                    width=100,
                    height=150,
                    fg_color="#252525",
                    corner_radius=5,
                )
                img_lbl.pack()
                img_lbl.bind(
                    "<Button-1>", lambda e, x=item: self._on_similar_clicked(x)
                )

                ctk.CTkLabel(
                    f,
                    text=item.get("name" if self.cat == "tv" else "title"),
                    font=("Segoe UI", 10, "bold"),
                    wraplength=100,
                    height=40,
                ).pack()
                if item.get("poster_path"):
                    self.app.run_async(
                        self.app.tmdb_api.get_poster_image(
                            item.get("poster_path"), (100, 150)
                        ),
                        lambda img, l=img_lbl: self.after(
                            0,
                            lambda: (
                                l.configure(
                                    image=ctk.CTkImage(img, img, (100, 150)), text=""
                                )
                                if img
                                else None
                            ),
                        ),
                    )

        self.after(0, _update_ui)

    def _on_season_selected(self, s_num):
        for w in self.season_scroll.winfo_children():
            if isinstance(w, ctk.CTkButton):
                if w.cget("text") == f"Season {s_num}":
                    w.configure(fg_color="#3498db")
                else:
                    w.configure(fg_color="#2c3e50")

        for w in self.episodes_frame.winfo_children():
            if w != self.lbl_episodes_status:
                w.destroy()

        self.lbl_episodes_status.configure(text=f"Loading Season {s_num} episodes...")
        self.lbl_episodes_status.pack(pady=20, expand=True)
        self.app.run_async(
            self.app.tmdb_api.fetch_season_details(self.tid, s_num),
            self._on_season_details_loaded,
        )

    def _on_season_details_loaded(self, data):
        if not data or not self.winfo_exists():
            return

        def _update_ui():
            self.lbl_episodes_status.pack_forget()
            for ep in data.get("episodes", []):
                row = ctk.CTkFrame(self.episodes_frame, fg_color="transparent")
                row.pack(fill="x", pady=2, padx=10)
                ctk.CTkLabel(
                    row,
                    text=f"Ep {ep.get('episode_number')}:",
                    font=("Segoe UI", 12, "bold"),
                    width=50,
                    anchor="w",
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=ep.get("name"), font=("Segoe UI", 12), anchor="w"
                ).pack(side="left", padx=5)
                if ep.get("air_date"):
                    ctk.CTkLabel(
                        row,
                        text=f"({ep.get('air_date')[:4]})",
                        font=("Segoe UI", 11),
                        text_color="#777",
                    ).pack(side="right")

        self.after(0, _update_ui)

    def _open_trailer(self):
        if self._trailer_key:
            webbrowser.open(f"https://www.youtube.com/watch?v={self._trailer_key}")

    def _open_url(self, url):
        if url:
            webbrowser.open(url)

    def _on_similar_clicked(self, item):
        self.destroy()
        self.app.open_details(item, self.cat)

    def _on_select_clicked(self):
        name = (
            self.item_data.get("name")
            if self.cat == "tv"
            else self.item_data.get("title")
        )
        date = (
            self.item_data.get("first_air_date" if self.cat == "tv" else "release_date")
            or "0000"
        )[:4]
        self.app.select_title(
            name, date, self.tid, self.item_data.get("poster_path"), cat=self.cat
        )
        self.destroy()
