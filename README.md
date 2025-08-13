# Valorant VOD Clip Extractor (PyQt6)

Minimal desktop MVP to extract 10-second clips from a VOD at specified timestamps and preview them in-app.

## Features
- Select a VOD file
- Enter match start offset (seconds)
- Provide fake event timestamps (relative to match start)
- Generate 10s clips (5s before/after each event) using FFmpeg
- Threaded extraction to keep the UI responsive
- In-app clip viewer with Play/Pause, Stop, Previous/Next, Seek
- Interactive clip list with context menu (Open Clip, Open Folder, Copy Path)

## Requirements
- Python 3.10+ recommended (works with 3.11/3.12/3.13)
- FFmpeg installed and on your system PATH
- PyQt6 (installed via `requirements.txt`)

### Install FFmpeg (Windows)
- winget:
  ```powershell
  winget install --id Gyan.FFmpeg -e --source winget
  ```
- Chocolatey:
  ```powershell
  choco install ffmpeg -y
  ```
- Verify:
  ```powershell
  ffmpeg -version
  ```

## Setup
```bash
python -m venv venv
# Windows PowerShell
venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Run
```bash
python main.py
```
The app opens maximized. Select your VOD, set the match start offset, edit timestamps, then click "Generate Clips". Clips are saved under `clips/`.

## How it works
- UI (`main.py`):
  - Grouped sections: Video Selection, Match Start, Fake Timestamps, Clip Generation, Generated Clips
  - Split-view layout: large in-app player on the left, controls on the right
  - Transport controls below the player on a single line
  - Palette-aware styling for dark/light themes
- Worker (`clip_worker.py`):
  - Computes video-relative timestamps by adding match offset to each fake timestamp
  - Cuts clips with FFmpeg. Default window: 5s before/5s after (10s total)
  - Emits signals so the UI updates progressively

## Adjustments
- Clip duration window: `main.py` inside `generateClips()` where `preSeconds` and `postSeconds` are defined
- Fake event timestamps defaults: `main.py` in `buildUi()` pre-filled text and fallback list in `generateClips()`
- FFmpeg command and encode settings: `clip_worker.py` `executeFfmpeg()`
- Player settings (volume, speed): `main.py` in `buildUi()` after creating `QMediaPlayer`

## Notes
- Ensure FFmpeg is installed and discoverable on PATH before generating clips
- The layout uses a splitter; you can drag the divider to resize panes
- The project is modular to allow future integration with Riot API or event detection

## Project structure
```
main.py                # PyQt6 GUI and in-app player
clip_worker.py         # Background worker that invokes FFmpeg
requirements.txt       # Python dependencies
clips/                 # Output clips (folder kept via .gitkeep)
```

## License
MIT
