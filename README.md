# VidSrc Jellyfin

**The ultimate bridge between VidSrc and your Jellyfin library.**

VidSrc Jellyfin is a sophisticated, all-in-one automation tool that scrapes media providers, organizes downloads into a professional library structure, fetches rich metadata via TMDB, and integrates directly with your Jellyfin server for a seamless "set it and forget it" experience.

---

## 🚀 Getting Started

### 1. Prerequisites
*   **Python:** 3.14 or higher installed.
*   **Browser:** [Microsoft Edge](https://www.microsoft.com/edge) (The app currently uses Edge for headless scraping).

*Note: More selenium drivers (Chrome, Firefox) support coming soon!*

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

### 💬 Setting up Discord Notifications (Optional)
Want to know when your show is ready while you're away?
1.  In your Discord server, go to **Server Settings > Integrations > Webhooks**.
2.  Create a **New Webhook**, name it, and copy the **Webhook URL**.
3.  Paste it into the **DISCORD WEBHOOK** field in the settings.

### 📁 Setting up Media Storage
The app is designed to keep your library perfectly organized for Jellyfin without any manual folder creation.
1.  In the app, click the **Folder Icon** ("Library Path") to select your main media directory (e.g., `C:\Jellyfin`).
2.  **Automatic Organization:** Once you select a root folder, the app will automatically create two subfolders: `/Movies` and `/Shows`. 
3.  **Smart Routing:** When you download a movie, it goes to `/Movies`. When you download a series, it goes to `/Shows`, complete with season subfolders and metadata. 

### 🎬 Setting Default Quality
You can control the resolution of your downloads to save space or ensure the highest fidelity.
1.  Open **Settings** and scroll down to **DEFAULT QUALITY**.
2.  Select between **480p**, **720p**, or **1080p**.

---

## 🛠️ Usage Guide

### Step 1: Search and Select
*   Toggle between **TV Show** and **Movie** mode in the sidebar.
*   Type your query in the search bar. You can search by name or even by **TMDB ID**.
*   Click **SELECT** on the correct result.

### Step 2: Add to Queue
*   **Configure the Batch:** 
    *   **For TV Shows:** Choose a **Season Range** or use the **Episode Selector** to pick specific episodes.
*   **Run:** Click the green **START PROCESS** button. This will automatically add the media to the background queue manager.

### Step 3: Manage the Queue
*   **Pending Queue:** Click the **⏳ PENDING QUEUE** button in the sidebar to see all currently waiting tasks.
*   **Delete Tasks:** Inside the queue window, you can remove or reorder tasks.

### Step 4: Automation in Action
Once a task reaches the front of the queue, the app takes over:
1.  **Scraping:** It launches a headless browser to find the best links.
2.  **Downloading:** Files are sent to your target folder.
3.  **Renaming:** The built-in **Watchdog** detects finished downloads and renames them professionally.
4.  **Metadata:** It writes `.nfo` files and saves `poster.jpg`.
5.  **Finalizing:** If connected, it tells Jellyfin to scan the folder and sends a Discord notification.

---

## 📦 Standalone Bundling (.exe)

You can bundle the entire application into a single, portable Windows executable:

1.  **Install PyInstaller:**
    ```bash
    pip install pyinstaller
    ```
2.  **Run the Build Command:**
    ```bash
    pyinstaller --noconsole --onefile --name "VidSrcJellyfin" --icon="NONE" --add-data "api;api" --add-data "core;core" --add-data "ui;ui" main.py
    ```
3.  **Result:** Your standalone app will be in the `dist/` folder. The app will automatically create and maintain `jellyfin_config.json` in the same directory as the `.exe`.

---

## ⚠️ Known Limitations & Troubleshooting

### 🛑 Rate Limiting
*   **Media Scraping:** If you are batch-downloading hundreds of episodes at once, providers may occasionally rate-limit your connection. **Always verify your download folder** after a large batch.
*   **Subtitle Provider:** Subtitle sources can experience high traffic and may temporarily rate-limit requests.

### 📝 Subtitle Language
*   **English Only:** Subtitles are currently only supported in English.

---

## ✨ Features at a Glance
*   **🚀 High-Performance UI:** Experience "Nuclear Resize Optimization" (Dynamic UI Hiding) for perfectly smooth 60FPS window movement and resizing.
*   **📱 Responsive & Robust Design:** All windows (Main, Settings, Dashboard) feature smart minimum/maximum constraints and adaptive grid layouts.
*   **🎮 Discord Rich Presence:** Show off what you're watching with posters, progress bars, and TMDB links.
*   **⚡ Optimized Resource Usage:** Zero Disk I/O on the main thread. Heavy background tasks and API checks are offloaded to dedicated threads.
*   **🧹 Smart Log Management:** Batched processing and automated log pruning (500-line cap) ensure long-term application speed.
*   **📦 Metadata Caching:** Efficiently fetches and stores TMDB/Jellyfin metadata to save API limits.
*   **👻 Headless Scraping:** No annoying browser windows popping up during the download process.
*   **🗂️ Professional Organization:** Automatic, industry-standard folder structures (`Show Name/Season 01/`).
*   **📊 Live Dashboard:** Monitor server storage and active streams in real-time.
*   **📜 History Management:** Keep track of downloads and delete server items directly from the app.

---

## ⚖️ Disclaimer
This project is for educational and personal use only. The developers do not host any media and are not responsible for how the tool is used. Please support official releases whenever possible.
