# Site AI Creation Editor

Paste a website address. The app opens the site in a real (headless) browser, reads the
start page **and the most useful pages it links to** (About, Pricing, Products…), pulls out
the brand's colours, logo, images and text, writes a video script, and renders a
marketing video (MP4, 1080p) with animated text, a voiceover and optional music.

Runs entirely on your own computer. No paid services needed.

## What you need (Windows 11)
1. **Python 3.10+**: `winget install Python.Python.3.12`
2. **ffmpeg**: `winget install Gyan.FFmpeg`  (close and reopen the terminal afterwards)
3. *(Optional but recommended)* a free **Gemini API key** from https://aistudio.google.com/apikey
   — without it the app still works, but the script is basic.

## First-time setup
Double-click `setup.bat` (or run the commands inside it by hand).
Then open the new `.env` file and paste your key after `GEMINI_API_KEY=`.

## Run
Double-click `run.bat`, or:
```
venv\Scripts\activate
python app.py
```
Open http://localhost:5000, paste a URL, click **1. Read site & write script**, edit any
text you like, then click **2. Make the video**. Finished videos are saved in `output/`.

## Music (optional)
Drop one royalty-free `.mp3` into `assets/music/`. It is mixed in quietly under the voice.

## Voices
Pick a voice in the page. Nigerian English voices are included. More voices:
`edge-tts --list-voices`. The voiceover needs an internet connection (free Microsoft service);
if it is unavailable the video is still made, silent.

## Tips for a modest laptop (8 GB RAM)
- Close Chrome and other heavy apps while rendering.
- A 45-second video takes a few minutes to render.
- Keep "Pages to read" at 4 or fewer.

## Files
| File | Job |
|---|---|
| `app.py` | Local web server and job runner |
| `crawler.py` | Reads the site: pages, text, colours, logo, images, screenshots |
| `storyboard.py` | Writes the scene-by-scene script (Gemini, or a basic offline fallback) |
| `renderer.py` | Draws scenes, makes voiceover, animates and joins with ffmpeg |
| `static/index.html` | The editor page |

## Security
Never commit `.env`. It is already in `.gitignore`.
