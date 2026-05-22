"""
Streamlit UI for AI Video Transcriber & Translator.

All transcription, audio, formatting, export, and notes logic is delegated
to the existing app/ modules — nothing is duplicated here.
"""

import json
import os
import re
import shutil
import tempfile

import streamlit as st

from app.audio import extract_audio
from app.config import TEMP_AUDIO_SUFFIX, VALID_FORMATS, VALID_MODELS, VALID_TEMPLATES
from app.dependencies import check_ffmpeg, check_python_docx, check_whisper, check_yt_dlp
from app.errors import TranscriberError
from app.exporter import save
from app.formatter import apply_cleaning
from app.logger import get_logger, setup_logging
from app.notes import generate as generate_notes
from app.transcriber import run_whisper
from app.youtube import download_audio, is_youtube_url, sanitize_title

# ── Logging — file handler only, idempotent ───────────────────────────────────

setup_logging(quiet=False, verbose=False, debug=False)

# ── Constants ─────────────────────────────────────────────────────────────────

LANGUAGE_OPTIONS: dict[str, str | None] = {
    "Auto-detect":         None,
    "English":             "en",
    "Japanese":            "ja",
    "Spanish":             "es",
    "French":              "fr",
    "German":              "de",
    "Hindi":               "hi",
    "Arabic":              "ar",
    "Chinese":             "zh",
    "Other (manual code)": "__manual__",
}

MIME_TYPES: dict[str, str] = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt":  "text/plain",
    "md":   "text/markdown",
    "json": "application/json",
    "srt":  "text/plain",
    "vtt":  "text/vtt",
}

SUPPORTED_EXTENSIONS = [
    "mp4", "mov", "mkv", "avi", "webm", "m4v",
    "mp3", "wav", "m4a", "flac", "ogg",
]

_SUBTITLE_FMTS = {"srt", "vtt"}   # cannot be regenerated from edited plain text


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Video Transcriber",
    page_icon="🎙",
    layout="wide",
)


# ── Session state defaults ────────────────────────────────────────────────────

_STATE_DEFAULTS: dict = {
    "results":             None,   # dict: text, segments, metadata, output_files, stem
    "output_dir":          None,   # temp dir holding output files
    "error":               None,   # user-facing error from last pipeline run
    "_last_upload_name":   None,   # detect local file change
    "_last_youtube_url":   None,   # detect YouTube URL change
    "_editor_stem":        None,   # which result set the editor was initialised for
    "edited_output_files": None,   # dict fmt->path for regenerated exports
    "regen_error":         None,   # error string from the regeneration step
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cleanup_output_dir() -> None:
    path = st.session_state.output_dir
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    st.session_state.output_dir = None


def _run_pipeline(
    input_path: str,
    language_code: str | None,
    wants_translation: bool,
    model_name: str,
    use_timestamps: bool,
    do_clean: bool,
    do_remove_fillers: bool,
    do_paragraphs: bool,
    do_summary: bool,
    do_notes: bool,
    template: str,
    formats: list[str],
    status,
    audio_override: str | None = None,   # pre-downloaded audio (YouTube)
    stem_override: str | None  = None,   # custom output filename stem
) -> dict:
    """Run the full transcription pipeline, reporting progress into a st.status box."""
    log = get_logger()
    stem = stem_override or os.path.splitext(os.path.basename(input_path))[0]

    if audio_override:
        audio_path = audio_override
        temp_audio = None
    else:
        temp_audio = os.path.splitext(input_path)[0] + TEMP_AUDIO_SUFFIX
        audio_path = temp_audio

    try:
        if not audio_override:
            status.update(label="Extracting audio…", state="running")
            extract_audio(input_path, temp_audio)

        status.update(label="Running Whisper AI — this may take a minute…", state="running")
        result = run_whisper(audio_path, language_code, wants_translation, model_name=model_name)

        text     = result["text"]
        segments = result.get("segments", []) if use_timestamps else None

        if any([do_clean, do_remove_fillers, do_paragraphs]):
            status.update(label="Cleaning transcript…", state="running")
        text = apply_cleaning(
            text,
            do_clean=do_clean,
            do_remove_fillers=do_remove_fillers,
            do_paragraphs=do_paragraphs,
        )

        notes_data = None
        if do_notes or do_summary:
            status.update(label="Generating summary and notes…", state="running")
            notes_data = generate_notes(
                text,
                template=template if do_notes else "default",
                summary_only=(do_summary and not do_notes),
            )

        cleaning_steps = [
            label for flag, label in (
                (do_clean,          "whitespace"),
                (do_remove_fillers, "fillers removed"),
                (do_paragraphs,     "paragraphs"),
            ) if flag
        ]
        metadata: dict = {
            "source_file":       os.path.basename(input_path),
            "language":          language_code or "auto",
            "model":             model_name,
            "translated":        wants_translation,
            "has_timestamps":    use_timestamps,
            "do_clean":          do_clean,
            "do_remove_fillers": do_remove_fillers,
            "do_paragraphs":     do_paragraphs,
            "cleaning_steps":    cleaning_steps,
        }
        if notes_data:
            metadata["notes"] = notes_data

        status.update(label="Saving output files…", state="running")
        out_dir = tempfile.mkdtemp(prefix="transcriber_ui_")
        st.session_state.output_dir = out_dir

        if wants_translation:
            file_stem = f"{stem}_translated_en"
        else:
            lang_suffix = f"_{language_code}" if language_code else "_auto"
            file_stem = f"{stem}_transcript{lang_suffix}"

        output_files: dict[str, str] = {}
        for fmt in formats:
            out_path = os.path.join(out_dir, f"{file_stem}.{fmt}")
            save(text, out_path, fmt, segments=segments, metadata=metadata)
            output_files[fmt] = out_path

        log.debug(f"Streamlit pipeline complete | {len(output_files)} file(s) | dir={out_dir}")

        return {
            "text":         text,
            "segments":     segments,
            "metadata":     metadata,
            "output_files": output_files,
            "stem":         file_stem,
        }

    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)


def _save_edited_exports(edited_text: str, results: dict, out_dir: str) -> dict[str, str]:
    """Save the edited transcript to all regeneratable formats (SRT/VTT excluded).

    SRT and VTT rely on Whisper's per-segment timing and cannot be rebuilt
    from plain edited text.  All other formats write using the existing
    app.exporter.save() — no logic is duplicated here.
    """
    original_formats = set(results["output_files"].keys())
    regen_formats    = sorted(original_formats - _SUBTITLE_FMTS)

    # Preserve original metadata; strip notes (scored on the original text)
    metadata = {k: v for k, v in results["metadata"].items() if k != "notes"}
    metadata["edited"] = True

    stem = results["stem"] + "_edited"
    output_files: dict[str, str] = {}
    for fmt in regen_formats:
        path = os.path.join(out_dir, f"{stem}.{fmt}")
        save(edited_text, path, fmt, segments=None, metadata=metadata)
        output_files[fmt] = path

    return output_files


def _download_row(output_files: dict[str, str], key_prefix: str) -> None:
    """Render a row of download buttons for a dict of fmt -> file path."""
    valid = {fmt: p for fmt, p in output_files.items() if os.path.exists(p)}
    if not valid:
        return
    cols = st.columns(min(len(valid), 4))
    for i, (fmt, path) in enumerate(valid.items()):
        fname = os.path.basename(path)
        with open(path, "rb") as fh:
            data = fh.read()
        cols[i % len(cols)].download_button(
            label     = f"⬇ {fname}",
            data      = data,
            file_name = fname,
            mime      = MIME_TYPES.get(fmt, "application/octet-stream"),
            key       = f"{key_prefix}_{fmt}",
        )


def _copy_button(text: str) -> None:
    """Render an HTML button that writes `text` to the clipboard on click."""
    escaped = json.dumps(text)   # safe JS string with all special chars escaped
    st.components.v1.html(
        f"""
        <button
          onclick="navigator.clipboard.writeText({escaped})
            .then(()=>{{this.textContent='✓ Copied';
                        setTimeout(()=>this.textContent='Copy to clipboard',2000)}})
            .catch(()=>this.textContent='Copy not supported in this browser')"
          style="padding:5px 16px;border-radius:6px;border:1px solid #d1d5db;
                 background:#ffffff;cursor:pointer;font-size:14px;color:#374151;
                 font-family:sans-serif">
          Copy to clipboard
        </button>
        """,
        height=44,
    )


def _search_results(text: str, query: str) -> None:
    """Show match count and matching lines for `query` within `text`."""
    if not query:
        return
    q_lower  = query.lower()
    count    = text.lower().count(q_lower)
    if count == 0:
        st.caption("No matches found.")
        return

    st.caption(f"{count} occurrence{'s' if count != 1 else ''} found.")

    # Collect up to 20 lines that contain the query
    matching_lines = [
        ln for ln in text.splitlines()
        if q_lower in ln.lower()
    ][:20]

    if matching_lines:
        with st.expander(f"Show matching lines ({min(len(matching_lines), 20)})"):
            for line in matching_lines:
                # Highlight the match with <mark>
                highlighted = re.sub(
                    f"({re.escape(query)})",
                    r"<mark style='background:#fef08a'>\1</mark>",
                    line,
                    flags=re.IGNORECASE,
                )
                st.markdown(highlighted, unsafe_allow_html=True)


# ── Page header ───────────────────────────────────────────────────────────────

st.title("AI Video Transcriber & Translator")
st.caption(
    "Powered by OpenAI Whisper — runs entirely on your machine, "
    "no API key or internet connection required."
)


# ── Sidebar — settings ────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    task_label        = st.radio("Task", ["Transcribe", "Translate to English"])
    wants_translation = task_label == "Translate to English"

    st.divider()

    language_name = st.selectbox("Source Language", list(LANGUAGE_OPTIONS.keys()))
    if language_name == "Other (manual code)":
        raw_code      = st.text_input(
            "ISO 639-1 / 639-2 code",
            max_chars=3,
            placeholder="e.g.  ko  pt  ru",
        ).strip().lower()
        language_code = raw_code or None
    else:
        language_code = LANGUAGE_OPTIONS[language_name]

    st.divider()

    model_name = st.selectbox(
        "Whisper Model",
        VALID_MODELS,
        index=list(VALID_MODELS).index("base"),
        help=(
            "tiny / base — fast, good for clear speech.  "
            "small / medium / large — slower, more accurate."
        ),
    )

    st.divider()

    st.subheader("Output Formats")
    col_a, col_b = st.columns(2)
    fmt_checks: dict[str, bool] = {}
    for i, fmt in enumerate(VALID_FORMATS):
        col = col_a if i % 2 == 0 else col_b
        fmt_checks[fmt] = col.checkbox(fmt.upper(), value=(fmt == "docx"))
    formats: list[str] = [f for f, checked in fmt_checks.items() if checked]

    st.divider()

    st.subheader("Transcript Options")
    use_timestamps    = st.checkbox("Include timestamps  [HH:MM:SS]")
    do_clean          = st.checkbox("Clean whitespace & punctuation")
    do_remove_fillers = st.checkbox("Remove filler words  (um, uh…)")
    do_paragraphs     = st.checkbox("Group into paragraphs")

    st.divider()

    st.subheader("Summary & Notes")
    st.caption("Local extractive summarization — no internet required.")
    do_summary = st.checkbox("Add summary")
    do_notes   = st.checkbox("Structured notes")
    template   = "default"
    if do_notes:
        template = st.selectbox("Notes template", list(VALID_TEMPLATES))


# ── Main area — input source ──────────────────────────────────────────────────

source_type = st.radio(
    "Input source",
    ["Local file", "YouTube URL"],
    horizontal=True,
)

uploaded_file = None
youtube_url   = None

if source_type == "Local file":
    uploaded_file = st.file_uploader(
        "Upload a video or audio file",
        type=SUPPORTED_EXTENSIONS,
        help="Processed locally — never sent to any server.",
    )
    if uploaded_file is not None:
        if st.session_state["_last_upload_name"] != uploaded_file.name:
            _cleanup_output_dir()
            st.session_state.results             = None
            st.session_state.error               = None
            st.session_state["_last_upload_name"] = uploaded_file.name

else:
    youtube_url = st.text_input(
        "YouTube URL",
        placeholder="https://youtube.com/watch?v=...  or  https://youtu.be/...",
    ).strip()
    if youtube_url:
        st.caption(
            "Only process content you have the rights or permission to transcribe."
        )
        if st.session_state["_last_youtube_url"] != youtube_url:
            _cleanup_output_dir()
            st.session_state.results              = None
            st.session_state.error                = None
            st.session_state["_last_youtube_url"]  = youtube_url

has_input = uploaded_file is not None or bool(youtube_url)
process_btn = st.button(
    "Process",
    type="primary",
    disabled=(not has_input or not formats),
    help="Select a file (or enter a URL) and at least one output format to continue."
    if (not has_input or not formats) else None,
)


# ── Processing ────────────────────────────────────────────────────────────────

if process_btn and has_input and formats:
    _cleanup_output_dir()
    st.session_state.results             = None
    st.session_state.error               = None
    st.session_state.edited_output_files = None
    st.session_state.regen_error         = None
    st.session_state["_editor_stem"]     = None   # force editor reinit

    dep_error: str | None = None
    try:
        check_ffmpeg()
        check_whisper()
        if "docx" in formats:
            check_python_docx()
        if youtube_url:
            check_yt_dlp()
    except TranscriberError as e:
        dep_error = str(e)

    if dep_error:
        st.session_state.error = dep_error
    else:
        effective_timestamps = use_timestamps or bool(_SUBTITLE_FMTS & set(formats))
        yt_tmpdir      = None
        audio_override = None
        stem_override  = None
        input_path     = None

        try:
            if youtube_url:
                # Download YouTube audio before launching the status box
                yt_tmpdir = tempfile.mkdtemp(prefix="transcriber_yt_")
                with st.status("Downloading YouTube audio…", expanded=True) as status:
                    status.update(label="Downloading YouTube audio…", state="running")
                    audio_override, video_title = download_audio(youtube_url, yt_tmpdir)
                    stem_override = sanitize_title(video_title)
                    status.update(
                        label=f"Downloaded: {video_title}",
                        state="complete",
                        expanded=False,
                    )
                source_path = youtube_url
            else:
                ext = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(uploaded_file.getbuffer())
                    input_path = tmp.name
                source_path = input_path

            with st.status("Processing…", expanded=True) as status:
                results = _run_pipeline(
                    input_path        = source_path,
                    language_code     = language_code,
                    wants_translation = wants_translation,
                    model_name        = model_name,
                    use_timestamps    = effective_timestamps,
                    do_clean          = do_clean,
                    do_remove_fillers = do_remove_fillers,
                    do_paragraphs     = do_paragraphs,
                    do_summary        = do_summary,
                    do_notes          = do_notes,
                    template          = template,
                    formats           = formats,
                    status            = status,
                    audio_override    = audio_override,
                    stem_override     = stem_override,
                )
                status.update(label="Done!", state="complete", expanded=False)

            st.session_state.results = results

        except TranscriberError as e:
            st.session_state.error = str(e)
        except Exception as e:
            st.session_state.error = f"Unexpected error: {type(e).__name__}: {e}"
        finally:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)
            if yt_tmpdir and os.path.isdir(yt_tmpdir):
                shutil.rmtree(yt_tmpdir, ignore_errors=True)


# ── Error display ─────────────────────────────────────────────────────────────

if st.session_state.error:
    st.error(st.session_state.error)


# ── Results ───────────────────────────────────────────────────────────────────

results = st.session_state.results
if not results:
    st.stop()

n = len(results["output_files"])
st.success(f"Transcription complete — {n} file{'s' if n != 1 else ''} ready to download.")


# ── Original exports ──────────────────────────────────────────────────────────

st.subheader("Original Exports")
_download_row(results["output_files"], key_prefix="orig")

has_subtitles = bool(_SUBTITLE_FMTS & set(results["output_files"]))
if has_subtitles:
    st.caption(
        "SRT / VTT files use original Whisper segment timing and are not affected by editing."
    )


# ── Transcript editor ─────────────────────────────────────────────────────────

st.subheader("Transcript Editor")
st.caption("Edit the transcript below before regenerating exports.")

# Initialise the editor text area once per result set
if st.session_state["_editor_stem"] != results["stem"]:
    st.session_state["editor_textarea"] = results["text"]
    st.session_state["_editor_stem"]    = results["stem"]

edited_text: str = st.text_area(
    label            = "transcript_editor",
    key              = "editor_textarea",
    height           = 380,
    label_visibility = "collapsed",
)

# ── Stats row ────────────────────────────────────────────────────────────────
word_count   = len(edited_text.split())
read_minutes = max(1, round(word_count / 250))
char_count   = len(edited_text)
st.caption(f"{word_count:,} words  ·  ~{read_minutes} min read  ·  {char_count:,} characters")

# ── Copy button ──────────────────────────────────────────────────────────────
_copy_button(edited_text)

# ── Search ───────────────────────────────────────────────────────────────────
search_query = st.text_input(
    "Search transcript",
    placeholder="Type a word or phrase…",
    label_visibility="visible",
)
_search_results(edited_text, search_query)


# ── Summary & Notes ───────────────────────────────────────────────────────────

notes = results["metadata"].get("notes")
if notes:
    with st.expander("Summary & Notes", expanded=False):
        for data_key, label, render_type in notes.get("layout", []):
            content = notes.get(data_key)
            if not content:
                continue
            st.markdown(f"**{label}**")
            if render_type == "text":
                st.write(content)
            elif render_type == "list":
                for item in content:
                    if item:
                        st.markdown(f"- {item}")
            elif render_type == "keyword_list":
                st.markdown(
                    ", ".join(content) if isinstance(content, list) else str(content)
                )
            st.markdown("")


# ── Regenerate from edited transcript ────────────────────────────────────────

st.subheader("Regenerate Exports from Edited Transcript")

regen_fmts = sorted(set(results["output_files"]) - _SUBTITLE_FMTS)
if not regen_fmts:
    st.info("No regeneratable formats in this run (only SRT / VTT were selected).")
else:
    if has_subtitles:
        st.caption(
            f"Regenerates: {', '.join(f.upper() for f in regen_fmts)}  ·  "
            "SRT / VTT are excluded (timing comes from the original Whisper output)."
        )

    regen_btn = st.button("Regenerate Exports from Edited Transcript", type="primary")

    if regen_btn:
        out_dir = st.session_state.output_dir
        if not out_dir or not os.path.isdir(out_dir):
            st.session_state.regen_error = (
                "Output directory is no longer available. "
                "Re-process the file to restore it."
            )
        else:
            try:
                st.session_state.edited_output_files = _save_edited_exports(
                    edited_text, results, out_dir
                )
                st.session_state.regen_error = None
            except TranscriberError as e:
                st.session_state.regen_error         = str(e)
                st.session_state.edited_output_files = None
            except Exception as e:
                st.session_state.regen_error         = f"Unexpected error: {type(e).__name__}: {e}"
                st.session_state.edited_output_files = None

    if st.session_state.regen_error:
        st.error(st.session_state.regen_error)

    if st.session_state.edited_output_files:
        st.success("Edited exports ready.")
        _download_row(st.session_state.edited_output_files, key_prefix="edited")
