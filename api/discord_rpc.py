import asyncio
import aiohttp
from pypresence.presence import AioPresence
from core.event_system import events


class DiscordRPCManager:
    def __init__(self, config_provider):
        self.config_provider = config_provider
        self.presence = None
        self.connected = False
        self.task = None
        self.last_item_id = None
        self.last_play_state = None
        self.tmdb_cache = {}
        self.metadata_cache = {}
        self._session = None

        if self._get_config("rpc_enabled"):
            self.start()

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_config(self, key):
        if hasattr(self.config_provider, key):
            return getattr(self.config_provider, key)
        if isinstance(self.config_provider, dict):
            return self.config_provider.get(key)
        return None

    def start(self):
        if self.connected or (self.task and not self.task.done()):
            return
        if hasattr(self.config_provider, "loop"):
            self.task = asyncio.run_coroutine_threadsafe(
                self._loop(), self.config_provider.loop
            )
        else:
            self.task = asyncio.create_task(self._loop())

    def stop(self):
        if self.task:
            if hasattr(self.task, "cancel"):
                self.task.cancel()
            self.task = None

        if hasattr(self.config_provider, "loop"):
            asyncio.run_coroutine_threadsafe(
                self._cleanup_presence(), self.config_provider.loop
            )
        else:
            asyncio.create_task(self._cleanup_presence())

    async def _cleanup_presence(self):
        if self.connected and self.presence:
            try:
                await self.presence.clear()
                self.presence.close()
            except:
                pass
        self.connected = False
        self.presence = None
        self.last_item_id = None
        self.last_play_state = None
        self.tmdb_cache = {}
        self.metadata_cache = {}

    def restart(self):
        self.stop()
        if self._get_config("rpc_enabled"):
            self.start()

    async def _connect(self):
        rpc_client_id = self._get_config("rpc_client_id")
        if not rpc_client_id:
            client_id = "1487889864119816225"
        else:
            client_id = rpc_client_id

        try:
            self.presence = AioPresence(client_id)
            await self.presence.connect()
            self.connected = True
            events.emit("log", f"RPC: Connected to Discord with Client ID {client_id}")
        except Exception as e:
            events.emit("log", f"RPC: Failed to connect to Discord: {e}")
            self.connected = False

    async def _loop(self):
        try:
            while True:
                if not self.connected:
                    await self._connect()
                    if not self.connected:
                        await asyncio.sleep(10)
                        continue

                try:
                    await self._update_presence()
                except Exception as e:
                    events.emit("log", f"RPC ERROR: {e}")
                    self.connected = False

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            await self._cleanup_presence()

    def _format_ticks(self, ticks):
        seconds = int(ticks / 10000000)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    async def _update_presence(self):
        if not self.presence:
            return

        jellyfin_url = self._get_config("jellyfin_url")
        jellyfin_api_key = self._get_config("jellyfin_api_key")
        rpc_target_user = self._get_config("rpc_target_user")
        tmdb_api_key = self._get_config("tmdb_api_key")
        rpc_show_server = self._get_config("rpc_show_server")

        if not jellyfin_url or not jellyfin_api_key:
            await self.presence.clear()
            return

        headers = {"X-Emby-Token": jellyfin_api_key}
        try:
            session = await self._get_session()
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(
                f"{jellyfin_url}/Sessions", headers=headers, timeout=timeout
            ) as res:
                res.raise_for_status()
                sessions = await res.json()
        except Exception as e:
            events.emit("log", f"RPC ERROR: Failed to fetch Jellyfin sessions: {e}")
            return

        target_session = None
        for s in sessions:
            if s.get("NowPlayingItem"):
                if rpc_target_user:
                    if s.get("UserName", "").lower() == rpc_target_user.lower():
                        target_session = s
                        break
                else:
                    target_session = s
                    break

        if not target_session:
            await self.presence.clear()
            self.last_item_id = None
            return

        item = target_session.get("NowPlayingItem", {})
        play_state = target_session.get("PlayState", {})

        is_paused = play_state.get("IsPaused", False)
        item_id = item.get("Id")

        title = item.get("Name", "Unknown")
        item_type = item.get("Type", "")

        details = ""
        state = ""
        large_image = "jellyfin_logo"
        small_image = "pause" if is_paused else "play"
        small_text = "Paused" if is_paused else "Playing"
        buttons = []

        if item_type == "Episode":
            series_name = item.get("SeriesName", "Unknown Series")
            season = item.get("ParentIndexNumber", 0)
            episode = item.get("IndexNumber", 0)
            details = series_name

            if title.lower() == f"episode {episode}":
                state = f"S{str(season).zfill(2)}E{str(episode).zfill(2)}"
            else:
                state = f"S{str(season).zfill(2)}E{str(episode).zfill(2)} - {title}"
        elif item_type == "Movie":
            details = title
            year = item.get("ProductionYear", "")
            state = f"({year})" if year else ""
        else:
            details = title

        ticks = play_state.get("PositionTicks", 0)
        runtime_ticks = item.get("RunTimeTicks", 0)
        pos_str = self._format_ticks(ticks)
        total_str = self._format_ticks(runtime_ticks)

        if runtime_ticks > 0:
            state = f"{state} ({pos_str} / {total_str})"

        if item_id and tmdb_api_key:
            tmdb_id = None
            media_type = "movie"

            if item_type == "Episode":
                target_id = item.get("SeriesId")
                tmdb_id = item.get("SeriesProviderIds", {}).get(
                    "Tmdb"
                ) or self.metadata_cache.get(target_id)
                media_type = "tv"
            else:
                target_id = item_id
                tmdb_id = item.get("ProviderIds", {}).get(
                    "Tmdb"
                ) or self.metadata_cache.get(target_id)
                media_type = "movie"

            if not tmdb_id and target_id:
                try:
                    timeout = aiohttp.ClientTimeout(total=3)
                    async with session.get(
                        f"{jellyfin_url}/Users/{target_session.get('UserId')}/Items/{target_id}",
                        headers=headers,
                        timeout=timeout,
                    ) as res:
                        item_res = await res.json()
                        tmdb_id = item_res.get("ProviderIds", {}).get("Tmdb")
                        if tmdb_id:
                            self.metadata_cache[target_id] = tmdb_id
                            events.emit(
                                "log",
                                f"RPC: Fetched metadata for {title}. Found TMDB ID: {tmdb_id}",
                            )
                except Exception as e:
                    events.emit("log", f"RPC ERROR: Failed to fetch item metadata: {e}")

            if tmdb_id:
                cache_key = f"{media_type}_{tmdb_id}"
                if cache_key in self.tmdb_cache:
                    cached_data = self.tmdb_cache[cache_key]
                    large_image = cached_data.get("poster", large_image)
                    tmdb_page_url = cached_data.get("url")
                    if tmdb_page_url:
                        buttons.append({"label": "View on TMDB", "url": tmdb_page_url})
                else:
                    tmdb_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={tmdb_api_key}"
                    try:
                        timeout = aiohttp.ClientTimeout(total=3)
                        async with session.get(tmdb_url, timeout=timeout) as res:
                            t_res = await res.json()
                            poster_path = t_res.get("poster_path")
                            tmdb_page_url = (
                                f"https://www.themoviedb.org/{media_type}/{tmdb_id}"
                            )

                            if poster_path:
                                large_image = (
                                    f"https://image.tmdb.org/t/p/w500{poster_path}"
                                )

                            self.tmdb_cache[cache_key] = {
                                "poster": large_image,
                                "url": tmdb_page_url,
                            }
                            buttons.append(
                                {"label": "View on TMDB", "url": tmdb_page_url}
                            )
                    except Exception as e:
                        events.emit("log", f"RPC ERROR: Failed to fetch TMDB data: {e}")

        if not large_image or large_image == "jellyfin_logo":
            large_image = "jellyfin_logo"

        kwargs = {
            "details": details,
            "state": state,
            "large_image": large_image,
            "large_text": title,
            "small_image": small_image,
            "small_text": small_text,
        }

        if buttons:
            kwargs["buttons"] = buttons

        if rpc_show_server:
            server_name = target_session.get("ServerName", "Jellyfin")
            kwargs["large_text"] = server_name

        kwargs["start"] = None
        kwargs["end"] = None

        await self.presence.update(**kwargs)
        self.last_item_id = item_id
        self.last_play_state = is_paused
