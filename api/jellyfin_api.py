import os
import re
import requests
import threading
from tkinter import messagebox
import time


class JellyfinAPI:
    def __init__(self, app):
        self.app = app

    def trigger_scan(self, path):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run_scan():
            try:
                url = f"{self.app.jellyfin_url}/Library/Media/Updated"
                headers = {
                    "X-Emby-Token": self.app.jellyfin_api_key,
                    "Content-Type": "application/json",
                }
                data = {
                    "Updates": [
                        {"Path": os.path.abspath(path), "UpdateType": "Created"}
                    ]
                }
                res = requests.post(url, headers=headers, json=data, timeout=10)
                if res.status_code >= 300:
                    requests.post(
                        f"{self.app.jellyfin_url}/Library/Refresh",
                        headers=headers,
                        timeout=10,
                    )
            except:
                pass

        threading.Thread(target=run_scan, daemon=True).start()

    def send_message(self, header, text):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run_send():
            try:
                headers = {
                    "X-Emby-Token": self.app.jellyfin_api_key,
                    "Content-Type": "application/json",
                }
                res = requests.get(
                    f"{self.app.jellyfin_url}/Sessions", headers=headers, timeout=5
                )
                if res.status_code == 200:
                    for s in res.json():
                        sid = s.get("Id")
                        if sid:
                            requests.post(
                                f"{self.app.jellyfin_url}/Sessions/{sid}/Message",
                                headers=headers,
                                json={
                                    "Header": header,
                                    "Text": text,
                                    "TimeoutMs": 5000,
                                },
                                timeout=5,
                            )
            except:
                pass

        threading.Thread(target=run_send, daemon=True).start()

    def update_status(self):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def check():
            try:
                headers = {"X-Emby-Token": self.app.jellyfin_api_key}
                info = requests.get(
                    f"{self.app.jellyfin_url}/System/Info", headers=headers, timeout=5
                ).json()
                self.app.after(
                    0,
                    lambda: self.app.lbl_jelly_info.configure(
                        text=f"Status: Online ({info.get('Version','?')})",
                        text_color="#2ecc71",
                    ),
                )

                storage = requests.get(
                    f"{self.app.jellyfin_url}/System/Info/Storage",
                    headers=headers,
                    timeout=5,
                ).json()

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
                    self.app.jellyfin_free_gb = free_gb
                    self.app.after(
                        0,
                        lambda: (
                            self.app.lbl_storage_info.configure(
                                text=f"Storage: {free_gb:.1f} GB Free"
                            ),
                            self.app.storage_prog.set((total - free) / total),
                        ),
                    )

                sessions = requests.get(
                    f"{self.app.jellyfin_url}/Sessions", headers=headers, timeout=5
                ).json()
                active = [s for s in sessions if s.get("NowPlayingItem")]
                curr = {}
                for s in active:
                    item = s["NowPlayingItem"]
                    name = item.get("Name")
                    if item.get("Type") == "Episode":
                        name = f"{item.get('SeriesName')} - S{str(item.get('ParentIndexNumber')).zfill(2)}E{str(item.get('IndexNumber')).zfill(2)}"
                    curr[s["Id"]] = {
                        "user": s.get("UserName"),
                        "title": name,
                        "client": s.get("Client"),
                    }
                for sid, info in curr.items():
                    if sid not in self.app.last_jelly_sessions:
                        self.app.log(
                            f"JELLYFIN: {info['user']} started watching '{info['title']}' on {info['client']}"
                        )
                self.app.last_jelly_sessions = curr
                self.app.after(
                    0,
                    lambda: self.app.lbl_jelly_streams.configure(
                        text=f"Active Streams: {len(active)}"
                    ),
                )
            except:
                self.app.after(
                    0,
                    lambda: self.app.lbl_jelly_info.configure(
                        text="Status: Offline", text_color="#e74c3c"
                    ),
                )

        threading.Thread(target=check, daemon=True).start()

    def fetch_watched_content(self, on_success):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run():
            try:
                headers = {"X-Emby-Token": self.app.jellyfin_api_key}

                users_res = requests.get(
                    f"{self.app.jellyfin_url}/Users", headers=headers, timeout=5
                )
                users_res.raise_for_status()
                users = users_res.json()

                if not users:
                    self.app.log("JELLYFIN: No users found.")
                    if on_success:
                        self.app.after(0, lambda: on_success([]))
                    return

                watched_items = {}

                for user in users:
                    user_id = user.get("Id")
                    user_name = user.get("Name")

                    items_res = requests.get(
                        f"{self.app.jellyfin_url}/Users/{user_id}/Items",
                        headers=headers,
                        params={
                            "Recursive": "true",
                            "Filters": "IsPlayed",
                            "IncludeItemTypes": "Movie,Episode",
                            "Fields": "Path",
                        },
                        timeout=10,
                    )

                    if items_res.status_code == 200:
                        items = items_res.json().get("Items", [])
                        for item in items:
                            i_id = item.get("Id")
                            if i_id not in watched_items:
                                watched_items[i_id] = {
                                    "Id": i_id,
                                    "Name": item.get("Name"),
                                    "Type": item.get("Type"),
                                    "Path": item.get("Path", "Unknown Path"),
                                    "WatchedBy": [],
                                }
                            watched_items[i_id]["WatchedBy"].append(user_name)

                if on_success:
                    self.app.after(0, lambda: on_success(list(watched_items.values())))

            except Exception as e:
                self.app.log(f"JELLYFIN ERROR: Fetching watched content failed: {e}")
                if on_success:
                    self.app.after(0, lambda: on_success([]))

        threading.Thread(target=run, daemon=True).start()

    def delete_items_batch(self, items, on_progress=None, on_complete=None):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run():
            headers = {"X-Emby-Token": self.app.jellyfin_api_key}
            total_items = len(items)
            deleted_count = 0

            for index, item in enumerate(items):
                try:
                    res = requests.delete(
                        f"{self.app.jellyfin_url}/Items/{item['Id']}",
                        headers=headers,
                        timeout=10,
                    )
                    res.raise_for_status()
                    deleted_count += 1
                except Exception as e:
                    self.app.log(
                        f"JELLYFIN ERROR: Batch delete failed for {item.get('Name')}: {e}"
                    )

                if on_progress:
                    self.app.after(
                        0,
                        lambda curr=index + 1, tot=total_items: on_progress(curr, tot),
                    )

                if index < total_items - 1:
                    time.sleep(1.5)

            self.app.after(
                0,
                lambda: messagebox.showinfo(
                    "Success", f"Successfully deleted {deleted_count} watched items."
                ),
            )
            if on_complete:
                self.app.after(0, on_complete)

        threading.Thread(target=run, daemon=True).start()

    def delete_item(self, item, on_success=None):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run():
            try:
                headers = {"X-Emby-Token": self.app.jellyfin_api_key}
                res = requests.get(
                    f"{self.app.jellyfin_url}/Items?Recursive=true&hasTmdbId=true&Fields=ProviderIds",
                    headers=headers,
                    timeout=10,
                ).json()
                to_del = [
                    j
                    for j in res.get("Items", [])
                    if str(j.get("ProviderIds", {}).get("Tmdb", "")) == str(item["tid"])
                ]
                if to_del:
                    for d in to_del:
                        requests.delete(
                            f"{self.app.jellyfin_url}/Items/{d['Id']}",
                            headers=headers,
                            timeout=10,
                        )
                    if on_success:
                        self.app.after(0, on_success)
                    self.app.after(
                        0,
                        lambda: messagebox.showinfo("Success", "Deleted from server."),
                    )
                else:
                    self.app.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Info", "Item not found on server."
                        ),
                    )
            except Exception as e:
                self.app.log(f"JELLYFIN ERROR: Delete failed: {e}")

        threading.Thread(target=run, daemon=True).start()

    def delete_item_by_id(self, item_id, name, on_success=None):
        if not self.app.jellyfin_url or not self.app.jellyfin_api_key:
            return

        def run():
            try:
                headers = {"X-Emby-Token": self.app.jellyfin_api_key}
                res = requests.delete(
                    f"{self.app.jellyfin_url}/Items/{item_id}",
                    headers=headers,
                    timeout=10,
                )
                res.raise_for_status()

                if on_success:
                    self.app.after(0, on_success)

                self.app.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Success", f"'{name}' deleted from server."
                    ),
                )
            except Exception as e:
                self.app.log(f"JELLYFIN ERROR: Delete failed for {name}: {e}")
                self.app.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Failed to delete '{name}': {e}"
                    ),
                )

        threading.Thread(target=run, daemon=True).start()
