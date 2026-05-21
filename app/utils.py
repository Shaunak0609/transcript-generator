import os
import re

from app.config import SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS
from app.errors import ConfigError, ExportError, FileError


def validate_file(path):
    """Check that the input file exists, has a supported extension, and is non-empty."""
    if not os.path.exists(path):
        raise FileError(
            f"File not found: {path}\n"
            "Check the path and try again."
        )

    ext = os.path.splitext(path)[1].lower()
    supported = SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS
    if ext not in supported:
        video_exts = "  " + ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        audio_exts = "  " + ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise FileError(
            f"Unsupported file type: '{ext}'\n"
            f"Supported video formats:\n{video_exts}\n"
            f"Supported audio formats:\n{audio_exts}"
        )

    if os.path.getsize(path) == 0:
        raise FileError(
            f"The file is empty (0 bytes): {os.path.basename(path)}\n"
            "Make sure the file was fully downloaded or transferred."
        )


def validate_output_dir(path):
    """Create the output directory if it does not exist; verify it is writable."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise ExportError(
            f"Could not create output directory: {path}\n"
            f"Reason: {e.strerror}"
        ) from e

    if not os.access(path, os.W_OK):
        raise ExportError(
            f"Output directory is not writable: {path}\n"
            "Check the folder permissions and try again."
        )


def validate_language(code):
    """Raise ConfigError if the language code looks syntactically invalid."""
    if code and not re.fullmatch(r"[a-zA-Z]{2,3}", code):
        raise ConfigError(
            f"Invalid language code: '{code}'\n"
            "Use a 2- or 3-letter ISO 639-1 code, e.g.  en  ja  fr  de  zh.\n"
            "Omit --language to let Whisper auto-detect."
        )


def build_output_path(video_path, wants_translation, source_lang):
    """Old-style: output placed next to the source video, always .docx."""
    file_root = os.path.splitext(video_path)[0]
    if wants_translation:
        return f"{file_root}_translated.docx"
    return f"{file_root}_transcript_{source_lang}.docx"


def build_output_paths(video_path, wants_translation, source_lang, output_dir, formats):
    """New-style: one output file per format, placed in output_dir.

    Naming rules:
      Transcription:  {basename}_transcript_{lang}.{ext}  (lang = code or 'auto')
      Translation:    {basename}_translated_en.{ext}       (Whisper always targets English)
    """
    validate_output_dir(output_dir)
    basename = os.path.splitext(os.path.basename(video_path))[0]
    if wants_translation:
        stem = f"{basename}_translated_en"
    else:
        lang_suffix = f"_{source_lang}" if source_lang else "_auto"
        stem = f"{basename}_transcript{lang_suffix}"
    return {fmt: os.path.join(output_dir, f"{stem}.{fmt}") for fmt in formats}
