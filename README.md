# YouTube Video Info Extractor.

**YouTube Video Info Extractor** is a command-line tool written in Python that helps you extract video information and Vietnamese subtitles from one or more YouTube links.

-----
## 🚀 Download
[**Download the latest release**](https://github.com/giaquy2000and4/LCTC-tool-pack/releases)

## 📥 Installation Guide
1. Download `LCTC-Pipeline.exe` from the link above.
2. Extract it if necessary (skip this step if it's a standalone `.exe`).
3. Run the program

## 📝 Changelog
### v3.0.0-alpha
- Fixed performance issues
- Optimized UI
- Added new features
- Resolved "error 429 too many requests" for yt-dlp

## Features

  - Extracts title, ID, duration, and URL of YouTube videos
  - Automatically downloads and cleans Vietnamese subtitles (both auto-generated and manual)
  - Saves results to `youtube_results.json` file
  - Exports subtitles and video info to the `subtitles/` directory
  - Interactive, user-friendly command-line menu
  - Automatically checks for and installs `yt-dlp` if not present

-----

## Requirements

  - Python 3.6+
  - `yt-dlp` package

> Note: The script will automatically check for and install `yt-dlp` if needed.

-----

## How to use

### 1\. Run the program

```bash
python3 title_sub.py
```

### 2\. Menu options

1.  **Select a file containing a list of URLs**
    (A `.txt` file with one YouTube link per line)

2.  **Enter URL directly**

3.  **View previous results**
    (Reads from `youtube_results.json` if it exists)

4.  **Export all subtitles to txt files**
    (Exports from previous results if available)

5.  **Exit program**

-----

## Output

  * JSON file: `youtube_results.json`

  * Directory: `subtitles/`

      * `sub.txt`: contains the cleaned Vietnamese subtitles
      * `info.txt`: contains basic video information

-----

## 📄 Input file structure (example)

```txt
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://youtu.be/abcdEFGhijk
```

> Supports formats like `youtube.com`, `youtu.be`, `embed`, etc.

-----

## Notes

  * The program handles errors and invalid URLs gracefully
  * Subtitles will be filtered to remove timestamps, HTML tags, and special characters
  * Ensure your computer has an internet connection to download subtitles
