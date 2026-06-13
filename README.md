# autoClipper 🎬✂️

`autoClipper` is a suite of automated Python tools designed for content creators. It streamlines the pipeline for processing long-form videos into short-form content (Shorts/Reels/TikToks).

## 🌟 Features

1. **`split.py` (Standard Splitter)**  
   Quickly slices any long video into fixed-length clips (e.g., 60 seconds) without re-encoding, preserving 100% of the original quality.
2. **`split_videos.py` (Vertical Converter & Splitter)**  
   Automatically detects landscape videos, pads them into a vertical 9:16 frame (with black bars to maintain the aspect ratio), and *then* splits them into short-form clips. 

---

## ⚙️ Installation & Setup

### Prerequisites

You will need **Python 3.11+** and **FFmpeg** installed on your system.

**Install FFmpeg:**
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt update && sudo apt install ffmpeg`
- **Windows:** `choco install ffmpeg`

### Setup the Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/pranavv00/autoClipper.git
   cd autoClipper
   ```

---

## 🚀 How to Use

### Splitting Videos (`split.py` or `split_videos.py`)

1. Place your long-form video files into a folder named `videos/` (next to the scripts).  
   *(Supported formats: .mp4, .mov, .mkv, .avi, .webm)*
2. By default, clips are cut into **60-second** intervals. You can change this by editing the `CLIP_DURATION` variable at the top of either script.
3. Run the desired script:
   ```bash
   # If your videos are already vertical
   python split.py
   
   # If you need them converted to vertical 9:16
   python split_videos.py
   ```
4. Your fresh clips will instantly appear organized in the `output/` folder!

---

## 📝 Configuration Options

You can easily tweak the behavior of the scripts by editing the variables at the top of the files:

- `CLIP_DURATION = 60` : Length of clips in seconds.
- `VERTICAL_WIDTH = 1080`, `VERTICAL_HEIGHT = 1920` : Output resolution for the vertical converter.
- `CRF_QUALITY = 18` : Video encoding quality for vertical conversions (lower is better, 18 is visually lossless).
- `ENCODING_PRESET = "ultrafast"` : Speed vs compression tradeoff.

---

## 🛡️ License

This project is open-source. Feel free to modify, distribute, and enhance it for your own workflow!
