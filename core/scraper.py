import os
import time
import re
from selenium.webdriver.edge.webdriver import WebDriver as EdgeDriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.webdriver import WebDriver as FirefoxDriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)
from contextlib import redirect_stderr
from core.event_system import events


class VidSrcScraper:
    def __init__(self, controller):
        self.controller = controller
        self.driver = None
        self.current_folder = None
        self.task_file_map = {}

    def get_browser_downloads(self):
        if not self.driver:
            return []
        browser = self.controller.config.get("browser", "Edge")
        if browser not in ["Chrome", "Edge"]:
            return []

        try:
            current_url = self.driver.current_url
            if (
                "downloads" not in current_url
                and not current_url.startswith("chrome://")
                and not current_url.startswith("edge://")
            ):
                self.driver.get(
                    "chrome://downloads/"
                    if browser == "Chrome"
                    else "edge://downloads/all"
                )
                time.sleep(1)

            items = self.driver.execute_script(
                """
                var manager = document.querySelector('downloads-manager');
                if (manager && manager.shadowRoot) {
                    var list = manager.shadowRoot.querySelector('#downloadsList');
                    if (list && list.items) {
                        return list.items.map(i => ({
                            fileName: i.fileName,
                            state: i.state,
                            totalBytes: i.totalBytes,
                            receivedBytes: i.receivedBytes,
                            percent: i.percent,
                            eta: i.estimatedEndTime
                        }));
                    }
                }
                return [];
            """
            )
            return items
        except Exception as e:
            events.emit("log", f"SCRAPER: Failed to get browser downloads: {e}")
            return []

    def _get_driver(self, folder):
        abs_folder = os.path.abspath(folder)
        browser = self.controller.config.get("browser", "Edge")

        if self.driver:
            try:
                self.driver.current_url
                if self.current_folder == abs_folder:
                    events.emit("log", "SCRAPER: Reusing existing driver instance.")
                    return self.driver
                elif browser in ["Chrome", "Edge"]:
                    events.emit(
                        "log",
                        f"SCRAPER: Updating download path to {abs_folder} via CDP.",
                    )
                    self.driver.execute_cdp_cmd(
                        "Page.setDownloadBehavior",
                        {"behavior": "allow", "downloadPath": abs_folder},
                    )
                    self.current_folder = abs_folder
                    return self.driver
                else:
                    events.emit(
                        "log",
                        f"SCRAPER: Target folder changed ({self.current_folder} -> {abs_folder}), restarting driver.",
                    )
                    self.quit_driver()
            except Exception:
                events.emit("log", "SCRAPER: Existing driver unresponsive, restarting.")
                self.quit_driver()

        self.driver = self._create_driver_instance(abs_folder)
        self.current_folder = abs_folder
        return self.driver

    def _create_driver_instance(self, abs_folder):
        browser = self.controller.config.get("browser", "Edge")
        events.emit(
            "log", f"SCRAPER: Initializing {browser} driver for folder: {abs_folder}"
        )

        try:
            with open(os.devnull, "w") as f, redirect_stderr(f):
                if browser == "Chrome":
                    opts = ChromeOptions()
                    opts.add_argument("--headless=new")
                    opts.add_argument("--log-level=3")
                    opts.add_argument("--silent")
                    opts.add_experimental_option(
                        "prefs",
                        {
                            "download.default_directory": abs_folder,
                            "profile.default_content_setting_values.automatic_downloads": 1,
                            "download.directory_upgrade": True,
                            "download.prompt_for_download": False,
                        },
                    )
                    return ChromeDriver(options=opts)

                elif browser == "Firefox":
                    opts = FirefoxOptions()
                    opts.add_argument("--headless")
                    opts.set_preference("browser.download.folderList", 2)
                    opts.set_preference(
                        "browser.download.manager.showWhenStarting", False
                    )
                    opts.set_preference("browser.download.dir", abs_folder)
                    opts.set_preference(
                        "browser.helperApps.neverAsk.saveToDisk",
                        "video/mp4,video/x-matroska,application/octet-stream",
                    )
                    return FirefoxDriver(options=opts)

                else:
                    opts = EdgeOptions()
                    opts.add_argument("--headless=new")
                    opts.add_argument("--log-level=3")
                    opts.add_argument("--silent")
                    opts.add_experimental_option(
                        "prefs",
                        {
                            "download.default_directory": abs_folder,
                            "profile.default_content_setting_values.automatic_downloads": 1,
                            "download.directory_upgrade": True,
                            "download.prompt_for_download": False,
                        },
                    )
                    return EdgeDriver(options=opts)

        except Exception as e:
            events.emit("log", f"SCRAPER ERROR: Failed to create {browser} driver: {e}")
            raise

    def quit_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                events.emit("log", f"SCRAPER: Error quitting driver: {e}")
            self.driver = None
            self.current_folder = None
            self.task_file_map = {}

    def check_no_links(self, task_id, display_name):
        try:
            if not self.driver:
                return False
            page_text = self.driver.page_source
            if "No download links or subtitles available" in page_text:
                events.emit("log", f"SCRAPER: No links for {display_name}. Skipping.")
                self.controller.missing_links.append(display_name)
                return True
        except Exception as e:
            events.emit("log", f"SCRAPER ERROR: Failed to check links: {e}")
        return False

    def _process_task(
        self,
        folder,
        tid,
        type_m,
        s,
        ep,
        media_name,
        quality,
        sub_only,
        video_only,
        is_retry,
    ):
        task_id = (
            f"{tid}_S{str(s).zfill(2) if s else '01'}E{str(ep).zfill(2)}"
            if s
            else f"MOVIE_{tid}"
        )
        display_name = (
            f"{media_name} - S{str(s).zfill(2) if s else '01'}E{str(ep).zfill(2)}"
            if s
            else media_name
        )

        events.emit("task_added", task_id, folder, display_name)
        time.sleep(0.1)

        if is_retry:
            events.emit("task_status_update", task_id, "RETRYING", 0.1)

        target_found = False
        if s:
            ep_pattern = (
                rf"[sS]0*{s}[eE]0*{ep}(?!\d)|0*{s}x0*{ep}(?!\d)|[eE]0*{ep}(?!\d)"
            )
            for f in os.listdir(folder):
                if re.search(ep_pattern, f, re.I):
                    if sub_only:
                        if f.lower().endswith(".srt"):
                            target_found = True
                            break
                    else:
                        if f.lower().endswith((".mp4", ".mkv")):
                            target_found = True
                            break
        else:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if sub_only:
                        if f.lower().endswith(".srt"):
                            target_found = True
                            break
                    else:
                        if not f.endswith(".crdownload") and f.lower().endswith(
                            (".mp4", ".mkv")
                        ):
                            if os.path.getsize(os.path.join(folder, f)) > 50000000:
                                target_found = True
                                break

        if target_found:
            events.emit(
                "log",
                f"SCRAPER: {display_name} already exists in {os.path.basename(folder)}. Skipping.",
            )
            events.emit(
                "task_status_update",
                task_id,
                "ALREADY FOUND" if sub_only else "FINISHED",
            )
            return True

        t_url = f"https://dl.vidsrc.vip/{type_m}/{tid}" + (
            f"/{s}/{ep}" if type_m == "tv" else ""
        )
        events.emit("log", f"SCRAPER: Fetching {display_name}...")
        events.emit("task_status_update", task_id, "FETCHING", 0.2)

        try:
            driver = self._get_driver(folder)

            nav_success = False
            for nav_attempt in range(2):
                try:
                    driver.get(t_url)
                    WebDriverWait(driver, 25).until(
                        lambda d: "No download links" in d.page_source
                        or len(d.find_elements(By.TAG_NAME, "button")) > 2
                    )
                    nav_success = True
                    break
                except TimeoutException:
                    if nav_attempt == 0:
                        driver.refresh()
                        time.sleep(3)
                except WebDriverException as e:
                    events.emit(
                        "log", f"SCRAPER: WebDriver error during navigation: {e}"
                    )
                    self.quit_driver()
                    driver = self._get_driver(folder)

            if not nav_success:
                events.emit("log", f"SCRAPER: Failed to load page for {display_name}")
                return False

        except Exception as e:
            events.emit("log", f"SCRAPER: Navigation critical error for {display_name}: {e}")
            return False

        try:
            if self.check_no_links(task_id, display_name):
                events.emit("task_status_update", task_id, "SKIPPED")
                return True

            success = False
            for attempt in range(3):
                if self.controller.stop_event.is_set():
                    break
                try:
                    time.sleep(3)
                    pre_count = len(
                        [f for f in os.listdir(folder) if f.endswith(".crdownload")]
                    )

                    target_q = quality
                    q_list = ["1080p", "720p", "480p"]
                    q_to_try = (
                        q_list[q_list.index(target_q) :]
                        if target_q in q_list
                        else q_list
                    )

                    btn = None
                    try:
                        btn = WebDriverWait(driver, 15).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, f"//button[contains(., '{target_q}')]")
                            )
                        )
                    except TimeoutException:
                        for q in q_to_try:
                            try:
                                btn = driver.find_element(
                                    By.XPATH, f"//button[contains(., '{q}')]"
                                )
                                if btn.is_displayed():
                                    break
                                btn = None
                            except NoSuchElementException:
                                continue

                    if not btn:
                        if self.check_no_links(task_id, display_name):
                            events.emit("task_status_update", task_id, "SKIPPED")
                            return True
                        raise Exception("Download buttons not found")

                    if not sub_only:
                        driver.execute_script("arguments[0].click();", btn)

                    sub_clicked = False
                    if not video_only:
                        try:
                            s_btn = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, "//button[contains(text(), 'Subtitle')]")
                                )
                            )
                            driver.execute_script("arguments[0].click();", s_btn)
                            time.sleep(1)
                            e_btn = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable(
                                    (
                                        By.XPATH,
                                        "//button[.//span[contains(text(), 'English')]]",
                                    )
                                )
                            )
                            driver.execute_script("arguments[0].click();", e_btn)
                            sub_clicked = True
                        except (TimeoutException, NoSuchElementException):
                            pass

                    started = False
                    found_filename = None
                    pattern = (
                        rf"[sS]0*{s}[eE]0*{ep}(?!\d)|0*{s}x0*{ep}(?!\d)|[eE]0*{ep}(?!\d)"
                        if s
                        else None
                    )

                    if sub_only and sub_clicked:
                        started = True
                    else:
                        for _ in range(40):
                            if self.controller.stop_event.is_set():
                                break
                            current_files = os.listdir(folder)

                            post_count = len(
                                [f for f in current_files if f.endswith(".crdownload")]
                            )

                            found_specific = False
                            if pattern:
                                for f in current_files:
                                    if re.search(pattern, f, re.I) and f.endswith(
                                        ".crdownload"
                                    ):
                                        found_specific = True
                                        found_filename = f.replace(".crdownload", "")
                                        break

                            if (
                                found_specific or post_count > pre_count
                            ) and not found_filename:
                                cr_files = [
                                    f
                                    for f in current_files
                                    if f.endswith(".crdownload")
                                ]
                                if cr_files:
                                    cr_files.sort(
                                        key=lambda x: os.path.getmtime(
                                            os.path.join(folder, x)
                                        ),
                                        reverse=True,
                                    )
                                    found_filename = cr_files[0].replace(
                                        ".crdownload", ""
                                    )

                            if found_specific or post_count > pre_count:
                                time.sleep(1)
                                started = True
                                break
                            time.sleep(0.5)

                    if started:
                        if found_filename:
                            self.task_file_map[task_id] = found_filename
                        events.emit("task_status_update", task_id, "DOWNLOADING", 0.5)
                        success = True
                        try:
                            driver.get("about:blank")
                        except:
                            pass
                        time.sleep(1.5)
                        break
                except Exception as e:
                    events.emit(
                        "log", f"SCRAPER: Attempt {attempt+1} failed for {display_name}: {e}"
                    )
                    driver.refresh()
                    time.sleep(4)

            if not success:
                self.controller.failed_tasks.append(
                    (folder, tid, type_m, s, ep, quality, sub_only, video_only)
                )
            return success

        except Exception as e:
            events.emit("log", f"SCRAPER CRITICAL ERROR for {display_name}: {e}")
            self.controller.failed_tasks.append(
                (folder, tid, type_m, s, ep, quality, sub_only, video_only)
            )
            return False

    def trigger_downloads(
        self,
        folder,
        tid,
        type_m,
        s=None,
        max_eps=1,
        start_ep=None,
        is_retry=False,
        media_name="Unknown",
        quality="1080p",
        sub_only=False,
        video_only=False,
    ):
        self.controller.current_target_folder = folder
        ep = start_ep if start_ep is not None else 1
        actual_max = max_eps if not is_retry else (start_ep if start_ep else max_eps)

        count_since_restart = 0
        while not self.controller.stop_event.is_set() and ep <= actual_max:
            if count_since_restart >= 100:
                events.emit(
                    "log", "SCRAPER: Refreshing driver session after 100 tasks..."
                )
                self.quit_driver()
                count_since_restart = 0

            if self._process_task(
                folder,
                tid,
                type_m,
                s,
                ep,
                media_name,
                quality,
                sub_only,
                video_only,
                is_retry,
            ):
                count_since_restart += 1
            ep += 1

    def trigger_selected_episodes(
        self,
        folder,
        tid,
        s,
        ep_list,
        is_retry=False,
        media_name="Unknown",
        quality="1080p",
        sub_only=False,
        video_only=False,
    ):
        self.controller.current_target_folder = folder
        count_since_restart = 0
        for ep in ep_list:
            if self.controller.stop_event.is_set():
                break
            if count_since_restart >= 100:
                events.emit(
                    "log", "SCRAPER: Refreshing driver session after 100 tasks..."
                )
                self.quit_driver()
                count_since_restart = 0

            if self._process_task(
                folder,
                tid,
                "tv",
                s,
                ep,
                media_name,
                quality,
                sub_only,
                video_only,
                is_retry,
            ):
                count_since_restart += 1
