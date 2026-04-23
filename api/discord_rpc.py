import asyncio
import aiohttp
import time
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
        self._last_rpc_error = None

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

    def restart(self):
        self.stop()
        if self._get_config("rpc_enabled"):
            self.start()

    async def _connect(self):
        try:
            client_id = self._get_config("rpc_client_id")
            if not client_id:
                return

            if self.presence:
                await self.presence.clear() # type: ignore
                self.presence = None

            self.presence = AioPresence(client_id)
            await self.presence.connect()
            self.connected = True
            events.emit("log", "RPC: Connected to Discord.")
            self._last_rpc_error = None
        except Exception as e:
            self.connected = False
            err_msg = str(e)
            if self._last_rpc_error != err_msg:
                events.emit("log", f"RPC: Connection failed ({err_msg})")
                self._last_rpc_error = err_msg

    async def _cleanup_presence(self):
        if self.presence:
            try:
                await self.presence.clear() # type: ignore
                await self.presence.close() # type: ignore
            except:
                pass
            self.presence = None
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
                    err_msg = str(e)
                    if self._last_rpc_error != err_msg:
                        events.emit("log", f"RPC ERROR: {err_msg}")
                        self._last_rpc_error = err_msg
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
        rpc_target_user = self._get_config("jellyfin_managed_user") or self._get_config("rpc_target_user")
        tmdb_api_key = self._get_config("tmdb_api_key")
        rpc_show_server = self._get_config("rpc_show_server")

        if not jellyfin_url or not jellyfin_api_key:
            if self.presence:
                await self.presence.clear() # type: ignore
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
                self._last_rpc_error = None
        except Exception as e:
            err_msg = str(e)
            if self._last_rpc_error != err_msg:
                events.emit("log", f"RPC ERROR: Failed to fetch Jellyfin sessions: {err_msg}")
                self._last_rpc_error = err_msg
            return

        target_session = None
        for s in sessions:
            if s.get("NowPlayingItem"):
                if rpc_target_user:
                    session_user = s.get("UserName")
                    if session_user and session_user.lower() == rpc_target_user.lower():
                        target_session = s
                        break
                else:
                    target_session = s
                    break

        if not target_session:
            if self.presence:
                await self.presence.clear()
            self.last_item_id = None
            self.last_play_state = None
            return

        item = target_session.get("NowPlayingItem", {})
        play_state = target_session.get("PlayState", {})
        client_name = target_session.get("Client", "Unknown")

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

        if rpc_show_server and jellyfin_url:
            server_name = jellyfin_url.split("//")[-1].split(":")[0]
            buttons.append({"label": f"Server: {server_name}", "url": jellyfin_url})

        # Detect state changes including device switches
        current_play_state = (item_id, is_paused, client_name)
        if current_play_state != self.last_play_state:
            self.last_play_state = current_play_state

            large_image = "jellyfin_logo"
            if tmdb_api_key:
                try:
                    tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                    if not tmdb_id:
                        search_url = f"https://api.themoviedb.org/3/search/{'tv' if item_type == 'Episode' else 'movie'}?api_key={tmdb_api_key}&query={series_name if item_type == 'Episode' else title}"
                        async with session.get(search_url) as search_res:
                            search_data = await search_res.json()
                            if search_data.get("results"):
                                tmdb_id = search_data["results"][0]["id"]

                    if tmdb_id:
                        cache_key = f"{item_type}_{tmdb_id}"
                        if cache_key in self.tmdb_cache:
                            large_image = self.tmdb_cache[cache_key]
                        else:
                            details_url = f"https://api.themoviedb.org/3/{'tv' if item_type == 'Episode' else 'movie'}/{tmdb_id}?api_key={tmdb_api_key}"
                            async with session.get(details_url) as details_res:
                                details_data = await details_res.json()
                                poster_path = details_data.get("poster_path")
                                if poster_path:
                                    large_image = f"https://image.tmdb.org/t/p/w500{poster_path}"
                                    self.tmdb_cache[cache_key] = large_image
                except Exception as e:
                    events.emit("log", f"RPC ERROR: Failed to fetch TMDB data: {e}")

            if not large_image or large_image == "jellyfin_logo":
                large_image = "jellyfin_logo"

            kwargs = {
                "details": details[:128],
                "state": state[:128],
                "large_image": large_image,
                "large_text": "VidSrc Jellyfin",
                "small_image": small_image,
                "small_text": small_text,
            }

            if buttons:
                kwargs["buttons"] = buttons

            if self._get_config("rpc_show_time") and not is_paused:
                pos_ticks = play_state.get("PositionTicks", 0)
                pos_seconds = int(pos_ticks / 10000000)
                kwargs["start"] = int(time.time()) - pos_seconds

            await self.presence.update(**kwargs) # type: ignore
