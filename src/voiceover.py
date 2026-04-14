"""
Voiceover — generates a spoken MP3 from a script using OpenAI TTS.
"""

import os
from pathlib import Path


# nova = warm, natural, good for UGC. Options: alloy, echo, fable, onyx, nova, shimmer
DEFAULT_VOICE = "nova"
DEFAULT_MODEL = "tts-1-hd"  # tts-1 is faster/cheaper, tts-1-hd is higher quality


def generate_voiceover(script: str, output_path: str) -> str:
    """
    Generate a voiceover MP3 from a script string using OpenAI TTS.
    Returns the path to the saved MP3.
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in .env")

    voice = os.getenv("OPENAI_TTS_VOICE", DEFAULT_VOICE)
    model = os.getenv("OPENAI_TTS_MODEL", DEFAULT_MODEL)

    client = OpenAI(api_key=api_key)

    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=script.strip(),
        response_format="mp3",
    )

    response.stream_to_file(output_path)
    return output_path


def mix_voiceover(video_path: str, audio_path: str, output_path: str) -> str:
    """
    Mix a voiceover MP3 onto a silent video.
    The output duration matches the longer of video or audio (-shortest behaviour
    can be controlled via the flag below).
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
            "-shortest",   # stop at the end of the shorter stream
            output_path,
        ],
        capture_output=True,
        check=True,
    )
    return output_path
