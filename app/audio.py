import os
import subprocess

from app.errors import AudioError
from app.logger import get_logger


def extract_audio(video_path, audio_path):
    """Extract audio from a video file to a temporary MP3 using FFmpeg."""
    log = get_logger()
    log.info("--- 1. EXTRACTING AUDIO ---")
    log.info(f"Input:  {os.path.basename(video_path)}")
    log.debug(f"Full path: {video_path}")

    command = [
        "ffmpeg", "-y", "-i", video_path, "-vn",
        "-acodec", "libmp3lame", "-q:a", "2", audio_path,
    ]

    try:
        subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError:
        raise AudioError(
            "FFmpeg was not found.\n"
            "Install it on macOS with:  brew install ffmpeg"
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace").strip()

        hint = ""
        if "moov atom not found" in stderr:
            hint = "\nThe file appears to be incomplete or truncated."
        elif "Invalid data found" in stderr or "Invalid argument" in stderr:
            hint = "\nThe file may be corrupted or use an unsupported codec."
        elif "No such file" in stderr:
            hint = "\nVerify the file path is correct."

        raise AudioError(
            f"FFmpeg failed to extract audio from '{os.path.basename(video_path)}'.{hint}\n"
            "Run with --debug to see full FFmpeg output.",
            details=f"FFmpeg stderr:\n{stderr}",
        ) from e

    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise AudioError(
            f"FFmpeg ran but produced no audio from '{os.path.basename(video_path)}'.\n"
            "The file may contain no audio track."
        )

    log.info("Status: Audio extraction successful.")
