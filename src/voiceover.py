"""
Voiceover — generates a spoken MP3 from a script using ElevenLabs TTS.
"""

import os
from pathlib import Path


# Default voice: Laura — warm, natural, great for UGC
DEFAULT_VOICE_ID = "FGY2WhTYpPnrIDTdsKH5"
DEFAULT_MODEL    = "eleven_turbo_v2_5"   # fast, high quality, low latency


def generate_voiceover(script: str, output_path: str) -> str:
    """
    Generate a voiceover MP3 from a script string using ElevenLabs TTS.
    Returns the path to the saved MP3.
    """
    from elevenlabs.client import ElevenLabs

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set in .env")

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    model    = os.getenv("ELEVENLABS_MODEL", DEFAULT_MODEL)

    client = ElevenLabs(api_key=api_key)

    audio = client.text_to_speech.convert(
        text=script.strip(),
        voice_id=voice_id,
        model_id=model,
        output_format="mp3_44100_128",
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return output_path


def mix_voiceover(video_path: str, audio_path: str, output_path: str) -> str:
    """
    Mix a voiceover MP3 onto a silent video.
    The output duration matches the shorter of video or audio.
    Returns path to the output file.
    """
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v",
            "-map", "1:a",
            "-shortest",
            output_path,
        ],
        capture_output=True,
        check=True,
    )
    return output_path
