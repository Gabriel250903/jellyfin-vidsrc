import os
import sys
import aiohttp
import subprocess
from core.event_system import events


class Updater:
    def __init__(self, current_version, repo):
        self.current_version = current_version.replace("v", "")
        self.repo = repo
        self.latest_version = None
        self.download_url = None
        self.html_url = None

    async def check_for_updates(self):
        try:
            async with aiohttp.ClientSession(trust_env=False) as session:
                url = f"https://api.github.com/repos/{self.repo}/releases/latest"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.latest_version = data.get("tag_name", "").replace("v", "")
                        self.html_url = data.get("html_url")

                        if (
                            self.latest_version
                            and self.latest_version != self.current_version
                        ):
                            exe_asset = next(
                                (
                                    a
                                    for a in data.get("assets", [])
                                    if a["name"].endswith(".exe")
                                ),
                                None,
                            )

                            if exe_asset:
                                self.download_url = exe_asset["browser_download_url"]
                                return {
                                    "status": "update_available",
                                    "version": self.latest_version,
                                    "can_auto_update": True,
                                    "download_url": self.download_url,
                                    "html_url": self.html_url,
                                }
                            else:
                                return {
                                    "status": "update_available",
                                    "version": self.latest_version,
                                    "can_auto_update": False,
                                    "html_url": self.html_url,
                                }
                        return {"status": "up_to_date"}
                    else:
                        return {
                            "status": "error",
                            "message": f"GitHub API returned {resp.status}",
                        }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def download_update(
        self, download_url, temp_exe_path, progress_callback=None
    ):
        try:
            async with aiohttp.ClientSession(trust_env=False) as session:
                async with session.get(download_url) as resp:
                    if resp.status == 200:
                        total_size = int(resp.headers.get("content-length", 0))
                        downloaded = 0
                        with open(temp_exe_path, "wb") as f:
                            while True:
                                chunk = await resp.content.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback:
                                    progress_callback(downloaded, total_size)
                        return True
            return False
        except Exception as e:
            events.emit("log", f"Updater: Download failed: {e}")
            return False

    def apply_update(self, temp_exe_path):
        current_exe = sys.executable
        exe_name = os.path.basename(current_exe)
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", exe_name)
        pid = os.getpid()

        is_frozen = getattr(sys, "frozen", False)
        bat_path = os.path.join(
            os.environ.get("TEMP", "."), "update_jellyfin_vidsrc.bat"
        )

        try:
            with open(bat_path, "w") as f:
                f.write("@echo off\n")
                f.write("title Jellyfin Updater\n")
                f.write("cd /d %TEMP%\n")
                f.write(f"echo Waiting for application to close (PID: {pid})...\n")

                f.write(":wait_loop\n")
                f.write(f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\n')
                f.write("if %ERRORLEVEL% EQU 0 (\n")
                f.write("    timeout /t 1 /nobreak >nul\n")
                f.write("    goto wait_loop\n")
                f.write(")\n")

                if is_frozen:
                    f.write(f'echo Updating: "{current_exe}"\n')
                    f.write(":move_loop\n")
                    f.write(f'move /y "{temp_exe_path}" "{current_exe}" >nul 2>&1\n')
                    f.write("if %ERRORLEVEL% NEQ 0 (\n")
                    f.write("    echo File is still locked, retrying...\n")
                    f.write("    timeout /t 1 /nobreak >nul\n")
                    f.write("    goto move_loop\n")
                    f.write(")\n")

                    f.write(f'echo Copying to Desktop: "{desktop_path}"\n')
                    f.write(f'copy /y "{current_exe}" "{desktop_path}" >nul\n')

                    f.write("echo Starting new version cleanly...\n")

                    f.write(f'explorer.exe "{current_exe}"\n')
                else:
                    f.write("echo [DEBUG] Running from source. Skipping replacement.\n")
                    f.write("timeout /t 3 /nobreak >nul\n")

                f.write(f'del "%~f0"\n')

            clean_env = os.environ.copy()
            vars_to_clear = [
                "_MEIPASS",
                "_MEIPASS2",
                "PYTHONHOME",
                "PYTHONPATH",
                "PYI_CHILD_STOP",
            ]
            for var in vars_to_clear:
                if var in clean_env:
                    del clean_env[var]

            subprocess.Popen(
                bat_path,
                shell=True,
                env=clean_env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return True
        except Exception as e:
            events.emit("log", f"Updater: Failed to create update script: {e}")
            return False
