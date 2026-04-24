import os
import aiohttp
import asyncio
import random
import re
from core.event_system import events


class JellyfinAPI:
    def __init__(self, config_provider=None):
        self.config_provider = config_provider
        self._session = None
        self._ws_task = None
        self._ws_running = False
        self._last_ws_error = None
        self._last_status_error = None
        self._last_api_error = None
        self.tmdb_keys = [
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

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(trust_env=False)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_url(self):
        url = ""
        if self.config_provider:
            if hasattr(self.config_provider, "jellyfin_url"):
                url = str(getattr(self.config_provider, "jellyfin_url") or "")
            if isinstance(self.config_provider, dict):
                url = str(self.config_provider.get("jellyfin_url", ""))

        if url and not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        return url.rstrip("/")

    def _get_api_key(self):
        if self.config_provider:
            if hasattr(self.config_provider, "jellyfin_api_key"):
                return str(getattr(self.config_provider, "jellyfin_api_key") or "")
            if isinstance(self.config_provider, dict):
                return str(self.config_provider.get("jellyfin_api_key", ""))
        return ""

    def _get_managed_user(self):
        if self.config_provider:
            if hasattr(self.config_provider, "jellyfin_managed_user"):
                return str(getattr(self.config_provider, "jellyfin_managed_user") or "")
            if isinstance(self.config_provider, dict):
                return str(self.config_provider.get("jellyfin_managed_user", ""))
        return ""

    async def trigger_scan(self, path):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            await asyncio.sleep(2)
            url = f"{url_base}/Library/Media/Updated"
            headers = {
                "X-Emby-Token": api_key,
                "Content-Type": "application/json",
            }
            data = {
                "Updates": [{"Path": os.path.abspath(path), "UpdateType": "Created"}]
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.post(
                    url, headers=headers, json=data, timeout=timeout, ssl=False
                ) as res:
                    if res.status >= 300:
                        await session.post(
                            f"{url_base}/Library/Refresh",
                            headers=headers,
                            timeout=timeout,
                            ssl=False,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            err_msg = str(e)
            if self._last_api_error != err_msg:
                events.emit("log", f"JELLYFIN ERROR: Trigger scan failed: {e}")
                self._last_api_error = err_msg
        except Exception as e:
            err_msg = str(e)
            if self._last_api_error != err_msg:
                events.emit("log", f"JELLYFIN CRITICAL ERROR: {e}")
                self._last_api_error = err_msg

    async def send_message(self, header, text):
        url_base = self._get_url()
        api_key = self._get_api_key()
        managed_user = self._get_managed_user()
        if not url_base or not api_key:
            return

        try:
            headers = {
                "X-Emby-Token": api_key,
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(
                    f"{url_base}/Sessions", headers=headers, timeout=timeout, ssl=False
                ) as res:
                    if res.status == 200:
                        sessions = await res.json()
                        for s in sessions:
                            if (
                                managed_user
                                and s.get("UserName", "").lower()
                                != managed_user.lower()
                            ):
                                continue

                            sid = s.get("Id")
                            if sid:
                                await session.post(
                                    f"{url_base}/Sessions/{sid}/Message",
                                    headers=headers,
                                    json={
                                        "Header": header,
                                        "Text": text,
                                        "TimeoutMs": 5000,
                                    },
                                    timeout=timeout,
                                    ssl=False,
                                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            err_msg = str(e)
            if self._last_api_error != err_msg:
                events.emit("log", f"JELLYFIN ERROR: Send message failed: {e}")
                self._last_api_error = err_msg
        except Exception as e:
            err_msg = str(e)
            if self._last_api_error != err_msg:
                events.emit("log", f"JELLYFIN CRITICAL ERROR: {e}")
                self._last_api_error = err_msg

    async def get_users(self):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return []

        try:
            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(
                    f"{url_base}/Users", headers=headers, timeout=timeout, ssl=False
                ) as res:
                    if res.status == 200:
                        return await res.json()
        except:
            pass
        return []

    async def _get_tmdb(self, url):
        key = random.choice(self.tmdb_keys)
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}api_key={key}"
        try:
            session = await self._get_session()
            async with session.get(
                full_url, timeout=aiohttp.ClientTimeout(total=10), ssl=False
            ) as res:
                if res.status == 200:
                    return await res.json()
        except:
            pass
        return None

    async def get_tmdb_id(self, name, year=None):
        url = f"https://api.themoviedb.org/3/search/tv?query={name}"
        if year:
            url += f"&first_air_date_year={year}"

        data = await self._get_tmdb(url)
        if not data or not data.get("results"):
            if year:
                data = await self._get_tmdb(
                    f"https://api.themoviedb.org/3/search/tv?query={name}"
                )

        if data and data.get("results"):
            return data["results"][0]["id"]
        return None

    async def get_season_data(self, tmdb_id):
        data = await self._get_tmdb(f"https://api.themoviedb.org/3/tv/{tmdb_id}")
        if not data:
            return {}
        return {
            s["season_number"]: s["episode_count"]
            for s in data.get("seasons", [])
            if s["season_number"] > 0
        }

    async def scan_missing_episodes(self, on_progress=None, on_complete=None):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}

            async with session.get(
                f"{url_base}/Items?IncludeItemTypes=Series&Recursive=true&Fields=ProviderIds",
                headers=headers,
                ssl=False,
            ) as res:
                series_list = (await res.json()).get("Items", [])

            total = len(series_list)
            missing_report = []

            for i, series in enumerate(series_list):
                if on_progress:
                    events.emit(
                        "api_callback", on_progress, i + 1, total, series.get("Name")
                    )

                tmdb_id = series.get("ProviderIds", {}).get("Tmdb")
                if not tmdb_id:
                    name = series.get("Name")
                    year = series.get("ProductionYear")
                    tmdb_id = await self.get_tmdb_id(name, year)

                if not tmdb_id:
                    continue

                expected = await self.get_season_data(tmdb_id)
                if not expected:
                    continue

                async with session.get(
                    f"{url_base}/Shows/{series['Id']}/Episodes?Fields=ProviderIds",
                    headers=headers,
                    ssl=False,
                ) as res:
                    local_eps = (await res.json()).get("Items", [])

                local_data = {}
                for ep in local_eps:
                    s = ep.get("ParentIndexNumber")
                    e = ep.get("IndexNumber")
                    if s is not None and e is not None:
                        if s not in local_data:
                            local_data[s] = set()
                        local_data[s].add(e)

                series_gaps = {}
                for s_num, count in expected.items():
                    existing = local_data.get(s_num, set())
                    missing = [e for e in range(1, count + 1) if e not in existing]
                    if missing:
                        series_gaps[s_num] = missing

                if series_gaps:
                    missing_report.append(
                        {
                            "name": series.get("Name"),
                            "year": series.get("ProductionYear"),
                            "tid": tmdb_id,
                            "gaps": series_gaps,
                        }
                    )

                await asyncio.sleep(0.5)

            if on_complete:
                events.emit("api_callback", on_complete, missing_report)

        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: scan_missing_episodes failed: {e}")
            if on_complete:
                events.emit("api_callback", on_complete, [])

    async def kill_session(self, session_id):
        await self.send_command(session_id, "Stop")
        await self.send_command(session_id, "GoHome")

    async def send_command(self, session_id, command, args=None):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            headers = {"X-Emby-Token": api_key, "Content-Length": "0"}
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(trust_env=False) as session:
                if command in [
                    "Stop",
                    "Pause",
                    "Unpause",
                    "PlayPause",
                    "Mute",
                    "Unmute",
                    "VolumeUp",
                    "VolumeDown",
                ]:
                    endpoint = f"{url_base}/Sessions/{session_id}/Playing/{command}"
                else:
                    endpoint = f"{url_base}/Sessions/{session_id}/Command/{command}"

                async with session.post(
                    endpoint, headers=headers, timeout=timeout, ssl=False
                ) as res:
                    if res.status < 300:
                        return True

                    headers_json = {
                        "X-Emby-Token": api_key,
                        "Content-Type": "application/json",
                    }
                    payload = {"Name": command, "Arguments": args or {}}
                    async with session.post(
                        f"{url_base}/Sessions/{session_id}/Command",
                        headers=headers_json,
                        json=payload,
                        timeout=timeout,
                        ssl=False,
                    ) as res2:
                        return res2.status < 300
        except:
            pass
        return False

    async def set_volume(self, session_id, volume):
        return await self.send_command(session_id, "SetVolume", {"Volume": volume})

    async def timed_kill(self, session_id, minutes, message):
        try:
            events.emit(
                "log",
                f"JELLYFIN: Scheduled kill for session {session_id} in {minutes}m.",
            )
            await self.send_message("Server Admin", message)
            await asyncio.sleep(minutes * 60)
            await self.kill_session(session_id)
        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: timed_kill failed: {e}")

    async def seek_relative(self, session_id, seconds):
        if hasattr(self, "_seeking") and self._seeking:
            return
        self._seeking = True
        try:
            url_base = self._get_url()
            api_key = self._get_api_key()
            if not url_base or not api_key:
                return

            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(
                    f"{url_base}/Sessions", headers=headers, timeout=timeout, ssl=False
                ) as res:
                    if res.status == 200:
                        sessions = await res.json()
                        target = next(
                            (s for s in sessions if s.get("Id") == session_id), None
                        )
                        if not target:
                            return

                        curr_ticks = target.get("PlayState", {}).get("PositionTicks", 0)
                        new_pos = max(0, curr_ticks + (seconds * 10000000))

                        seek_url = f"{url_base}/Sessions/{session_id}/Playing/Seek?seekPositionTicks={int(new_pos)}"
                        async with session.post(
                            seek_url, headers=headers, timeout=timeout, ssl=False
                        ) as seek_res:
                            if seek_res.status < 300:
                                await asyncio.sleep(0.5)
                                return True
        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: Seek failed: {e}")
        finally:
            self._seeking = False
        return False

    async def update_status(self):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(
                f"{url_base}/System/Info", headers=headers, timeout=timeout, ssl=False
            ) as res:
                res.raise_for_status()
                info = await res.json()

            events.emit(
                "jellyfin_status_update",
                {"status": "Online", "version": info.get("Version", "?")},
            )
            self._last_status_error = None
            self._last_api_error = None

            async with session.get(
                f"{url_base}/System/Info/Storage",
                headers=headers,
                timeout=timeout,
                ssl=False,
            ) as res:
                if res.status == 200:
                    storage = await res.json()

                    unique_drives = {}
                    for l in storage.get("Libraries", []):
                        for f in l.get("Folders", []):
                            total_space = f.get("UsedSpace", 0) + f.get("FreeSpace", 0)
                            free_space = f.get("FreeSpace", 0)
                            if total_space > 0:
                                t_mb = round(total_space / (1024 * 1024))
                                f_mb = round(free_space / (1024 * 1024))
                                drive_key = f"{t_mb}_{f_mb}"
                                if drive_key not in unique_drives:
                                    unique_drives[drive_key] = f

                    total = sum(
                        f.get("UsedSpace", 0) + f.get("FreeSpace", 0)
                        for f in unique_drives.values()
                    )
                    free = sum(f.get("FreeSpace", 0) for f in unique_drives.values())

                    if total > 0:
                        free_gb = free / (1024**3)
                        events.emit(
                            "jellyfin_storage_update",
                            {"free_gb": free_gb, "percent": (total - free) / total},
                        )

            async with session.get(
                f"{url_base}/Sessions", headers=headers, timeout=timeout, ssl=False
            ) as res:
                if res.status == 200:
                    sessions = await res.json()
                    active = [s for s in sessions if s.get("NowPlayingItem")]
                    curr = {}
                    for s in active:
                        item = s["NowPlayingItem"]
                        name = item.get("Name", "Unknown Item")
                        if item.get("Type") == "Episode":
                            series_name = item.get("SeriesName", "Unknown Series")
                            s_num = str(item.get("ParentIndexNumber", 0)).zfill(2)
                            e_num = str(item.get("IndexNumber", 0)).zfill(2)
                            name = f"{series_name} - S{s_num}E{e_num}"

                        curr[s["Id"]] = {
                            "user": s.get("UserName") or "System/TV",
                            "title": name,
                            "client": s.get("Client") or "Unknown Client",
                            "session_data": s,
                        }

                    events.emit("jellyfin_sessions_update", curr)
                    events.emit("jellyfin_streams_count", len(active))

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            events.emit("jellyfin_status_update", {"status": "Offline"})
            err_msg = str(e)
            if self._last_status_error != err_msg:
                is_starting = (
                    "503" in err_msg
                    or "refused" in err_msg.lower()
                    or "10061" in err_msg
                )
                if is_starting:
                    events.emit(
                        "log",
                        f"JELLYFIN: Waiting for server to be ready... ({err_msg})",
                    )
                else:
                    events.emit("log", f"JELLYFIN: Connection lost/failed ({err_msg})")
                self._last_status_error = err_msg
        except Exception as e:
            err_msg = str(e)
            if self._last_status_error != err_msg:
                events.emit("log", f"JELLYFIN STATUS CRITICAL ERROR: {e}")
                self._last_status_error = err_msg

    async def send_message_to_session(self, session_id, header, text):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            headers = {
                "X-Emby-Token": api_key,
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.post(
                    f"{url_base}/Sessions/{session_id}/Message",
                    headers=headers,
                    json={
                        "Header": header,
                        "Text": text,
                        "TimeoutMs": 5000,
                    },
                    timeout=timeout,
                    ssl=False,
                ) as res:
                    return res.status < 300
        except:
            return False

    async def fetch_watched_content(self, on_success):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=10)

            async with session.get(
                f"{url_base}/Users", headers=headers, timeout=timeout, ssl=False
            ) as users_res:
                users_res.raise_for_status()
                users = await users_res.json()

            if not users:
                events.emit("log", "JELLYFIN: No users found.")
                if on_success:
                    events.emit("api_callback", on_success, [])
                return

            watched_items = {}

            for user in users:
                user_id = user.get("Id")
                user_name = user.get("Name")

                params = {
                    "Recursive": "true",
                    "Filters": "IsPlayed",
                    "IncludeItemTypes": "Movie,Episode",
                    "Fields": "Path,SeriesName,ParentIndexNumber,IndexNumber,CollectionIds",
                }
                async with session.get(
                    f"{url_base}/Users/{user_id}/Items",
                    headers=headers,
                    params=params,
                    timeout=timeout,
                    ssl=False,
                ) as items_res:
                    if items_res.status == 200:
                        data = await items_res.json()
                        items = data.get("Items", [])
                        for item in items:
                            i_id = item.get("Id")
                            if i_id not in watched_items:
                                watched_items[i_id] = {
                                    "Id": i_id,
                                    "Name": item.get("Name"),
                                    "Type": item.get("Type"),
                                    "Path": item.get("Path", "Unknown Path"),
                                    "SeriesName": item.get("SeriesName"),
                                    "SeasonNumber": item.get("ParentIndexNumber"),
                                    "EpisodeNumber": item.get("IndexNumber"),
                                    "CollectionIds": item.get("CollectionIds", []),
                                    "WatchedBy": [],
                                }
                            watched_items[i_id]["WatchedBy"].append(user_name)

            if on_success:
                events.emit("api_callback", on_success, list(watched_items.values()))

        except Exception as e:
            err_msg = str(e)
            if self._last_api_error != err_msg:
                events.emit(
                    "log", f"JELLYFIN ERROR: Fetching watched content failed: {e}"
                )
                self._last_api_error = err_msg
            if on_success:
                events.emit("api_callback", on_success, [])

    async def delete_items_batch(self, items, on_progress=None, on_complete=None):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}
            total_items = len(items)
            deleted_count = 0
            timeout = aiohttp.ClientTimeout(total=10)

            for index, item in enumerate(items):
                try:
                    async with session.delete(
                        f"{url_base}/Items/{item['Id']}",
                        headers=headers,
                        timeout=timeout,
                    ) as res:
                        res.raise_for_status()
                        deleted_count += 1
                except Exception as e:
                    events.emit(
                        "log",
                        f"JELLYFIN ERROR: Batch delete failed for {item.get('Name')}: {e}",
                    )

                if on_progress:
                    events.emit("api_callback", on_progress, index + 1, total_items)

                if index < total_items - 1:
                    await asyncio.sleep(1.5)

            events.emit(
                "show_info",
                "Success",
                f"Successfully deleted {deleted_count} watched items.",
            )
            if on_complete:
                events.emit("api_callback", on_complete)
        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: Batch delete process failed: {e}")

    async def delete_item(self, item, on_success=None):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(
                f"{url_base}/Items?Recursive=true&hasTmdbId=true&Fields=ProviderIds",
                headers=headers,
                timeout=timeout,
            ) as res:
                data = await res.json()

            to_del = [
                j
                for j in data.get("Items", [])
                if str(j.get("ProviderIds", {}).get("Tmdb", "")) == str(item["tid"])
            ]
            if to_del:
                for d in to_del:
                    try:
                        async with session.delete(
                            f"{url_base}/Items/{d['Id']}",
                            headers=headers,
                            timeout=timeout,
                        ) as del_res:
                            del_res.raise_for_status()
                    except Exception as e:
                        events.emit(
                            "log",
                            f"JELLYFIN ERROR: Failed to delete sub-item {d['Id']}: {e}",
                        )

                if on_success:
                    events.emit("api_callback", on_success)
                events.emit("show_info", "Success", "Deleted from server.")
            else:
                events.emit("show_info", "Info", "Item not found on server.")
        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: Delete failed: {e}")

    async def delete_item_by_id(self, item_id, name, on_success=None):
        url_base = self._get_url()
        api_key = self._get_api_key()
        if not url_base or not api_key:
            return

        try:
            session = await self._get_session()
            headers = {"X-Emby-Token": api_key}
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.delete(
                f"{url_base}/Items/{item_id}", headers=headers, timeout=timeout
            ) as res:
                res.raise_for_status()

            if on_success:
                events.emit("api_callback", on_success)

            events.emit("show_info", "Success", f"'{name}' deleted from server.")
        except Exception as e:
            events.emit("log", f"JELLYFIN ERROR: Delete failed for {name}: {e}")
            events.emit("show_error", "Error", f"Failed to delete '{name}': {e}")

    def start_websocket(self, loop):
        if self._ws_running:
            return
        self._ws_running = True
        self._ws_task = asyncio.run_coroutine_threadsafe(self._ws_loop(), loop)

    async def _ws_loop(self):
        while self._ws_running:
            url_base = self._get_url()
            api_key = self._get_api_key()
            if not url_base or not api_key:
                await asyncio.sleep(10)
                continue

            ws_url = (
                url_base.replace("http", "ws", 1)
                + f"/socket?api_key={api_key}&deviceId=VidSrcJellyfin"
            )

            try:
                await self.update_status()
                async with aiohttp.ClientSession(trust_env=False) as session:
                    async with session.ws_connect(
                        ws_url, ssl=False, heartbeat=30
                    ) as ws:
                        events.emit("log", "JELLYFIN: WebSocket connected.")
                        self._last_ws_error = None

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                msg_type = data.get("MessageType")

                                if msg_type in [
                                    "Sessions",
                                    "PlaybackStart",
                                    "PlaybackStop",
                                    "SessionStart",
                                    "SessionEnded",
                                    "UserDataChanged",
                                    "LibraryChanged",
                                ]:
                                    await self.update_status()
                            elif msg.type in [
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ]:
                                break
            except Exception as e:
                err_msg = str(e)
                if self._last_ws_error != err_msg:
                    events.emit(
                        "log", f"JELLYFIN: WebSocket connection failed ({err_msg})"
                    )
                    self._last_ws_error = err_msg

            if self._ws_running:
                await asyncio.sleep(5)

    def stop_websocket(self):
        self._ws_running = False
        if self._ws_task:
            self._ws_task.cancel()
