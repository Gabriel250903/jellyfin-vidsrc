import os
import aiohttp
import asyncio
import io
import functools
from PIL import Image, ImageOps
from core.utils import sanitize_path
from core.event_system import events


class TMDBAPI:
    def __init__(self, config_provider=None):
        self.config_provider = config_provider
        self._session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    @functools.lru_cache(maxsize=100)
    def _get_cached_image(self, cache_path):
        try:
            return Image.open(cache_path).copy()
        except Exception:
            return None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_api_key(self):
        if self.config_provider:
            if hasattr(self.config_provider, "tmdb_api_key"):
                return str(getattr(self.config_provider, "tmdb_api_key") or "")
            if isinstance(self.config_provider, dict):
                return str(self.config_provider.get("api_key") or "")
        return ""

    def _get_mode(self):
        if self.config_provider:
            if hasattr(self.config_provider, "mode_switch"):
                return (
                    "tv"
                    if getattr(self.config_provider, "mode_switch").get() == "TV Show"
                    else "movie"
                )
            if isinstance(self.config_provider, dict):
                return (
                    "tv" if self.config_provider.get("mode") == "TV Show" else "movie"
                )
        return "tv"

    async def _get(self, url, retries=3, timeout=10):
        last_err = Exception("Unknown TMDB error")
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        for i in range(retries):
            try:
                async with aiohttp.ClientSession(
                    headers=self.headers, trust_env=False
                ) as session:
                    async with session.get(url, timeout=client_timeout) as res:
                        res.raise_for_status()
                        return await res.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if i < retries - 1:
                    await asyncio.sleep(1)
            except Exception as e:
                events.emit("log", f"TMDB GET CRITICAL ERROR: {e}")
                raise e
        raise last_err

    async def _get_raw(self, url, retries=3, timeout=10):
        last_err = Exception("Unknown TMDB error")
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        for i in range(retries):
            try:
                async with aiohttp.ClientSession(
                    headers=self.headers, trust_env=False
                ) as session:
                    async with session.get(url, timeout=client_timeout) as res:
                        res.raise_for_status()
                        return await res.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if i < retries - 1:
                    await asyncio.sleep(1)
            except Exception as e:
                events.emit("log", f"TMDB RAW GET CRITICAL ERROR: {e}")
                raise e
        raise last_err

    async def preload_posters(self, results, size=(160, 240)):
        tasks = []
        for item in results:
            p_path = item.get("poster_path")
            if p_path:
                tasks.append(self.get_poster_image(p_path, size=size))
            else:

                async def _none():
                    return None

                tasks.append(_none())
        return await asyncio.gather(*tasks)

    async def perform_search(self, query, year=None):
        key = self._get_api_key()
        if not key or not query:
            events.emit("log", "ERROR: API Key or Search Query is missing.")
            return

        events.emit("search_started")
        cat = self._get_mode()

        if query.isdigit() and not year:
            events.emit("log", f"UI: Fetching TMDB ID {query}...")
            await self.fetch_by_id(query, cat)
        else:
            search_msg = f"'{query}'"
            if year:
                search_msg += f" ({year})"
            events.emit("log", f"UI: Searching TMDB for {search_msg}...")
            await self.bg_search(query, cat, year)

    async def fetch_by_id(self, tid, cat):
        try:
            key = self._get_api_key()
            url = f"https://api.themoviedb.org/3/{cat}/{tid}?api_key={key}"
            res = await self._get(url)

            if "status_code" in res and res.get("status_code") != 1:
                alt_cat = "movie" if cat == "tv" else "tv"
                events.emit(
                    "log",
                    f"UI: ID {tid} not found in {cat.upper()}, trying {alt_cat.upper()}...",
                )
                url = f"https://api.themoviedb.org/3/{alt_cat}/{tid}?api_key={key}"
                try:
                    res_alt = await self._get(url)
                    if "status_code" in res_alt and res_alt.get("status_code") != 1:
                        events.emit(
                            "log",
                            f"TMDB ERROR: ID {tid} not found in Movies or TV Shows.",
                        )
                        events.emit("results_rendered", [], cat, [])
                        return
                    res = res_alt
                    cat = alt_cat
                    events.emit(
                        "mode_change_request", "Movie" if cat == "movie" else "TV Show"
                    )
                except Exception:
                    events.emit(
                        "log", f"TMDB ERROR: ID {tid} not found in Movies or TV Shows."
                    )
                    events.emit("results_rendered", [], cat, [])
                    return

            results = [res]
            posters = await self.preload_posters(results)
            events.emit("results_rendered", results, cat, posters)
        except Exception as e:
            events.emit("log", f"ERROR fetching ID from TMDB: {e}")
            events.emit("results_rendered", [], cat, [])

    async def bg_search(self, query, cat, year=None, is_fallback=False):
        try:
            key = self._get_api_key()
            url = (
                f"https://api.themoviedb.org/3/search/{cat}?api_key={key}&query={query}"
            )
            if year:
                if cat == "movie":
                    url += f"&year={year}"
                else:
                    url += f"&first_air_date_year={year}"

            res = await self._get(url)
            if "status_code" in res:
                events.emit(
                    "log", f"TMDB ERROR: {res.get('status_message', 'Invalid API Key')}"
                )
                events.emit("results_rendered", [], cat, [])
                return

            results = res.get("results", [])

            if not results and not is_fallback:
                alt_cat = "movie" if cat == "tv" else "tv"
                events.emit(
                    "log",
                    f"UI: No {cat.upper()} results for '{query}', trying {alt_cat.upper()}...",
                )
                await self.bg_search(query, alt_cat, year, is_fallback=True)
                return

            if results and is_fallback:
                events.emit(
                    "mode_change_request", "Movie" if cat == "movie" else "TV Show"
                )

            limited_results = results[:20]
            posters = await self.preload_posters(limited_results)
            events.emit("results_rendered", limited_results, cat, posters)
        except Exception as e:
            events.emit("log", f"ERROR fetching from TMDB: {e}")
            events.emit("results_rendered", [], cat, [])

    async def fetch_seasons(self, tid):
        try:
            events.emit("log", f"API: Fetching season data for TID {tid}...")
            url = f"https://api.themoviedb.org/3/tv/{tid}?api_key={self._get_api_key()}"
            d = await self._get(url)
            season_data = {
                s["season_number"]: s["episode_count"]
                for s in d.get("seasons", [])
                if s.get("season_number", 0) > 0
            }
            events.emit("season_data_loaded", season_data)
            events.emit("log", f"API: Found {len(season_data)} seasons.")
        except Exception as e:
            events.emit("log", f"ERROR fetching seasons: {e}")

    async def load_poster(self, p):
        try:
            cache_dir = "cache/posters"
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            cache_path = os.path.join(cache_dir, p.lstrip("/"))
            if os.path.exists(cache_path):
                img = self._get_cached_image(cache_path)
            else:
                url = f"https://image.tmdb.org/t/p/w300{p}"
                img_data = await self._get_raw(url, timeout=15)
                with open(cache_path, "wb") as f:
                    f.write(img_data)
                img = Image.open(io.BytesIO(img_data))

            return img
        except Exception as e:
            events.emit("log", f"ERROR loading poster: {e}")
            return None

    async def fetch_trending(self, cat="movie", page=1):
        try:
            key = self._get_api_key()
            url = f"https://api.themoviedb.org/3/trending/{cat}/day?api_key={key}&page={page}"
            res = await self._get(url)
            results = res.get("results", [])
            posters = await self.preload_posters(results)
            return results, posters, res.get("total_pages", 1)
        except Exception as e:
            events.emit("log", f"ERROR fetching trending: {e}")
            return [], [], 0

    async def fetch_popular(self, cat="movie", page=1):
        try:
            key = self._get_api_key()
            url = (
                f"https://api.themoviedb.org/3/{cat}/popular?api_key={key}&page={page}"
            )
            res = await self._get(url)
            results = res.get("results", [])
            posters = await self.preload_posters(results)
            return results, posters, res.get("total_pages", 1)
        except Exception as e:
            events.emit("log", f"ERROR fetching popular: {e}")
            return [], [], 0

    async def fetch_genres(self, cat="movie"):
        try:
            key = self._get_api_key()
            url = f"https://api.themoviedb.org/3/genre/{cat}/list?api_key={key}"
            res = await self._get(url)
            return res.get("genres", [])
        except Exception as e:
            events.emit("log", f"ERROR fetching genres: {e}")
            return []

    async def fetch_discover(self, cat="movie", page=1, genre_id=None):
        try:
            key = self._get_api_key()
            url = f"https://api.themoviedb.org/3/discover/{cat}?api_key={key}&page={page}&sort_by=popularity.desc"
            if genre_id:
                url += f"&with_genres={genre_id}"
            res = await self._get(url)
            results = res.get("results", [])
            posters = await self.preload_posters(results)
            return results, posters, res.get("total_pages", 1)
        except Exception as e:
            events.emit("log", f"ERROR fetching discover: {e}")
            return [], [], 0

    async def fetch_full_details(self, tid, cat):
        try:
            key = self._get_api_key()
            append = "credits,videos,similar,recommendations"
            if cat == "movie":
                append += ",release_dates"
            else:
                append += ",content_ratings,external_ids"
            url = f"https://api.themoviedb.org/3/{cat}/{tid}?api_key={key}&append_to_response={append}"
            return await self._get(url)
        except Exception as e:
            events.emit("log", f"ERROR fetching full details: {e}")
            return {}

    async def fetch_season_details(self, tid, s_num):
        try:
            key = self._get_api_key()
            url = f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}?api_key={key}"
            return await self._get(url)
        except Exception as e:
            events.emit("log", f"ERROR fetching season details: {e}")
            return {}

    async def load_backdrop(self, p):
        try:
            cache_dir = "cache/backdrops"
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            cache_path = os.path.join(cache_dir, p.lstrip("/"))
            if os.path.exists(cache_path):
                img = self._get_cached_image(cache_path)
            else:
                url = f"https://image.tmdb.org/t/p/w1280{p}"
                img_data = await self._get_raw(url, timeout=20)
                with open(cache_path, "wb") as f:
                    f.write(img_data)
                img = Image.open(io.BytesIO(img_data))

            return img
        except Exception as e:
            events.emit("log", f"ERROR loading backdrop: {e}")
            return None

    async def get_poster_image(self, p_path, size=(100, 150)):
        if not p_path:
            return None
        try:
            cache_dir = "cache/posters"
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            cache_path = os.path.join(cache_dir, p_path.lstrip("/"))
            if os.path.exists(cache_path):
                img = self._get_cached_image(cache_path)
            else:
                url = f"https://image.tmdb.org/t/p/w185{p_path}"
                img_data = await self._get_raw(url, timeout=15)
                with open(cache_path, "wb") as f:
                    f.write(img_data)
                img = Image.open(io.BytesIO(img_data))

            if img:
                img = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
            return img
        except Exception as e:
            events.emit("log", f"ERROR getting poster thumbnail: {e}")
            return None

    async def download_metadata(self, name, year, tid, mode, folder):
        try:
            key = self._get_api_key()
            cat = "tv" if mode == "TV Show" else "movie"
            url = f"https://api.themoviedb.org/3/{cat}/{tid}?api_key={key}"
            d = await self._get(url)

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
                try:
                    url_poster = f"https://image.tmdb.org/t/p/original{p_path}"
                    img_data = await self._get_raw(url_poster)
                    if mode == "TV Show":
                        with open(os.path.join(folder, "poster.jpg"), "wb") as f:
                            f.write(img_data)
                    else:
                        with open(
                            os.path.join(
                                folder, f"{sanitize_path(name)} ({year})-poster.jpg"
                            ),
                            "wb",
                        ) as f:
                            f.write(img_data)
                except Exception as e:
                    events.emit("log", f"ERROR saving metadata poster: {e}")

            if mode == "TV Show":
                try:
                    seasons = d.get("seasons", [])
                    for s in seasons:
                        s_num = s.get("season_number")
                        if s_num is None or s_num == 0:
                            continue

                        s_url = f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}?api_key={key}"
                        s_data = await self._get(s_url)

                        season_folder = os.path.join(folder, f"Season {s_num}")
                        if not os.path.exists(season_folder):
                            os.makedirs(season_folder, exist_ok=True)

                        s_poster = s_data.get("poster_path")
                        if s_poster:
                            try:
                                s_poster_url = (
                                    f"https://image.tmdb.org/t/p/original{s_poster}"
                                )
                                s_img_data = await self._get_raw(s_poster_url)
                                with open(
                                    os.path.join(season_folder, "folder.jpg"), "wb"
                                ) as f:
                                    f.write(s_img_data)
                            except:
                                pass

                        for ep in s_data.get("episodes", []):
                            ep_num = ep.get("episode_number")
                            if ep_num is None:
                                continue

                            ep_meta = {
                                "tag": "episodedetails",
                                "title": ep.get("name", f"Episode {ep_num}"),
                                "season": s_num,
                                "episode": ep_num,
                                "plot": ep.get("overview", ""),
                                "rating": ep.get("vote_average", ""),
                                "tmdb_id": ep.get("id", ""),
                            }

                            ep_nfo_name = f"{sanitize_path(name)} S{str(s_num).zfill(2)}E{str(ep_num).zfill(2)}.nfo"
                            self.write_nfo(season_folder, ep_nfo_name, ep_meta)
                except Exception as e:
                    events.emit("log", f"ERROR generating episode NFOs: {e}")

        except Exception as e:
            events.emit("log", f"ERROR downloading metadata: {e}")

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
        except OSError as e:
            events.emit("log", f"ERROR writing NFO file: {e}")
