import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_DRIVE_CREDENTIALS_PATH = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH", "./credentials.json")

NUM_CUTS = int(os.getenv("NUM_CUTS", 4))
TARGET_DURATIONS = [int(d) for d in os.getenv("TARGET_DURATIONS", "15,30,30,45").split(",")]
OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "vertical")  # vertical | square | landscape
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
TEMP_DIR = os.getenv("TEMP_DIR", "./tmp")

# Map output format to ffmpeg scale + crop filter
FORMAT_FILTERS = {
    "vertical":  "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
    "square":    "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080",
    "landscape": "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
}

SUPPORTED_EXTENSIONS = {".mov", ".mp4", ".m4v"}

def validate():
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    if len(TARGET_DURATIONS) != NUM_CUTS:
        raise EnvironmentError(
            f"TARGET_DURATIONS has {len(TARGET_DURATIONS)} values but NUM_CUTS is {NUM_CUTS}. They must match."
        )
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
