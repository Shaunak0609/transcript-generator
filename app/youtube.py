"""
YouTube audio download via yt-dlp.

yt-dlp is an optional dependency — a DependencyError with install
instructions is raised when a YouTube URL is passed but yt-dlp is absent.
FFmpeg is also required (for audio conversion); the existing check_ffmpeg()
pre-flight catches that case before this module is reached.
"""

import os
import re

from app.errors import AudioError, DependencyError
from app.logger import get_logger

_YOUTUBE_RE = re.compile(
    r"^https?://(www\.|m\.|music\.)?youtube\.com/"
    r"|^https?://youtu\.be/",
    re.IGNORECASE,
)


def is_youtube_url(s: str) -> bool:
    """Return True if *s* looks like a YouTube URL."""
    return bool(_YOUTUBE_RE.match(s.strip()))


def sanitize_title(title: str, max_len: int = 60) -> str:
    """Convert a video title into a safe, compact filesystem stem."""
    safe = re.sub(r"[^\w\s\-]", "", title).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:max_len] or "youtube_audio"


def download_audio(url: str, out_dir: str) -> tuple[str, str]:
    """Download audio from *url* and convert it to MP3 inside *out_dir*.

    Returns ``(audio_path, video_title)``.

    Raises DependencyError if yt-dlp is not installed.
    Raises AudioError  if the download or FFmpeg conversion fails.
    """
    log = get_logger()

    try:
        import yt_dlp
    except ImportError:
        raise DependencyError(
            "yt-dlp is not installed.\n"
            "Install it with:\n"
            "  pip install yt-dlp"
        )

    log.info("--- 1. DOWNLOADING YOUTUBE AUDIO ---")
    log.info(f"URL: {url}")
    log.info("Note: downloading and converting audio, please wait…")

    ydl_opts = {
        "format":       "bestaudio/best",
        "outtmpl":      os.path.join(out_dir, "audio.%(ext)s"),
        "postprocessors": [{
            "key":             "FFmpegExtractAudio",
            "preferredcodec":  "mp3",
            "preferredquality": "192",
        }],
        "quiet":      True,
        "no_warnings": True,
        "noprogress":  True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info  = ydl.extract_info(url, download=True)
            title = (info or {}).get("title", "youtube_audio")
    except Exception as e:
        msg  = str(e)
        hint = ""
        if "private" in msg.lower():
            hint = "\nThe video is private — only process content you have access to."
        elif "unavailable" in msg.lower() or "not available" in msg.lower():
            hint = "\nThe video may have been removed or is unavailable in your region."
        elif "sign in" in msg.lower() or "age" in msg.lower():
            hint = "\nThe video requires sign-in or is age-restricted."
        raise AudioError(
            f"yt-dlp failed to download audio from the URL.{hint}\n"
            "Check that the URL is valid and the video is publicly accessible.",
            details=f"yt-dlp error:\n{msg}",
        ) from e

    audio_path = os.path.join(out_dir, "audio.mp3")
    if not os.path.exists(audio_path):
        # Fallback: accept any non-partial audio file yt-dlp produced
        candidates = [
            f for f in os.listdir(out_dir)
            if f.startswith("audio") and not f.endswith(".part")
        ]
        if candidates:
            audio_path = os.path.join(out_dir, sorted(candidates)[0])
        else:
            raise AudioError(
                "yt-dlp ran but produced no audio file.\n"
                "Make sure FFmpeg is installed:  brew install ffmpeg"
            )

    log.info(f"Title:  {title}")
    log.info("Status: Download and audio extraction successful.")
    return audio_path, title
