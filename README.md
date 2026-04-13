# VidSrc Jellyfin

**The ultimate bridge between VidSrc and your Jellyfin library.**

VidSrc Jellyfin is a sophisticated, all-in-one automation tool that scrapes media providers, organizes downloads into a professional library structure, fetches rich metadata via TMDB, and integrates directly with your Jellyfin server for a seamless "set it and forget it" experience.

---

## 🚀 Getting Started

### 1. Prerequisites
*   **Python:** 3.14 or higher installed.
*   **Browser:** [Microsoft Edge](https://www.microsoft.com/edge), [Google Chrome](https://www.google.com/chrome/), or [Mozilla Firefox](https://www.mozilla.org/firefox/) (The app supports these browsers for headless scraping, selectable in Settings).

### 2. Installation
1.  **Clone the Repo:**
    ```bash
    git clone https://github.com/Gabriel250903/jellyfin-vidsrc.git
    cd jellyfin-vidsrc
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Launch the App:**
    ```bash
    python main.py
    ```

---

## ⚙️ Configuration (The "How-To")

To unlock the full power of the app, click the **Gear Icon** in the sidebar to open Settings.

### 🎮 Discord Rich Presence (RPC)
The app now includes a fully customizable Discord RPC that shows what you are currently watching on your Jellyfin server.
1.  Click the **🎮 Discord RPC** button in the sidebar.
2.  **Toggle "Enable Discord RPC"** to start showing your activity.
3.  **Customization:**
    *   **Client ID:** Use the default or provide your own Discord Application ID.
    *   **Target User:** Filter the presence to only show when a specific user is watching.
    *   **Features:** Toggle playback time, server name, and interactive "View on TMDB" buttons.
4.  **Assets:** If using a custom ID, ensure you upload `jellyfin_logo`, `play`, and `pause` to your Discord Developer Portal.

### 🔑 Setting up TMDB (Required for Search & Metadata)
The app uses The Movie Database (TMDB) to find movies, posters, and plot summaries.
1.  Go to [themoviedb.org](https://www.themoviedb.org/) and create a free account.
2.  Navigate to your **Account Settings > API**.
3.  Request an **API Key** (Developer).
4.  Copy the **API Key**.
5.  Paste it into the **TMDB API KEY** field in the app settings and click **Save**.

### 📽️ Setting up Jellyfin Integration (Optional for users who have a local Jellyfin server)
Connecting Jellyfin allows the app to trigger library scans and monitor your server.
1.  Open your **Jellyfin Dashboard**.
2.  Go to **Advanced > API Keys**.
3.  Create a new key named "VidSrc Jellyfin".
4.  Copy the key and paste it into the **API Key** field in the app's Jellyfin section.
5.  **Enter your Server URL:**
    *   Your URL should look like `http://192.168.1.100:8096`.
6.  Enable **"Show Jellyfin features"** to unlock the Live Dashboard and RPC tracking.

### 💬 Setting up Notifications (Optional)
Want to know when your show is ready while you're away?
1.  **Discord:** In your Discord server, go to **Server Settings > Integrations > Webhooks**, create a **New Webhook**, and paste the URL into the app settings.
2.  **Windows Toasts:** The app uses `win11toast` to send native Windows 11 notifications when a download finishes or a critical error occurs.

### 📁 Setting up Media Storage
The app is designed to keep your library perfectly organized for Jellyfin without any manual folder creation.
1.  In the app, click the **Folder Icon** ("Library Path") to select your main media directory (e.g., `C:\Jellyfin`).
2.  **Lazy Folder Creation:** The app will not create any folders immediately.
3.  **Automatic Organization:** When you actually start a download, the app will automatically create the necessary subfolders: `/Movies` or `/Shows`, including season subfolders and metadata.
4.  **Smart Routing:** When you download a movie, it goes to `/Movies`. When you download a series, it goes to `/Shows`, complete with season subfolders and metadata. 

### 🎬 Setting Default Quality
You can control the resolution of your downloads to save space or ensure the highest fidelity.
1.  Open **Settings** and scroll down to **DEFAULT QUALITY**.
2.  Select between **480p**, **720p**, or **1080p**.

---

## 🛠️ Usage Guide

### Step 1: Search and Select
*   Toggle between **TV Show** and **Movie** mode in the sidebar.
*   Type your query in the search bar. You can search by name or even by **TMDB ID**.
*   Click **SELECT** on the correct result. **Auto-Switch Mode:** If you click a movie from your history while in "TV Show" mode, the app will automatically switch modes for you.

### Step 2: Add to Queue
*   **Configure the Batch:** 
    *   **For TV Shows:** Choose a **Season Range** or use the **Episode Selector** to pick specific episodes.
*   **Run:** Click the green **START PROCESS** button. This will automatically add the media to the background queue manager.

### Step 3: Manage the Queue
*   **Parallel Processing:** The app supports multiple worker threads (default: 2), allowing you to download multiple movies or shows simultaneously.
*   **Pending Queue Window:** Click the **⏳ PENDING QUEUE** button to see both **ACTIVE** tasks currently downloading and **PENDING** tasks waiting in line. You can reorder or delete pending tasks.

### Step 4: Automation in Action
Once a task reaches the front of the queue, the app takes over:
1.  **Headless Scraper:** It launches a persistent headless browser instance. For Chrome/Edge, it uses **CDP Dynamic Routing** to update download paths without restarting the browser.
2.  **Downloading:** Files are sent to your target folder. Real-time progress is mapped directly from the browser's download engine.
3.  **Renaming:** The built-in **Task-Isolated Watchdog** detects finished downloads and renames them professionally (e.g., `Show Name (2024) S01 E01.mp4`).
4.  **Metadata:** It writes advanced `.nfo` files for movies, shows, and individual episodes, and saves season posters as `folder.jpg`.
5.  **Finalizing:** If connected, it tells Jellyfin to scan the folder, sends a Discord notification, and triggers a Windows Toast.

---

## 📦 Standalone Bundling (.exe) & Updates

You can bundle the entire application into a single, portable Windows executable:

1.  **Install PyInstaller:**
    ```bash
    pip install pyinstaller
    ```
2.  **Run the Build Command:**
    ```bash
    pyinstaller --noconsole --onefile --name "VidSrcJellyfin" --icon="NONE" --add-data "api;api" --add-data "core;core" --add-data "ui;ui" main.py
    ```
3.  **Silent Updates:** For compiled versions, the app features an **Auto-Updater**. It silently downloads new releases in the background and presents a **"RESTART TO UPDATE"** button when ready.

---

## ✨ Features at a Glance
*   **🧵 Multi-Threaded Workers:** Process multiple downloads in parallel with isolated scraper instances.
*   **🚀 Persistent Scraper Pool:** Optimized browser lifecycle management using CDP to avoid CPU-heavy browser restarts.
*   **📊 Real Progress Tracking:** Accurate percentage-based progress bars synced with the browser's internal download engine.
*   **🔔 Native Notifications:** Windows 11 Toast notifications and Discord webhooks for instant status updates.
*   **📂 Full Metadata Automation:** Detailed `.nfo` generation for movies, shows, and episodes, including season posters.
*   **🔄 Auto-Mode Switching:** Seamlessly transitions between Movie and TV Show modes based on your selection.
*   **🎮 Discord Rich Presence:** Show off what you're watching with posters, progress bars, and TMDB links.
*   **⚡ Optimized State Management:** Debounced configuration saving to minimize Disk I/O and maintain UI snappiness.
*   **📦 Standalone Auto-Updater:** Background release downloading with one-click installation for `.exe` users.
*   **📊 Live Dashboard:** Monitor server storage and active streams in real-time.
*   **📜 History Management:** Keep track of downloads and delete server items directly from the app.

---

## ⚖️ Disclaimer
This project is for educational and personal use only. The developer does not host any media and is not responsible for how the tool is used. Please support official releases whenever possible.
