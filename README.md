# 🎬 UGC Cut Generator

Automatically transform a folder of raw UGC clips into 3–4 distinct, ready-to-post video edits — each with a different vibe and viral hook — using Claude AI + FFmpeg.

## What it does

1. **Pulls clips** from a Google Drive folder (or local folder)
2. **Analyzes** each clip using Claude Vision — identifies content, energy, suitability as an opener
3. **Plans** 3–4 distinct edits, each with a unique viral hook and vibe (e.g. moody/atmospheric, high-energy FOMO, intimate/close-up)
4. **Assembles** each edit using FFmpeg and exports ready-to-post MP4s

## Example output

Given 25 raw venue clips, you get:

| Output | Hook | Vibe | Duration |
|---|---|---|---|
| `cut_1_moody.mp4` | Slow reveal of dimly lit bar | Atmospheric, cinematic | 30s |
| `cut_2_fomo.mp4` | Crowd energy opener | High energy, fast cuts | 15s |
| `cut_3_aesthetic.mp4` | Close-up food/drink detail | Aspirational, slow | 20s |
| `cut_4_walkthrough.mp4` | Wide entrance shot | Full venue tour | 45s |

---

## Requirements

- Python 3.10+
- FFmpeg installed (`brew install ffmpeg` on Mac)
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Google Drive API credentials (optional — can use local folder instead)

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/ugc-cut-generator.git
cd ugc-cut-generator

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 5. Run
python main.py --source drive --folder-url "https://drive.google.com/drive/folders/YOUR_ID"
# or with a local folder:
python main.py --source local --folder-path ./my_clips
```

## Google Drive Setup

To enable Drive integration, follow the guide in [`scripts/setup_drive.md`](scripts/setup_drive.md).

## Project Structure

```
ugc-cut-generator/
├── main.py               # Entry point + CLI
├── src/
│   ├── config.py         # Env + settings
│   ├── drive_client.py   # Google Drive download
│   ├── analyzer.py       # Frame extraction + Claude Vision
│   ├── planner.py        # Claude edit planning
│   └── assembler.py      # FFmpeg assembly
├── prompts/
│   ├── analyze_clip.md   # Claude prompt: clip analysis
│   └── plan_edits.md     # Claude prompt: edit planning
├── output/               # Generated MP4s land here
├── scripts/
│   └── setup_drive.md    # Drive API setup walkthrough
├── .env.example
├── requirements.txt
└── ARCHITECTURE.md
```

## Configuration

All settings live in `.env`. See `.env.example` for full reference.

Key settings:
- `ANTHROPIC_API_KEY` — required
- `NUM_CUTS` — how many edits to generate (default: 4)
- `TARGET_DURATIONS` — comma-separated seconds per cut (default: `15,30,30,45`)
- `OUTPUT_FORMAT` — `vertical` (9:16), `square` (1:1), or `landscape` (16:9)

## License

MIT
