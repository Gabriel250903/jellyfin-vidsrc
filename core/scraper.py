import os
import time
import re
from tkinter import messagebox
import threading
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from contextlib import redirect_stderr


class VidSrcScraper:
    def __init__(self, app):
        self.app = app

    def create_driver(self, folder):
        abs_folder = os.path.abspath(folder)
        self.app.log(f"SCRAPER: Initializing driver for folder: {abs_folder}")
        opts = Options()
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

        try:
            with open(os.devnull, "w") as f, redirect_stderr(f):
                d = webdriver.Edge(options=opts)
            d.set_page_load_timeout(35)
            return d
        except Exception as e:
            self.app.log(f"SCRAPER ERROR: Failed to create Edge driver: {e}")
            raise

    def check_no_links(self, task_id, media_name):
        try:
            page_text = self.app.driver.page_source
            if "No download links or subtitles available" in page_text:
                self.app.log(f"SCRAPER: No links for {task_id}. Skipping.")
                self.app.missing_links.append(f"{media_name} - {task_id}")
                return True
        except:
            pass
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
        self.app.current_target_folder = folder
        if self.app.driver:
            try:
                self.app.driver.quit()
            except:
                pass
        self.app.driver = self.create_driver(folder)
        ep = start_ep if start_ep is not None else 1
        actual_max = max_eps if not is_retry else (start_ep if start_ep else max_eps)
        count_since_restart = 0

        while not self.app.stop_event.is_set() and ep <= actual_max:
            task_id = (
                f"S{str(s).zfill(2) if s else '01'}E{str(ep).zfill(2)}"
                if s
                else "MOVIE"
            )
            display_name = (
                f"{media_name} - {task_id.replace('S', 'S').replace('E', ' E')}"
                if s
                else media_name
            )

            self.app.after(
                0,
                lambda tid=task_id, f=folder, dn=display_name: self.app.add_task_ui(
                    tid, f, dn
                ),
            )

            time.sleep(0.1)

            if is_retry:
                self.app.update_task_status(task_id, "RETRYING", 0.1)

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
                self.app.log(f"SCRAPER: {task_id} already exists. Skipping.")
                self.app.update_task_status(
                    task_id, "ALREADY FOUND" if sub_only else "FINISHED"
                )
                ep += 1
                continue

            if count_since_restart >= 5:
                self.app.log("SCRAPER: Refreshing session after 5 downloads...")
                self.app.wait_for_done(folder, quit_driver=False)
                try:
                    self.app.driver.quit()
                except:
                    pass
                self.app.driver = self.create_driver(folder)
                count_since_restart = 0

            t_url = f"https://dl.vidsrc.vip/{type_m}/{tid}" + (
                f"/{s}/{ep}" if type_m == "tv" else ""
            )
            self.app.log(f"SCRAPER: Fetching {task_id}...")
            self.app.update_task_status(task_id, "FETCHING", 0.2)

            try:
                nav_success = False
                for nav_attempt in range(2):
                    try:
                        self.app.driver.get(t_url)
                        WebDriverWait(self.app.driver, 25).until(
                            lambda d: "No download links" in d.page_source
                            or len(d.find_elements(By.TAG_NAME, "button")) > 2
                        )
                        nav_success = True
                        break
                    except:
                        if nav_attempt == 0:
                            self.app.driver.refresh()
                            time.sleep(3)

                if self.check_no_links(task_id, media_name):
                    self.app.update_task_status(task_id, "SKIPPED")
                    ep += 1
                    continue

                success = False
                for attempt in range(3):
                    if self.app.stop_event.is_set():
                        break
                    try:
                        time.sleep(3)
                        pre_count = len(
                            [f for f in os.listdir(folder) if f.endswith(".crdownload")]
                        )

                        target_q = quality
                        q_list = ["1080p", "720p", "480p"]
                        try:
                            start_idx = q_list.index(target_q)
                            q_to_try = q_list[start_idx:]
                        except:
                            q_to_try = q_list

                        btn = None
                        try:
                            btn = WebDriverWait(self.app.driver, 15).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, f"//button[contains(., '{target_q}')]")
                                )
                            )
                        except:
                            for q in q_to_try:
                                try:
                                    btn = self.app.driver.find_element(
                                        By.XPATH, f"//button[contains(., '{q}')]"
                                    )
                                    if btn.is_displayed():
                                        break
                                    else:
                                        btn = None
                                except:
                                    continue

                        if not btn:
                            if self.check_no_links(task_id, media_name):
                                self.app.update_task_status(task_id, "SKIPPED")
                                success = True
                                break
                            raise Exception("Buttons not found")

                        if not sub_only:
                            self.app.driver.execute_script("arguments[0].click();", btn)

                        sub_clicked = False
                        if not video_only:
                            try:
                                s_btn = WebDriverWait(self.app.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (
                                            By.XPATH,
                                            "//button[contains(text(), 'Subtitle')]",
                                        )
                                    )
                                )
                                self.app.driver.execute_script(
                                    "arguments[0].click();", s_btn
                                )
                                time.sleep(1)
                                e_btn = WebDriverWait(self.app.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (
                                            By.XPATH,
                                            "//button[.//span[contains(text(), 'English')]]",
                                        )
                                    )
                                )
                                self.app.driver.execute_script(
                                    "arguments[0].click();", e_btn
                                )
                                sub_clicked = True
                            except:
                                pass

                        started = False
                        pattern = (
                            rf"[sS]0*{s}[eE]0*{ep}(?!\d)|0*{s}x0*{ep}(?!\d)|[eE]0*{ep}(?!\d)"
                            if s
                            else None
                        )
                        for _ in range(40):
                            if self.app.stop_event.is_set():
                                break
                            current_files = os.listdir(folder)
                            post_count = len(
                                [f for f in current_files if f.endswith(".crdownload")]
                            )
                            found_specific = False
                            if pattern and any(
                                re.search(pattern, f, re.I)
                                and f.endswith(".crdownload")
                                for f in current_files
                            ):
                                found_specific = True
                            if post_count > pre_count or found_specific:
                                started = True
                                break
                            time.sleep(0.5)

                        if started or (sub_only and sub_clicked):
                            self.app.update_task_status(task_id, "DOWNLOADING", 0.5)
                            success = True
                            count_since_restart += 1
                            time.sleep(1.5)
                            break
                    except:
                        self.app.driver.refresh()
                        time.sleep(4)

                if not success and not is_retry:
                    self.app.failed_tasks.append((folder, tid, type_m, s, ep))
                ep += 1
            except:
                if not is_retry:
                    self.app.failed_tasks.append((folder, tid, type_m, s, ep))
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
        self.app.current_target_folder = folder
        if self.app.driver:
            try:
                self.app.driver.quit()
            except:
                pass
        self.app.driver = self.create_driver(folder)
        count_since_restart = 0

        for ep in ep_list:
            if self.app.stop_event.is_set():
                break
            task_id = f"S{str(s).zfill(2)}E{str(ep).zfill(2)}"
            display_name = f"{media_name} - S{str(s).zfill(2)} E{str(ep).zfill(2)}"

            self.app.after(
                0,
                lambda tid=task_id, f=folder, dn=display_name: self.app.add_task_ui(
                    tid, f, dn
                ),
            )
            time.sleep(0.1)

            target_found = False
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

            if target_found:
                self.app.log(f"SCRAPER: {task_id} already exists. Skipping.")
                self.app.update_task_status(
                    task_id, "ALREADY FOUND" if sub_only else "FINISHED"
                )
                continue

            if count_since_restart >= 5:
                self.app.wait_for_done(folder, quit_driver=False)
                try:
                    self.app.driver.quit()
                except:
                    pass
                self.app.driver = self.create_driver(folder)
                count_since_restart = 0

            t_url = f"https://dl.vidsrc.vip/tv/{tid}/{s}/{ep}"
            self.app.log(f"SCRAPER: Fetching {task_id}...")
            self.app.update_task_status(task_id, "FETCHING", 0.2)

            try:
                nav_success = False
                for nav_attempt in range(2):
                    try:
                        self.app.driver.get(t_url)
                        WebDriverWait(self.app.driver, 25).until(
                            lambda d: "No download links" in d.page_source
                            or len(d.find_elements(By.TAG_NAME, "button")) > 2
                        )
                        nav_success = True
                        break
                    except:
                        if nav_attempt == 0:
                            self.app.driver.refresh()
                            time.sleep(3)

                if self.check_no_links(task_id, media_name):
                    self.app.update_task_status(task_id, "SKIPPED")
                    continue

                success = False
                for attempt in range(3):
                    if self.app.stop_event.is_set():
                        break
                    try:
                        time.sleep(3)
                        pre_count = len(
                            [f for f in os.listdir(folder) if f.endswith(".crdownload")]
                        )

                        target_q = quality
                        q_list = ["1080p", "720p", "480p"]
                        try:
                            start_idx = q_list.index(target_q)
                            q_to_try = q_list[start_idx:]
                        except:
                            q_to_try = q_list

                        btn = None
                        try:
                            btn = WebDriverWait(self.app.driver, 15).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, f"//button[contains(., '{target_q}')]")
                                )
                            )
                        except:
                            for q in q_to_try:
                                try:
                                    btn = self.app.driver.find_element(
                                        By.XPATH, f"//button[contains(., '{q}')]"
                                    )
                                    if btn.is_displayed():
                                        break
                                    else:
                                        btn = None
                                except:
                                    continue

                        if not btn:
                            if self.check_no_links(task_id, media_name):
                                self.app.update_task_status(task_id, "SKIPPED")
                                success = True
                                break
                            raise Exception("Buttons not found")

                        if not sub_only:
                            self.app.driver.execute_script("arguments[0].click();", btn)

                        sub_clicked = False
                        if not video_only:
                            try:
                                s_btn = WebDriverWait(self.app.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (
                                            By.XPATH,
                                            "//button[contains(text(), 'Subtitle')]",
                                        )
                                    )
                                )
                                self.app.driver.execute_script(
                                    "arguments[0].click();", s_btn
                                )
                                time.sleep(1)
                                e_btn = WebDriverWait(self.app.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (
                                            By.XPATH,
                                            "//button[.//span[contains(text(), 'English')]]",
                                        )
                                    )
                                )
                                self.app.driver.execute_script(
                                    "arguments[0].click();", e_btn
                                )
                                sub_clicked = True
                            except:
                                pass

                        started = False
                        pattern = rf"[sS]0*{s}[eE]0*{ep}(?!\d)|0*{s}x0*{ep}(?!\d)|[eE]0*{ep}(?!\d)"
                        for _ in range(40):
                            if self.app.stop_event.is_set():
                                break
                            current_files = os.listdir(folder)
                            post_count = len(
                                [f for f in current_files if f.endswith(".crdownload")]
                            )
                            found_specific = False
                            if any(
                                re.search(pattern, f, re.I)
                                and f.endswith(".crdownload")
                                for f in current_files
                            ):
                                found_specific = True
                            if post_count > pre_count or found_specific:
                                started = True
                                break
                            time.sleep(0.5)

                        if started or (sub_only and sub_clicked):
                            self.app.update_task_status(task_id, "DOWNLOADING", 0.5)
                            success = True
                            count_since_restart += 1
                            time.sleep(1.5)
                            break
                    except:
                        self.app.driver.refresh()
                        time.sleep(4)

                if not success and not is_retry:
                    self.app.failed_tasks.append((folder, tid, "tv", s, ep))
            except:
                if not is_retry:
                    self.app.failed_tasks.append((folder, tid, "tv", s, ep))
