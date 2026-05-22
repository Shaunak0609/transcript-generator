import argparse
import os
import shutil
import sys
import tempfile
import time
import traceback

from app.audio import extract_audio
from app.config import (
    DEFAULT_MODEL, DEFAULT_OUTPUT_DIR, SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS, TEMP_AUDIO_SUFFIX,
    VALID_FORMATS, VALID_MODELS, VALID_TEMPLATES,
)
from app.dependencies import check_ffmpeg, check_python_docx, check_whisper, check_yt_dlp
from app.errors import ConfigError, FileError, TranscriberError
from app.exporter import save
from app.formatter import apply_cleaning
from app.logger import get_logger, setup_logging
from app.notes import generate as generate_notes
from app.transcriber import run_whisper
from app.utils import (
    build_output_path, build_output_paths, validate_file, validate_language,
)
from app.youtube import download_audio, is_youtube_url, sanitize_title


# ── Argparse subclass ────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    """Raise ConfigError on bad arguments instead of printing and calling sys.exit."""

    def error(self, message):
        raise ConfigError(
            f"{message}\n"
            f"Run '{self.prog} --help' for usage information."
        )


# ── Shared pipeline ──────────────────────────────────────────────────────────

def _run_pipeline(video_input, source_lang, wants_translation, model_name, output_paths,
                  use_timestamps=False, metadata=None,
                  do_clean=False, do_remove_fillers=False, do_paragraphs=False,
                  do_summary=False, do_notes=False, template="default",
                  audio_override=None, save_temp=False):
    """Core pipeline: extract audio → transcribe → clean → summarize → save.

    audio_override: path to a pre-downloaded audio file (e.g. from YouTube).
      When set, the FFmpeg extraction step is skipped and this file is fed
      directly to Whisper.  Cleanup of audio_override is the caller's
      responsibility.
    save_temp: when True, the locally-extracted temp audio is not deleted.
    """
    log = get_logger()

    if audio_override:
        audio_path = audio_override
        temp_audio = None
    else:
        file_root  = os.path.splitext(video_input)[0]
        temp_audio = f"{file_root}{TEMP_AUDIO_SUFFIX}"
        audio_path = temp_audio

    source_label = video_input if audio_override else os.path.basename(video_input)
    task_label   = "translation" if wants_translation else "transcription"
    log.debug(
        f"Pipeline start | source={source_label} "
        f"| model={model_name} | task={task_label} "
        f"| formats={','.join(output_paths.keys())}"
    )
    start_time = time.monotonic()

    try:
        if not audio_override:
            extract_audio(video_input, temp_audio)

        result = run_whisper(audio_path, source_lang, wants_translation, model_name=model_name)

        text = apply_cleaning(
            result["text"],
            do_clean=do_clean,
            do_remove_fillers=do_remove_fillers,
            do_paragraphs=do_paragraphs,
        )
        segments = result.get("segments") if use_timestamps else None

        if do_notes or do_summary:
            notes_data = generate_notes(
                text,
                template=template if do_notes else "default",
                summary_only=(do_summary and not do_notes),
            )
            if metadata is None:
                metadata = {}
            metadata["notes"] = notes_data
            log.debug(
                f"Notes generated | template={notes_data['template']} "
                f"| sections={[row[0] for row in notes_data['layout']]}"
            )

        for fmt, path in output_paths.items():
            save(text, path, fmt, segments=segments, metadata=metadata)

    finally:
        if temp_audio and not save_temp and os.path.exists(temp_audio):
            os.remove(temp_audio)
        elif temp_audio and save_temp and os.path.exists(temp_audio):
            log.info(f"Extracted audio preserved at: {temp_audio}")

    elapsed = time.monotonic() - start_time
    log.debug(
        f"Pipeline end | {len(output_paths)} format(s) saved "
        f"| elapsed {elapsed:.1f}s"
    )
    log.info("\n" + "*" * 30 + "\n  PIPELINE FINISHED SUCCESSFULLY\n" + "*" * 30)


# ── Parser helpers ───────────────────────────────────────────────────────────

def _prog_name() -> str:
    """Return a user-friendly program name for help text."""
    name = os.path.basename(sys.argv[0]) if sys.argv else "transcribeflow"
    return f"python3 {name}" if name.endswith(".py") else name


def _add_shared_options(p: argparse.ArgumentParser) -> None:
    """Attach options that appear on both `transcribe` and `batch` subcommands."""
    p.add_argument(
        "--language", "-l",
        default=None,
        metavar="CODE",
        help=(
            "Source language code (e.g. ja, es, fr, de, zh). "
            "Omit to let Whisper auto-detect the language."
        ),
    )
    p.add_argument(
        "--translate",
        action="store_true",
        help="Translate audio to English instead of transcribing in the source language",
    )
    p.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        choices=VALID_MODELS,
        metavar="MODEL",
        help=(
            f"Whisper model size (default: {DEFAULT_MODEL}). "
            f"Choices: {', '.join(VALID_MODELS)}. "
            "Larger models are more accurate but slower and use more memory."
        ),
    )
    p.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory for output files, created if missing (default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--format", "-f",
        nargs="+",
        default=["docx"],
        choices=list(VALID_FORMATS),
        metavar="FORMAT",
        help=(
            f"Output format(s) (default: docx). "
            f"Choices: {', '.join(VALID_FORMATS)}. "
            "Pass multiple to export all at once, e.g. --format docx txt md json srt vtt"
        ),
    )
    p.add_argument(
        "--timestamps",
        action="store_true",
        help=(
            "Include per-segment timestamps in the output. "
            "Format: [HH:MM:SS - HH:MM:SS] text."
        ),
    )

    verbosity = p.add_argument_group(
        "output verbosity",
        "Control how much is printed to the terminal. "
        "All levels write the full DEBUG log to logs/.",
    )
    verbosity.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all progress output; show only warnings and errors",
    )
    verbosity.add_argument(
        "--verbose",
        action="store_true",
        help="Show extra detail: timing, word counts, output paths",
    )
    verbosity.add_argument(
        "--debug",
        action="store_true",
        help="Show full exception details and stack traces on error (implies --verbose)",
    )

    notes_group = p.add_argument_group(
        "summary and notes",
        "Local extractive summarization — no API or internet required.",
    )
    notes_group.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Prepend a short extractive summary and key terms to each output file. "
            "Uses word-frequency scoring — no LLM or API required."
        ),
    )
    notes_group.add_argument(
        "--notes",
        action="store_true",
        help="Prepend structured notes shaped by --template.",
    )
    notes_group.add_argument(
        "--template",
        default="default",
        choices=list(VALID_TEMPLATES),
        metavar="TEMPLATE",
        help=(
            f"Notes template to use with --notes (default: default). "
            f"Choices: {', '.join(VALID_TEMPLATES)}."
        ),
    )

    cleaning = p.add_argument_group(
        "transcript cleaning",
        "Optional post-processing applied before export. Flags can be combined freely.",
    )
    cleaning.add_argument(
        "--clean",
        action="store_true",
        help=(
            "Light cleanup: collapse repeated spaces, normalise line endings, "
            "fix space-before-punctuation, insert missing space after sentence ends."
        ),
    )
    cleaning.add_argument(
        "--remove-fillers",
        action="store_true",
        dest="remove_fillers",
        help=(
            "Remove common filler words: um, uh, 'you know', and filler 'like' "
            "(only when flanked by commas)."
        ),
    )
    cleaning.add_argument(
        "--paragraphs",
        action="store_true",
        help="Break the transcript into readable paragraphs (~4 sentences each).",
    )


def _build_parser() -> _Parser:
    prog = _prog_name()
    parser = _Parser(
        prog=prog,
        description="AI Video Transcriber & Translator — powered by OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
commands:
  transcribe   Transcribe or translate a single file or YouTube URL
  batch        Transcribe all media files in a directory

quick start:
  {prog} transcribe video.mp4
  {prog} transcribe video.mp4 --language ja --translate --format docx
  {prog} transcribe "https://youtu.be/..." --format docx md --summary
  {prog} batch ./videos --format docx --model small

old-style (still supported):
  python3 transcribe_video.py video.mp4 en
  python3 transcribe_video.py video.mp4 ja translate
""",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── transcribe ────────────────────────────────────────────────────────────
    t = sub.add_parser(
        "transcribe",
        help="Transcribe or translate a single video/audio file or YouTube URL",
        description="Transcribe or translate a video/audio file using OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
examples:
  {prog} transcribe video.mp4
  {prog} transcribe video.mp4 --language ja --translate
  {prog} transcribe video.mp4 --model small --format docx txt md json srt vtt
  {prog} transcribe video.mp4 --timestamps --clean --remove-fillers
  {prog} transcribe video.mp4 --notes --template lecture --format docx md
  {prog} transcribe "https://youtu.be/VIDEO_ID" --format docx md --summary
  {prog} transcribe "https://youtube.com/watch?v=VIDEO_ID" --translate --format docx
""",
    )
    t.add_argument(
        "video",
        help=(
            "Path to a local video/audio file, "
            "or a YouTube URL (requires yt-dlp: pip install yt-dlp). "
            "Only process content you have the rights or permission to use."
        ),
    )
    _add_shared_options(t)
    t.add_argument(
        "--save-temp",
        action="store_true",
        dest="save_temp",
        help=(
            "Keep the temporary audio file after processing. "
            "For local files: preserves the extracted MP3 next to the source. "
            "For YouTube: preserves the downloaded audio in its temp directory."
        ),
    )

    # ── batch ─────────────────────────────────────────────────────────────────
    b = sub.add_parser(
        "batch",
        help="Transcribe all supported media files in a directory",
        description=(
            "Scan a directory for video and audio files and transcribe each one "
            "using the same settings. Errors on individual files are reported but "
            "do not stop the batch unless --fail-fast is set."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
examples:
  {prog} batch ./videos
  {prog} batch ./videos --format docx txt --model small
  {prog} batch ./recordings --language ja --translate --format docx
  {prog} batch ./lectures --notes --template lecture --recursive
  {prog} batch ./videos --fail-fast --verbose
""",
    )
    b.add_argument(
        "directory",
        help="Path to the directory containing media files to process",
    )
    _add_shared_options(b)
    b.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Scan subdirectories recursively for media files",
    )
    b.add_argument(
        "--fail-fast",
        action="store_true",
        dest="fail_fast",
        help="Stop immediately if any file fails instead of continuing the batch",
    )

    return parser


# ── transcribe subcommand ────────────────────────────────────────────────────

def _run_new_style(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)
    log = get_logger()

    if args.command is None:
        parser.print_help()
        return

    is_url      = is_youtube_url(args.video)
    video_input = None if is_url else os.path.abspath(args.video)
    formats     = list(dict.fromkeys(args.format))

    check_ffmpeg()
    check_whisper()
    if "docx" in formats:
        check_python_docx()
    if is_url:
        check_yt_dlp()

    validate_language(args.language)
    if not is_url:
        validate_file(video_input)

    yt_tmpdir      = None
    audio_override = None
    stem_override  = None

    try:
        if is_url:
            yt_tmpdir = tempfile.mkdtemp(prefix="transcriber_yt_")
            audio_override, video_title = download_audio(args.video, yt_tmpdir)
            stem_override = sanitize_title(video_title)

        output_paths = build_output_paths(
            video_input or args.video,
            args.translate, args.language, args.output_dir, formats,
            stem_override=stem_override,
        )
        log.debug(f"Output directory: {args.output_dir}")
        log.debug(f"Output formats:   {', '.join(formats)}")

        _SUBTITLE_FORMATS = {"srt", "vtt"}
        use_timestamps = args.timestamps or bool(set(formats) & _SUBTITLE_FORMATS)

        cleaning_steps = [
            label for flag, label in (
                (args.clean,           "whitespace"),
                (args.remove_fillers,  "fillers removed"),
                (args.paragraphs,      "paragraphs"),
            ) if flag
        ]

        source_label = args.video if is_url else os.path.basename(video_input)
        metadata = {
            "source_file":       source_label,
            "language":          args.language or "auto",
            "model":             args.model,
            "translated":        args.translate,
            "has_timestamps":    use_timestamps,
            "do_clean":          args.clean,
            "do_remove_fillers": args.remove_fillers,
            "do_paragraphs":     args.paragraphs,
            "cleaning_steps":    cleaning_steps,
        }

        _run_pipeline(
            video_input or args.video,
            args.language, args.translate, args.model, output_paths,
            use_timestamps=use_timestamps,
            metadata=metadata,
            do_clean=args.clean,
            do_remove_fillers=args.remove_fillers,
            do_paragraphs=args.paragraphs,
            do_summary=args.summary,
            do_notes=args.notes,
            template=args.template,
            audio_override=audio_override,
            save_temp=args.save_temp,
        )

    finally:
        if yt_tmpdir:
            if args.save_temp:
                log.info(f"Downloaded audio preserved at: {yt_tmpdir}")
            else:
                shutil.rmtree(yt_tmpdir, ignore_errors=True)


# ── batch subcommand ─────────────────────────────────────────────────────────

def _run_batch_style(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)
    log = get_logger()

    directory = os.path.abspath(args.directory)
    if not os.path.isdir(directory):
        raise FileError(
            f"Directory not found: {directory}\n"
            "Check the path and try again."
        )

    # ── Collect files ─────────────────────────────────────────────────────────
    supported = SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS
    if args.recursive:
        files = []
        for root, _, filenames in os.walk(directory):
            for fname in sorted(filenames):
                if os.path.splitext(fname)[1].lower() in supported:
                    files.append(os.path.join(root, fname))
    else:
        files = sorted([
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
            and os.path.splitext(f)[1].lower() in supported
        ])

    if not files:
        print(f"No supported media files found in: {directory}", file=sys.stderr)
        log.warning(f"Batch: no supported files found in {directory}")
        return

    formats = list(dict.fromkeys(args.format))

    # ── Pre-flight checks (once, not per file) ────────────────────────────────
    check_ffmpeg()
    check_whisper()
    if "docx" in formats:
        check_python_docx()
    validate_language(args.language)

    _SUBTITLE_FORMATS = {"srt", "vtt"}
    use_timestamps = args.timestamps or bool(set(formats) & _SUBTITLE_FORMATS)

    cleaning_steps = [
        label for flag, label in (
            (args.clean,          "whitespace"),
            (args.remove_fillers, "fillers removed"),
            (args.paragraphs,     "paragraphs"),
        ) if flag
    ]

    log.info(f"Batch: {len(files)} file(s) in {directory}")
    print(f"Found {len(files)} file(s) — processing with model={args.model}, "
          f"formats={', '.join(formats)}\n")

    # ── Process each file ─────────────────────────────────────────────────────
    succeeded: list[str] = []
    failed:    list[tuple[str, str]] = []

    for i, file_path in enumerate(files, 1):
        fname = os.path.basename(file_path)
        log.info(f"Batch [{i}/{len(files)}]: {fname}")
        print(f"  [{i}/{len(files)}] {fname}", end="  ", flush=True)

        try:
            output_paths = build_output_paths(
                file_path, args.translate, args.language, args.output_dir, formats
            )
            metadata = {
                "source_file":       fname,
                "language":          args.language or "auto",
                "model":             args.model,
                "translated":        args.translate,
                "has_timestamps":    use_timestamps,
                "do_clean":          args.clean,
                "do_remove_fillers": args.remove_fillers,
                "do_paragraphs":     args.paragraphs,
                "cleaning_steps":    cleaning_steps,
            }
            _run_pipeline(
                file_path,
                args.language, args.translate, args.model, output_paths,
                use_timestamps=use_timestamps,
                metadata=metadata,
                do_clean=args.clean,
                do_remove_fillers=args.remove_fillers,
                do_paragraphs=args.paragraphs,
                do_summary=args.summary,
                do_notes=args.notes,
                template=args.template,
            )
            succeeded.append(fname)
            print("OK")

        except TranscriberError as e:
            failed.append((fname, str(e)))
            log.error(f"Batch [{i}/{len(files)}] FAILED: {fname}: {e}")
            print(f"FAILED\n    {e}", file=sys.stderr)
            if args.fail_fast:
                print("\nStopped early due to --fail-fast.", file=sys.stderr)
                break

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(succeeded) + len(failed)
    print(f"\n{'─' * 50}")
    print(f"Batch complete: {len(succeeded)}/{total} succeeded")
    if failed:
        print("Failed:")
        for fname, err in failed:
            print(f"  {fname}: {err}", file=sys.stderr)
    log.info(f"Batch done | {len(succeeded)} OK | {len(failed)} failed | total {total}")

    if failed:
        sys.exit(1)


# ── Old-style (positional argv) ──────────────────────────────────────────────

def _run_old_style(argv):
    if len(argv) < 2:
        raise ConfigError(
            "Not enough arguments.\n"
            "Usage:  python3 transcribe_video.py <video_path> <language_code> [translate]\n"
            "Or use the new interface:  transcribeflow transcribe --help"
        )

    if is_youtube_url(argv[0]):
        raise ConfigError(
            "YouTube URLs are only supported via the new-style interface.\n"
            'Use:  transcribeflow transcribe "URL" --format docx'
        )

    video_input = os.path.abspath(argv[0])
    source_lang = argv[1]
    wants_translation = len(argv) > 2 and argv[2].lower() == "translate"

    check_ffmpeg()
    check_whisper()
    check_python_docx()
    validate_language(source_lang)
    validate_file(video_input)

    final_doc = build_output_path(video_input, wants_translation, source_lang)
    _run_pipeline(video_input, source_lang, wants_translation, DEFAULT_MODEL, {"docx": final_doc})


# ── Error display ─────────────────────────────────────────────────────────────

def _print_error(err, debug=False):
    """Log the error to the log file and display it on stderr for the user."""
    log = get_logger()
    log.error(str(err), exc_info=debug)
    if debug and getattr(err, "details", None):
        log.error(f"Additional details:\n{err.details}")

    print(f"\nError: {err}", file=sys.stderr)
    if debug:
        if getattr(err, "details", None):
            print(f"\n[DEBUG] Additional details:\n{err.details}", file=sys.stderr)
        print("\n[DEBUG] Full traceback:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    # Pre-scan sys.argv so logging is active before argparse runs.
    debug   = "--debug"   in sys.argv
    quiet   = "--quiet"   in sys.argv or "-q" in sys.argv
    verbose = "--verbose" in sys.argv

    _logger, log_path = setup_logging(quiet=quiet, verbose=verbose, debug=debug)
    log = get_logger()

    if log_path:
        log.debug(f"Session log: {log_path}")

    argv = sys.argv[1:]

    try:
        if not argv or argv[0] in ("--help", "-h"):
            _build_parser().print_help()
            return
        if argv[0] == "transcribe":
            _run_new_style(argv)
        elif argv[0] == "batch":
            _run_batch_style(argv)
        else:
            _run_old_style(argv)

    except TranscriberError as e:
        _print_error(e, debug)
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nProcess stopped by user.", file=sys.stderr)
        log.warning("Run interrupted by user (KeyboardInterrupt).")
        sys.exit(0)

    except SystemExit:
        raise

    except Exception as e:
        log.critical(f"Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        print(f"\n[UNEXPECTED ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
