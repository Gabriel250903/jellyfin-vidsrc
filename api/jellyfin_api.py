import os
import re
import requests
import threading
from tkinter import messagebox


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
                total = sum(
                    f.get("UsedSpace", 0) + f.get("FreeSpace", 0)
                    for l in storage.get("Libraries", [])
                    for f in l.get("Folders", [])
                )
                free = sum(
                    f.get("FreeSpace", 0)
                    for l in storage.get("Libraries", [])
                    for f in l.get("Folders", [])
                )
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
