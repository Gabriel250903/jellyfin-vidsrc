import os
import requests
import io
import threading
from PIL import Image
import customtkinter as ctk
from core.utils import sanitize_path


class TMDBAPI:
    def __init__(self, app):
        self.app = app

    def perform_search(self, query, year=None):
        key = self.app.tmdb_api_key
        if not key or not query:
            self.app.log("ERROR: API Key or Search Query is missing.")
            return

        cat = "tv" if self.app.mode_switch.get() == "TV Show" else "movie"

        if query.isdigit() and not year:
            self.app.log(f"UI: Fetching TMDB ID {query}...")
            threading.Thread(
                target=lambda: self.fetch_by_id(query, cat), daemon=True
            ).start()
        else:
            search_msg = f"'{query}'"
            if year:
                search_msg += f" ({year})"
            self.app.log(f"UI: Searching TMDB for {search_msg}...")
            threading.Thread(
                target=lambda: self.bg_search(query, cat, year), daemon=True
            ).start()

    def fetch_by_id(self, tid, cat):
        try:
            key = self.app.tmdb_api_key
            url = f"https://api.themoviedb.org/3/{cat}/{tid}?api_key={key}"
            res = requests.get(url).json()

            if "status_code" in res and res.get("status_code") != 1:
                alt_cat = "movie" if cat == "tv" else "tv"
                self.app.log(
                    f"UI: ID {tid} not found in {cat.upper()}, trying {alt_cat.upper()}..."
                )
                url = f"https://api.themoviedb.org/3/{alt_cat}/{tid}?api_key={key}"
                res_alt = requests.get(url).json()

                if "status_code" in res_alt and res_alt.get("status_code") != 1:
                    self.app.log(
                        f"TMDB ERROR: ID {tid} not found in Movies or TV Shows."
                    )
                    return

                res = res_alt
                cat = alt_cat
                self.app.after(
                    0,
                    lambda: self.app.mode_switch.set(
                        "Movie" if cat == "movie" else "TV Show"
                    ),
                )

            self.app.after(0, lambda: self.app.render_results([res], cat))
        except Exception as e:
            self.app.log(f"ERROR fetching ID from TMDB: {e}")

    def bg_search(self, query, cat, year=None, is_fallback=False):
        try:
            key = self.app.tmdb_api_key
            url = (
                f"https://api.themoviedb.org/3/search/{cat}?api_key={key}&query={query}"
            )
            if year:
                if cat == "movie":
                    url += f"&year={year}"
                else:
                    url += f"&first_air_date_year={year}"

            res = requests.get(url).json()
            if "status_code" in res:
                self.app.log(
                    f"TMDB ERROR: {res.get('status_message', 'Invalid API Key')}"
                )
                return

            results = res.get("results", [])

            if not results and not is_fallback:
                alt_cat = "movie" if cat == "tv" else "tv"
                self.app.log(
                    f"UI: No {cat.upper()} results for '{query}', trying {alt_cat.upper()}..."
                )
                self.bg_search(query, alt_cat, year, is_fallback=True)
                return

            if results and is_fallback:
                self.app.after(
                    0,
                    lambda: self.app.mode_switch.set(
                        "Movie" if cat == "movie" else "TV Show"
                    ),
                )

            self.app.after(0, lambda: self.app.render_results(results, cat))
        except Exception as e:
            self.app.log(f"ERROR fetching from TMDB: {e}")

    def fetch_seasons(self, tid):
        try:
            self.app.log(f"API: Fetching season data for TID {tid}...")
            d = requests.get(
                f"https://api.themoviedb.org/3/tv/{tid}?api_key={self.app.tmdb_api_key}"
            ).json()
            self.app.season_data = {
                s["season_number"]: s["episode_count"]
                for s in d["seasons"]
                if s["season_number"] > 0
            }
            if self.app.season_data:
                max_s = max(self.app.season_data.keys())
                self.app.after(
                    0,
                    lambda: (
                        self.app.end_season.delete(0, "end"),
                        self.app.end_season.insert(0, str(max_s)),
                    ),
                )
            self.app.log(f"API: Found {len(self.app.season_data)} seasons.")
        except Exception as e:
            self.app.log(f"ERROR fetching seasons: {e}")

    def load_poster(self, p):
        try:
            r = requests.get(f"https://image.tmdb.org/t/p/w300{p}", timeout=10)
            img = Image.open(io.BytesIO(r.content))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(220, 300))
            self.app.after(
                0,
                lambda: self.app.poster_label.configure(
                    image=ctk_img, text="", fg_color="transparent"
                ),
            )
        except Exception as e:
            self.app.log(f"ERROR loading poster: {e}")

    def download_metadata(self, name, year, tid, mode, folder):
        try:
            key = self.app.tmdb_api_key
            cat = "tv" if mode == "TV Show" else "movie"
            url = f"https://api.themoviedb.org/3/{cat}/{tid}?api_key={key}"
            d = requests.get(url).json()

            meta = {
                "tag": "tvshow" if mode == "TV Show" else "movie",
                "title": d.get("name" if mode == "TV Show" else "title"),
                "original_title": d.get(
                    "original_name" if mode == "TV Show" else "original_title"
                ),
                "year": year,
                "plot": d.get("overview"),
                "tmdb_id": tid,
                "genre": ", ".join([g["name"] for g in d.get("genres", [])]),
                "rating": d.get("vote_average"),
            }

            nfo_name = (
                "tvshow.nfo"
                if mode == "TV Show"
                else f"{sanitize_path(name)} ({year}).nfo"
            )
            self.write_nfo(folder, nfo_name, meta)

            p_path = d.get("poster_path")
            if p_path:
                r = requests.get(f"https://image.tmdb.org/t/p/original{p_path}")
                with open(os.path.join(folder, "poster.jpg"), "wb") as f:
                    f.write(r.content)
        except:
            pass

    def write_nfo(self, folder, filename, data):
        try:
            path = os.path.join(folder, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
                f.write(f"<{data['tag']}>\n")
                f.write(f"  <title>{data.get('title', '')}</title>\n")
                f.write(
                    f"  <originaltitle>{data.get('original_title', '')}</originaltitle>\n"
                )
                f.write(f"  <year>{data.get('year', '')}</year>\n")
                f.write(f"  <plot>{data.get('plot', '')}</plot>\n")
                f.write(
                    f"  <uniqueid type=\"tmdb\">{data.get('tmdb_id', '')}</uniqueid>\n"
                )
                f.write(f"  <genre>{data.get('genre', '')}</genre>\n")
                f.write(f"  <rating>{data.get('rating', '')}</rating>\n")
                f.write(f"</{data['tag']}>\n")
        except:
            pass
