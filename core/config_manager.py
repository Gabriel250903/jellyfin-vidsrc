import json
import os
import sys
import threading
from core.event_system import events


class ConfigManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_file=None):
        if hasattr(self, "_initialized") and self._initialized:
            return

        if config_file:
            self.config_file = config_file
        else:
            if getattr(sys, "frozen", False):
                self.config_file = os.path.join(
                    os.path.dirname(sys.executable), "jellyfin_config.json"
                )
            else:
                self.config_file = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..",
                    "jellyfin_config.json",
                )

        self.defaults = {
            "api_key": "",
            "show_path": "C:\\Jellyfin\\Shows",
            "movie_path": "C:\\Jellyfin\\Movies",
            "history": [],
            "quality": "1080p",
            "discord_webhook": "",
            "jellyfin_url": "",
            "jellyfin_api_key": "",
            "video_only": False,
            "sub_only": False,
            "open_folder": True,
            "show_jellyfin": True,
            "browser": "Edge",
            "rpc_enabled": False,
            "rpc_client_id": "",
            "rpc_target_user": "",
            "rpc_show_time": True,
            "rpc_show_server": True,
            "jellyfin_managed_user": "",
        }
        self.config = self.defaults.copy()
        self._save_timer = None
        self.load()
        self._initialized = True

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.config.update(data)
                events.emit("log", "CONFIG: Settings loaded successfully.")
            except Exception as e:
                events.emit("log", f"CONFIG ERROR: Failed to load settings: {e}")
        else:
            self.save()

    def save(self):
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(1.0, self._perform_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _perform_save(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
            events.emit("log", "CONFIG: Settings saved successfully.")
        except Exception as e:
            events.emit("log", f"CONFIG ERROR: Failed to save settings: {e}")

    def get(self, key, default=None):
        return self.config.get(
            key, default if default is not None else self.defaults.get(key)
        )

    def set(self, key, value):
        self.config[key] = value
        self.save()
        events.emit("config_updated", key, value)

    def update(self, data):
        self.config.update(data)
        self.save()
        events.emit("config_batch_updated", data)


config = ConfigManager()
