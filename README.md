# Lyrics to Video

**Audio + lyrics → `.lrc` → `.srt` → animated `.ass` → `.mp4` video**

A local application (no installation, no pip dependencies) that turns a song and its lyrics into a video with synchronized, animated subtitles. Everything runs on your computer: a lightweight Python file server serves the interface, and **FFmpeg** handles the final rendering.

Built entirely with the **Python standard library (3.8+)** and a single `index.html` file (HTML + CSS + JS, no build process, no frameworks).

---

## Getting Started

**Windows**

```bat
iniciar.bat
```

**Linux / macOS**

```sh
sh iniciar.sh
# or
python3 app.py
```

The server starts at `http://127.0.0.1:8765/` (automatically moves to the next available port if occupied) and opens your browser automatically.

**Close the terminal window to shut down the application.**

### Requirements

| Requirement | Where to get it |
|---|---|
| Python 3.8 or later | [python.org](https://www.python.org/downloads/) |
| `ffmpeg` (+ `ffprobe`) | Project's `ffmpeg/` folder — Windows binaries are already included; on Linux/macOS, place the binaries in `ffmpeg/` or install them system-wide |

> The app looks for FFmpeg in `ffmpeg/`, `ffmpeg/bin/`, and finally in the system `PATH`.
> Without it, the interface will open, but video generation will fail.

---

## The 4-Step Workflow

The interface features a sidebar with steps 1 → 4:

1. **Audio & Lyrics** — Select (or drag and drop) an audio file and paste the lyrics, **one line per verse line**. Empty lines are ignored. You can also import an existing `.lrc` file. The final video uses the same filename as the audio file.

2. **Synchronize** — Play the audio and mark each line at the exact moment it should appear. A large button and keyboard shortcuts let you set timestamps. The *reaction compensation* setting (150 ms by default) corrects for the delay between hearing the lyrics and clicking. You can go back one line, manually adjust timestamps, edit individual lines, and reset all markers.

3. **Style & Background** — Choose the font (fonts from the `fonts/` folder appear in the list, with a preview), size, colors, outline, bold formatting, position (top/middle/bottom), margins, entrance and exit animations (fade, slide up, slide down, zoom, pop) with durations in milliseconds. Choose a solid-color or image background (fill/fit), resolution, and a live preview that follows audio playback.

4. **Generate Video** — Review/edit the `.LRC`, download `.lrc` and `.srt` files, adjust the maximum duration per line, global subtitle offset, and FPS (24/30/60). Generate the `.mp4` with a progress bar, log output, cancel button, and a shortcut to open the output folder.

### Keyboard Shortcuts (Step 2)

| Key | Action |
|---|---|
| <kbd>Space</kbd> | Mark current line |
| <kbd>B</kbd> | Go back one line |
| <kbd>K</kbd> | Play / Pause |
| <kbd>J</kbd> | −5 seconds |
| <kbd>L</kbd> | +5 seconds |

The fixed bottom player includes play, ±5-second controls, a progress bar, and playback speed adjustment (0.5× to 1.25×).

---

## Folder Structure

```text
lrc_srt2/
├── app.py          # HTTP server + rendering pipeline (stdlib only)
├── index.html      # Complete interface (HTML/CSS/JS)
├── iniciar.bat     # Windows launcher
├── iniciar.sh     # Linux/macOS launcher
├── ffmpeg/         # FFmpeg binaries
├── fonts/          # (optional) Custom .ttf/.otf fonts used in preview and video
├── temp/           # Uploads and temporary files (cleared on every startup)
└── videos/         # Output: <audio filename>.mp4 + .lrc + .srt
```

---

## How It Works Internally

1. The uploaded audio is converted to **WAV PCM 48 kHz**. This exact file is played by the browser and used by FFmpeg, ensuring that synchronization timestamps match the final video precisely (MP3 VBR and encoder delay could otherwise cause timing differences between the browser and FFmpeg).

2. The timestamps are saved as `.lrc`; the `.lrc` file is then converted to `.srt`, respecting the maximum duration configured for each line.

3. The `.srt` file is converted into an animated `.ass` file. Each line is divided into *entrance* → *static* → *exit* segments, using tags such as `\fad`, `\move`, `\fscx/\fscy`, etc.

   Font sizes are scaled from a 1080p reference, ensuring consistent rendering at 480p, 720p, 1080p, vertical, or square resolutions.

4. FFmpeg renders the video using `libx264` (CRF 20) + AAC audio (192 kbps), `+faststart`, over a solid-color or image background, using fonts from the `fonts/` folder.

---

## Local API

Useful for automation and integration:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Main interface |
| GET | `/api/info` | FFmpeg path and version, output folder |
| GET | `/api/fonts` | Available fonts from the `fonts/` folder |
| GET | `/api/job?id=` | Job status (`running`, `done`, `error`, `cancelled`) |
| POST | `/api/upload?kind=audio&name=` | Uploads audio (converted to WAV) or an image |
| POST | `/api/render` | Starts rendering (JSON: audio, lrc/srt, style, background, resolution, fps) |
| POST | `/api/cancel` | Cancels the current job |
| POST | `/api/open-folder` | Opens the `videos/` folder in the file explorer |

The server listens exclusively on `127.0.0.1` (localhost).

---

## Troubleshooting

- **"FFmpeg not found"** — Place `ffmpeg` (+ `ffprobe`) in the `ffmpeg/` folder or add them to your system `PATH`.
- **"No subtitles to render"** — Synchronize at least one line in Step 2.
- **Audio "no longer available on the server"** — The `temp/` folder is cleared on every startup. Select the audio file again.
- **Lyrics appear "out of sync" (too early/too late)** — Adjust the *reaction compensation* in Step 2 and/or the global subtitle offset in Step 4.
- **Port 8765 is already in use** — The app automatically tries the next 20 ports.
