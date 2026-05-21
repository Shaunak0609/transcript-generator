import argparse
import os
import sys
import time
import traceback

from app.audio import extract_audio
from app.config import DEFAULT_MODEL, DEFAULT_OUTPUT_DIR, TEMP_AUDIO_SUFFIX, VALID_FORMATS, VALID_MODELS, VALID_TEMPLATES
from app.dependencies import check_ffmpeg, check_python_docx, check_whisper
from app.errors import ConfigError, TranscriberError
from app.exporter import save
from app.formatter import apply_cleaning
from app.logger import get_logger, setup_logging
from app.notes import generate as generate_notes
from app.transcriber import run_whisper
from app.utils import (
    build_output_path, build_output_paths, validate_file, validate_language,
)


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
                  do_summary=False, do_notes=False, template="default"):
    """Core pipeline: extract audio → transcribe → clean → summarize → save.

    Temp audio is always removed in the finally block, even on error or interrupt.
    """
    log = get_logger()
    file_root = os.path.splitext(video_input)[0]
    temp_audio = f"{file_root}{TEMP_AUDIO_SUFFIX}"

    task_label = "translation" if wants_translation else "transcription"
    log.debug(
        f"Pipeline start | file={os.path.basename(video_input)} "
        f"| model={model_name} | task={task_label} "
        f"| formats={','.join(output_paths.keys())}"
    )
    start_time = time.monotonic()

    try:
        extract_audio(video_input, temp_audio)
        result = run_whisper(temp_audio, source_lang, wants_translation, model_name=model_name)

        text = apply_cleaning(
            result["text"],
            do_clean=do_clean,
            do_remove_fillers=do_remove_fillers,
            do_paragraphs=do_paragraphs,
        )
        segments = result.get("segments") if use_timestamps else None

        # ── Notes / summary generation ────────────────────────────────────────
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
        if os.path.exists(temp_audio):
            os.remove(temp_audio)

    elapsed = time.monotonic() - start_time
    log.debug(
        f"Pipeline end | {len(output_paths)} format(s) saved "
        f"| elapsed {elapsed:.1f}s"
    )

    log.info("\n" + "*" * 30 + "\n  PIPELINE FINISHED SUCCESSFULLY\n" + "*" * 30)


# ── New-style (argparse subcommand) ─────────────────────────────────────────

def _build_parser():
    parser = _Parser(
        prog="python3 transcribe_video.py",
        description="AI Video Transcriber & Translator — powered by OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples (new style):
  python3 transcribe_video.py transcribe video.mp4
  python3 transcribe_video.py transcribe video.mp4 --language ja --translate
  python3 transcribe_video.py transcribe video.mp4 --model small --format docx txt md json
  python3 transcribe_video.py transcribe video.mp4 --format srt vtt
  python3 transcribe_video.py transcribe video.mp4 --timestamps
  python3 transcribe_video.py transcribe video.mp4 --clean --remove-fillers --paragraphs
  python3 transcribe_video.py transcribe video.mp4 --quiet
  python3 transcribe_video.py transcribe video.mp4 --verbose

examples (old style — still supported):
  python3 transcribe_video.py video.mp4 ja
  python3 transcribe_video.py video.mp4 ja translate
""",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    t = sub.add_parser(
        "transcribe",
        help="Transcribe or translate a video/audio file",
        description="Transcribe or translate a video/audio file using OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python3 transcribe_video.py transcribe video.mp4
  python3 transcribe_video.py transcribe video.mp4 --language ja --translate
  python3 transcribe_video.py transcribe video.mp4 --model small --output-dir outputs
  python3 transcribe_video.py transcribe video.mp4 --format docx txt md json srt vtt
  python3 transcribe_video.py transcribe video.mp4 --timestamps
  python3 transcribe_video.py transcribe video.mp4 --clean --remove-fillers --paragraphs
  python3 transcribe_video.py transcribe video.mp4 --language ja --translate --timestamps --format json
  python3 transcribe_video.py transcribe video.mp4 --quiet
  python3 transcribe_video.py transcribe video.mp4 --verbose
  python3 transcribe_video.py transcribe video.mp4 --debug
""",
    )

    t.add_argument("video", help="Path to the video or audio file to process")
    t.add_argument(
        "--language", "-l",
        default=None,
        metavar="CODE",
        help=(
            "Source language code (e.g. ja, es, fr, de, zh). "
            "Omit to let Whisper auto-detect the language."
        ),
    )
    t.add_argument(
        "--translate",
        action="store_true",
        help="Translate audio to English instead of transcribing in the source language",
    )
    t.add_argument(
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
    t.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory for output files, created if missing (default: {DEFAULT_OUTPUT_DIR})",
    )
    t.add_argument(
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
    t.add_argument(
        "--timestamps",
        action="store_true",
        help=(
            "Include per-segment timestamps in the output. "
            "Format: [HH:MM:SS - HH:MM:SS] text. "
            "Each segment is its own paragraph in DOCX, its own line in TXT, "
            "its own block in Markdown, and a structured entry in JSON."
        ),
    )

    # ── Output verbosity ──────────────────────────────────────────────────────
    verbosity = t.add_argument_group(
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

    # ── Summary and notes ─────────────────────────────────────────────────────
    notes_group = t.add_argument_group(
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
        help=(
            "Prepend structured notes shaped by --template. "
            "Includes summary, key points, and template-specific sections."
        ),
    )
    notes_group.add_argument(
        "--template",
        default="default",
        choices=list(VALID_TEMPLATES),
        metavar="TEMPLATE",
        help=(
            f"Notes template to use with --notes (default: default). "
            f"Choices: {', '.join(VALID_TEMPLATES)}. "
            "lecture → Key Concepts + Study Notes + Study Questions. "
            "meeting → Key Points + Action Items + Decisions. "
            "interview → Themes + Notable Moments. "
            "podcast → Highlights + Topics Discussed."
        ),
    )

    # ── Cleaning flags ────────────────────────────────────────────────────────
    cleaning = t.add_argument_group(
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
            "(only when flanked by commas). Conservative rules — 'I like this' is never touched."
        ),
    )
    cleaning.add_argument(
        "--paragraphs",
        action="store_true",
        help=(
            "Break the transcript into readable paragraphs (~4 sentences each). "
            "Has no visible effect on timestamped output (segments are already per-unit)."
        ),
    )

    return parser


def _run_new_style(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)
    log = get_logger()

    if args.command is None:
        parser.print_help()
        return

    video_input = os.path.abspath(args.video)
    formats = list(dict.fromkeys(args.format))  # deduplicate, preserve order

    # ── Pre-flight checks (fast, before any real work) ────────────────────────
    check_ffmpeg()
    check_whisper()
    if "docx" in formats:
        check_python_docx()

    validate_language(args.language)
    validate_file(video_input)

    # ── Output paths ──────────────────────────────────────────────────────────
    output_paths = build_output_paths(
        video_input, args.translate, args.language, args.output_dir, formats
    )
    log.debug(f"Output directory: {args.output_dir}")
    log.debug(f"Output formats:   {', '.join(formats)}")

    # Subtitle formats always need segment timing data regardless of --timestamps
    _SUBTITLE_FORMATS = {"srt", "vtt"}
    use_timestamps = args.timestamps or bool(set(formats) & _SUBTITLE_FORMATS)

    # ── Metadata ──────────────────────────────────────────────────────────────
    cleaning_steps = [
        label for flag, label in (
            (args.clean,           "whitespace"),
            (args.remove_fillers,  "fillers removed"),
            (args.paragraphs,      "paragraphs"),
        ) if flag
    ]

    metadata = {
        "source_file":       os.path.basename(video_input),
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
        video_input, args.language, args.translate, args.model, output_paths,
        use_timestamps=use_timestamps,
        metadata=metadata,
        do_clean=args.clean,
        do_remove_fillers=args.remove_fillers,
        do_paragraphs=args.paragraphs,
        do_summary=args.summary,
        do_notes=args.notes,
        template=args.template,
    )


# ── Old-style (positional argv) ──────────────────────────────────────────────

def _run_old_style(argv):
    if len(argv) < 2:
        raise ConfigError(
            "Not enough arguments.\n"
            "Usage:  python3 transcribe_video.py <video_path> <language_code> [translate]\n"
            "Or use the new interface:  python3 transcribe_video.py transcribe --help"
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
    """Log the error to the log file and display it on stderr for the user.

    The console logging handler excludes ERROR-level records, so logger.error()
    writes only to the log file.  The print() calls below are the user-visible
    display on stderr.
    """
    log = get_logger()

    # Log to file — include traceback in debug mode
    log.error(str(err), exc_info=debug)
    if debug and getattr(err, "details", None):
        log.error(f"Additional details:\n{err.details}")

    # User-facing stderr display
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
        raise  # let sys.exit() calls pass through untouched

    except Exception as e:
        # Unexpected error — always show the traceback regardless of --debug.
        log.critical(f"Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        print(f"\n[UNEXPECTED ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
