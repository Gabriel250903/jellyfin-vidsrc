import os
import re
import requests
import json
import time

SHOWS_DIR = r"C:\Jellyfin\Shows"
CONFIG_FILE = "jellyfin_config.json"
TMDB_KEYS = [
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
    "fb7bb23f03b6994dafc674c074d01761",
    "09ad8ace66eec34302943272db0e8d2c",
]


class Verifier:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
        )
        self.api_key = self.get_api_key()

    def get_api_key(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    key = json.load(f).get("api_key")
                    if key:
                        return key
            except:
                pass
        return TMDB_KEYS[2]

    def _get(self, url, retries=3):
        for i in range(retries):
            try:
                res = self.session.get(url, timeout=10)
                res.raise_for_status()
                return res.json()
            except:
                if i == retries - 1:
                    return None
                time.sleep(1)
        return None

    def get_tmdb_id(self, name, year=None):
        url = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={name}"
        if year:
            url += f"&first_air_date_year={year}"

        res = self._get(url)
        if not res or not res.get("results"):
            if year:
                url_no_year = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={name}"
                res = self._get(url_no_year)

        if res and res.get("results"):
            return res["results"][0]["id"]
        return None

    def get_season_data(self, tmdb_id):
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={self.api_key}"
        res = self._get(url)
        if not res:
            return {}
        return {
            s["season_number"]: s["episode_count"]
            for s in res.get("seasons", [])
            if s["season_number"] > 0
        }

    def scan_local_episodes(self, show_path):
        local_data = {}
        if not os.path.exists(show_path):
            return local_data

        for root, _, files in os.walk(show_path):
            for f in files:
                if f.lower().endswith((".mp4", ".mkv")):
                    match = re.search(r"[sS](\d+)\s*[eE](\d+)|(\d+)x(\d+)", f)
                    if match:
                        s = int(match.group(1) or match.group(3))
                        e = int(match.group(2) or match.group(4))
                        if s not in local_data:
                            local_data[s] = set()
                        local_data[s].add(e)
        return local_data

    def run(self):
        print("=" * 60)
        print("EPISODE VERIFIER")
        print("=" * 60)

        if not os.path.exists(SHOWS_DIR):
            print(f"ERROR: Directory not found: {SHOWS_DIR}")
            return

        shows = [
            d
            for d in os.listdir(SHOWS_DIR)
            if os.path.isdir(os.path.join(SHOWS_DIR, d))
        ]
        missing_report = []

        for show_folder in shows:
            year_match = re.search(r"\((\d{4})\)", show_folder)
            year = year_match.group(1) if year_match else None
            clean_name = re.sub(r"\(\d{4}\)", "", show_folder).strip()

            print(f"\nChecking: {show_folder}...", end="", flush=True)

            tmdb_id = self.get_tmdb_id(clean_name, year)
            if not tmdb_id:
                print(" [FAILED SEARCH]")
                continue

            expected = self.get_season_data(tmdb_id)
            if not expected:
                print(" [FAILED SEASON DATA]")
                continue

            local = self.scan_local_episodes(os.path.join(SHOWS_DIR, show_folder))

            show_has_missing = False
            first_missing_output = True
            for s_num, count in expected.items():
                local_eps = local.get(s_num, set())
                missing = [e for e in range(1, count + 1) if e not in local_eps]

                if missing:
                    if first_missing_output:
                        print(" [MISSING]")
                        first_missing_output = False
                    show_has_missing = True
                    msg = f"  Season {s_num}: Missing {len(missing)}/{count} eps -> {missing}"
                    print(msg)
                    missing_report.append(f"{show_folder} - S{s_num}: {missing}")

            if not show_has_missing:
                print(" [OK]")

        print("\n" + "=" * 60)
        if missing_report:
            print(
                f"SUMMARY: Found missing episodes in {len(set([m.split(' - ')[0] for m in missing_report]))} shows."
            )
            with open("missing_episodes.txt", "w") as f:
                f.write("\n".join(missing_report))
            print("Detailed report saved to: missing_episodes.txt")
        else:
            print("SUMMARY: Everything is complete! No missing episodes found.")
        print("=" * 60)


if __name__ == "__main__":
    Verifier().run()
    input("\nPress Enter to exit...")
