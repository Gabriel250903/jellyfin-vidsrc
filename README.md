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
    git clone https://github.com/yourusername/jellyfin-vidsrc.git
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
    *   Open your terminal/command prompt and type `ipconfig`.
    *   Look for your **IPv4 Address** (e.g., `192.168.1.100`).
    *   Your URL should look like `http://192.168.1.100:8096`.
6.  Enable **"Show Jellyfin features"** to unlock the Live Dashboard.

### 💬 Setting up Discord Notifications (Optional)
Want to know when your show is ready while you're away?
1.  In your Discord server, go to **Server Settings > Integrations > Webhooks**.
2.  Create a **New Webhook**, name it, and copy the **Webhook URL**.
3.  Paste it into the **DISCORD WEBHOOK** field in the settings.

### 📁 Setting up Media Storage
The app is designed to keep your library perfectly organized for Jellyfin without any manual folder creation.
1.  In the app, click the **Folder Icon** ("Library Path") to select your main media directory (e.g., `C:\Jellyfin`).
2.  **Automatic Organization:** Once you select a root folder, the app will automatically create two subfolders: `/Movies` and `/Shows` (only upon downloading a movie and/or show). 
3.  **Smart Routing:** When you download a movie, it goes to `/Movies`. When you download a series, it goes to `/Shows`, complete with season subfolders and metadata. 
    *   *Note: If you accidentally select an existing `/Movies` or `/Shows` folder as the root, the app is smart enough to move up one level and maintain the correct structure.*

### 🎬 Setting Default Quality
You can control the resolution of your downloads to save space or ensure the highest fidelity.
1.  Open **Settings** and scroll down to **DEFAULT QUALITY**.
2.  Select between **480p**, **720p**, or **1080p**.
3.  **Note:** VidSrc primarily distributes within this range. Higher resolutions like 2K or 4K are not supported as they are rarely available.

---

## 🛠️ Usage Guide

### Step 1: Search and Select
*   Toggle between **TV Show** and **Movie** mode in the sidebar.
*   Type your query in the search bar. You can search by name or even by **TMDB ID** and the movie/show initial release year.
*   Click **SELECT** on the correct result. The app will automatically fetch the poster and season data.

### Step 2: Add to Queue
*   **Configure the Batch:** 
    *   **For TV Shows:** Choose a **Season Range** (e.g., Season 1 to 5) or use the **Episode Selector** to pick specific episodes.
    *   **Settings:** Set the **Threads** slider (determines how many downloads to attempt simultaneously).
*   **Run:** Click the green **START PROCESS** button. This will automatically add the media to the background queue manager.
*   **Multi-Tasking:** You can repeat the search and selection process for as many movies or shows as you like. Each time you hit **START PROCESS**, the item is added to the end of the queue.

### Step 3: Manage the Queue
*   **Pending Queue:** Click the **⏳ PENDING QUEUE** button in the sidebar to see all currently waiting tasks.
*   **Delete Tasks:** Inside the queue window, you can remove any specific movie or show from the list if you change your mind.

*💡 Performance Tip: It is recommended to keep your pending queue to **a maximum of 10 items**. Because each task can spawn multiple background threads, having a massive queue may cause the UI to become laggy.*

### Step 4: Automation in Action
Once a task reaches the front of the queue, the app takes over:
1.  **Scraping:** It launches a headless browser to find the best high-quality links.
2.  **Downloading:** Files are sent to your target folder.
3.  **Renaming:** The built-in **Watchdog** detects finished downloads and renames them to a professional format (e.g., `Movie Name (Year).mp4`).
4.  **Metadata:** It writes a `.nfo` file containing the plot, rating, and genres, and saves `poster.jpg`.
5.  **Finalizing:** If connected, it tells Jellyfin to scan the folder and sends a notification to your Discord.

---

## ⚠️ Known Limitations & Troubleshooting

### 🛑 Rate Limiting
*   **Media Scraping:** If you are batch-downloading hundreds of episodes at once, the source providers may occasionally rate-limit your connection. If this happens, some episodes might be skipped. **Always verify your download folder** after a large batch is finished to ensure every episode was successfully captured.
*   **Subtitle Provider:** The subtitle source is an external service that can experience high traffic. If the service is under heavy load, it may temporarily rate-limit requests, causing subtitles to fail for some files. This is an external factor and cannot be fixed within the app.

### 📝 Subtitle Language
*   **English Only:** Subtitles are currently only supported in English. This is because the underlying providers (VidSrc) rarely offer subtitle tracks in other languages.

---

## ✨ Features at a Glance
*   **Headless Scraping:** No annoying browser windows popping up.
*   **Professional Organization:** Automatic folder structures (`Show Name/Season 01/`).
*   **Subtitles:** English `.srt` files are automatically fetched and renamed to match your video.
*   **Live Dashboard:** Monitor server storage and active streams in real-time.
*   **History Management:** Keep track of what you've downloaded and delete items from your server directly from the app.

---

## ⚖️ Disclaimer
This project is for educational and personal use only. The developers do not host any media and are not responsible for how the tool is used. Please support official releases whenever possible.
