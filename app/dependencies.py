"""
Pre-flight dependency checks.

Each function raises DependencyError with a friendly, actionable message
if its tool or package is unavailable. Call these at the start of a run,
before doing any work, so the user gets an immediate diagnosis instead of
a confusing mid-run failure.
"""

import shutil

from app.errors import DependencyError


def check_ffmpeg():
    """Raise DependencyError if FFmpeg is not on PATH."""
    if shutil.which("ffmpeg") is None:
        raise DependencyError(
            "FFmpeg was not found.\n"
            "Install it on macOS with:\n"
            "  brew install ffmpeg\n"
            "For other platforms visit: https://ffmpeg.org/download.html"
        )


def check_whisper():
    """Raise DependencyError if openai-whisper is not installed."""
    try:
        import whisper  # noqa: F401
    except ImportError:
        raise DependencyError(
            "The 'openai-whisper' package is not installed.\n"
            "Activate your virtual environment, then run:\n"
            "  pip install openai-whisper"
        )


def check_python_docx():
    """Raise DependencyError if python-docx is not installed."""
    try:
        import docx  # noqa: F401
    except ImportError:
        raise DependencyError(
            "The 'python-docx' package is not installed.\n"
            "Activate your virtual environment, then run:\n"
            "  pip install python-docx"
        )


def check_yt_dlp():
    """Raise DependencyError if yt-dlp is not installed."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise DependencyError(
            "yt-dlp is not installed.\n"
            "Install it with:\n"
            "  pip install yt-dlp"
        )
