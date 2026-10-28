# Sahm Download Manager · سهم

A free IDM-style download manager for Windows and macOS — fast multi-connection downloads, pause/resume,
a scheduler, and one-click video downloads from YouTube and 1000+ sites. Arabic and English.

مدير تنزيلات مجاني لويندوز وماك — تنزيل سريع بعدة اتصالات، إيقاف واستئناف، جدولة، وتنزيل الفيديو من يوتيوب وأكثر من 1000 موقع بنقرة واحدة.

## ⬇ Download · التنزيل

Go to the **[Releases page](../../releases/latest)** and download:

| File | |
|---|---|
| **Sahm-Setup.exe** | Installer (recommended) · المثبّت (موصى به) |
| **Sahm-Portable.zip** | Windows, no install — extract and run `Sahm\Sahm.exe` · نسخة محمولة بدون تثبيت |
| **Sahm-macOS-AppleSilicon.dmg** | Mac with M1/M2/M3/M4 chip · ماك بمعالج Apple |
| **Sahm-macOS-Intel.dmg** | Older Mac with Intel chip · ماك بمعالج Intel |

Not sure which Mac you have?  → About This Mac → "Chip: Apple M…" = Apple Silicon, "Processor: Intel" = Intel.

Nothing else to install — video support is included.

**Windows:** if you see "Windows protected your PC", click **More info → Run anyway**.

**macOS:** open the .dmg and drag **Sahm** onto **Applications**. The first time you open it, macOS says it
can't verify the developer — click **Done**, then go to **System Settings → Privacy & Security**, scroll down
and click **Open Anyway** next to Sahm. You only do this once.

---

## For developers

## Features
- **Multi-connection downloads** – each file is split into up to 32 parts downloaded in parallel.
  When a part finishes early, Sahm splits the largest remaining part so every connection stays busy.
- **Pause / resume** – progress survives closing the app or a crash (`.sahmpart` file + saved state).
  Servers that don't support ranges still download, but restart from zero.
- **Queue** – set how many downloads run at once; "Add to queue" instead of "Start now".
- **Scheduler** – start the queue at a set time (e.g. 2:00 AM) and optionally stop it at another.
- **Speed limit** – global limit shared across all downloads.
- **Browser integration** – Chrome / Edge extension catches downloads (with cookies and referrer,
  so logged-in downloads work) plus a "Download with Sahm" right-click menu.
- **Arabic + English UI** with full right-to-left layout.
- **Video downloads (YouTube + 1000 sites)** – a "Download this video" button appears over videos,
  the extension badge counts video streams found on the page, and Sahm shows a quality list
  (1080p / 720p / … / audio M4A / MP3). Powered by yt-dlp + FFmpeg + Deno, bundled inside the program.
  yt-dlp updates itself daily in the background (copy kept in the Sahm data folder).
- Tray / menu-bar icon, completion notifications, auto-retry on network drops, optional start at login.

Data folder: Windows `%APPDATA%\Sahm`, macOS `~/Library/Application Support/Sahm`.

## Build it yourself
The easiest way is GitHub: publish a release and `.github/workflows/build.yml` builds the Windows installer
and both Mac versions automatically (Actions tab shows progress; files are attached to the release).

### Windows
1. Install **Python** from python.org – tick *Add python.exe to PATH*.
2. (Optional, for the setup file) install **Inno Setup 6**: https://jrsoftware.org/isdl.php
3. Open a command window in this folder and run:
   ```
   py build.py
   ```
   It installs the packages, builds the app, downloads yt-dlp / FFmpeg / Deno **once**
   (about 250 MB, cached in `vendor_tools\`) and packs them inside the program.
   - `dist\Sahm\Sahm.exe` – the app (video tools included in `dist\Sahm\tools`)
   - `dist\Sahm-Setup.exe` – the installer (if Inno Setup is installed)

People who install Sahm get video support immediately – no extra downloads or windows.

### macOS
On a Mac (build on an Apple Silicon Mac for the AppleSilicon version, on an Intel Mac for the Intel one):
```
python3 build.py
```
Result: `dist/Sahm.app` and `dist/Sahm-macOS-AppleSilicon.dmg` (or `-Intel.dmg`).

**Signing (optional, removes the "Open Anyway" step):** with an Apple Developer account ($99/year), set
`MAC_SIGN_IDENTITY` to your "Developer ID Application: …" certificate name before building, then notarize
the .dmg with `xcrun notarytool submit … --wait` and `xcrun stapler staple`.

## Install the browser extension
1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and pick the `extension` folder
   (after installing, it's at `C:\Program Files\Sahm\extension`, also in the Start menu).
4. Keep Sahm running – the extension icon shows "Connected".
   If Sahm is closed, downloads simply stay in the browser.

## Where data is stored
`%APPDATA%\Sahm\settings.json` and `downloads.json`. Default download folder: `Downloads\Sahm`.

## Project layout
```
app/main.py       entry point (also accepts: Sahm.exe <url>)
app/autostart.py  start at login (Windows registry / macOS LaunchAgent)
app/engine.py     segmented download engine
app/manager.py    list, queue, scheduler
app/server.py     local bridge for the extension (127.0.0.1:9614)
app/gui.py        PyQt6 interface
app/video.py      yt-dlp video engine
app/video_gui.py  quality picker + tool installer
app/tools.py      yt-dlp / FFmpeg / Deno management (Windows + macOS sources)
app/i18n.py       English / Arabic strings
extension/        Chrome/Edge MV3 extension
installer.iss     Inno Setup script (Windows)
build.py          one-command build for Windows and macOS
```

## Notes
- Windows SmartScreen may warn on first run because the exe isn't code-signed; click *More info → Run anyway*.
- Video: if YouTube says "Sign in to confirm you're not a bot", open the video in your browser while
  signed in and use the Sahm button on the video – your browser cookies are passed along.
- DRM-protected streams (Netflix, Shahid, OSN, Disney+…) cannot be downloaded.
- Only download videos you have the right to save.
