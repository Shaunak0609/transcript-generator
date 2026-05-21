import json
import os
from datetime import datetime

from app.errors import ConfigError, ExportError
from app.formatter import format_segments, seconds_to_hms
from app.logger import get_logger


# ── Notes rendering helpers ───────────────────────────────────────────────────

def _notes_as_txt(notes):
    """Render notes dict as plain-text sections with === headers ===."""
    if not notes:
        return ""
    lines = []
    for data_key, label, render_type in notes.get("layout", []):
        content = notes.get(data_key)
        if not content:
            continue
        lines.append(f"=== {label.upper()} ===\n")
        if render_type == "text":
            lines.append(f"{content}\n")
        elif render_type == "list":
            for item in content:
                if item:
                    lines.append(f"  • {item}")
        elif render_type == "keyword_list":
            if isinstance(content, list):
                lines.append("  " + ",  ".join(content))
            else:
                lines.append(f"  {content}")
        lines.append("")  # blank line after each section
    lines.append("=" * 72)
    lines.append("")
    return "\n".join(lines)


def _notes_as_md(notes):
    """Render notes dict as Markdown sections with ## headings."""
    if not notes:
        return ""
    lines = []
    for data_key, label, render_type in notes.get("layout", []):
        content = notes.get(data_key)
        if not content:
            continue
        lines.append(f"## {label}\n")
        if render_type == "text":
            lines.append(f"{content}\n")
        elif render_type == "list":
            for item in content:
                if item:
                    lines.append(f"- {item}")
            lines.append("")
        elif render_type == "keyword_list":
            if isinstance(content, list):
                lines.append(", ".join(content))
            else:
                lines.append(str(content))
            lines.append("")
    lines.append("---\n")
    return "\n".join(lines)


# ── DOCX ─────────────────────────────────────────────────────────────────────

def save_to_word(text, output_path, segments=None, metadata=None):
    """Save transcription to a professionally formatted Word (.docx) document."""
    log = get_logger()
    log.info("--- SAVING: Word Document ---")
    from app.docx_builder import build_docx
    build_docx(text, output_path, segments, metadata)
    log.info(f"Status: Saved to {os.path.basename(output_path)}")
    log.debug(f"Output path: {output_path}")


# ── TXT ──────────────────────────────────────────────────────────────────────

def save_to_txt(text, output_path, segments=None, metadata=None):
    """Save transcription as plain text.

    With segments: one '[HH:MM:SS - HH:MM:SS] text' line per segment.
    Without: the full transcript as-is.
    Notes/summary sections are prepended when present in metadata.
    """
    log = get_logger()
    log.info("--- SAVING: Text File ---")
    try:
        notes    = (metadata or {}).get("notes")
        body     = "\n".join(format_segments(segments)) if segments else text
        header   = _notes_as_txt(notes)
        content  = header + body if header else body
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        log.info(f"Status: Saved to {os.path.basename(output_path)}")
        log.debug(f"Output path: {output_path}")
    except OSError as e:
        raise ExportError(
            f"Could not write text file: {os.path.basename(output_path)}\n"
            f"Reason: {e.strerror}",
            details=str(e),
        ) from e


# ── Markdown ─────────────────────────────────────────────────────────────────

def save_to_md(text, output_path, segments=None, metadata=None):
    """Save transcription as Markdown.

    Structure when notes are present:
      # Title
      metadata block
      ---
      notes sections (summary, key points, etc.)
      ---
      ## Transcript
      body
    """
    log = get_logger()
    log.info("--- SAVING: Markdown ---")
    try:
        notes = (metadata or {}).get("notes")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Whisper AI Transcription Result\n\n")

            if metadata:
                mode = "Translation to English" if metadata.get("translated") else "Transcription"
                f.write(f"**Source:** {metadata.get('source_file', '')}  \n")
                f.write(f"**Language:** {metadata.get('language', 'auto')}  \n")
                f.write(f"**Model:** {metadata.get('model', 'base')}  \n")
                f.write(f"**Type:** {mode}  \n")
                f.write("\n---\n\n")

            if notes:
                f.write(_notes_as_md(notes))
                f.write("## Transcript\n\n")

            if segments:
                for line in format_segments(segments):
                    f.write(f"{line}\n\n")
            else:
                f.write(text)

        log.info(f"Status: Saved to {os.path.basename(output_path)}")
        log.debug(f"Output path: {output_path}")
    except OSError as e:
        raise ExportError(
            f"Could not write Markdown file: {os.path.basename(output_path)}\n"
            f"Reason: {e.strerror}",
            details=str(e),
        ) from e


# ── JSON ─────────────────────────────────────────────────────────────────────

def save_to_json(text, output_path, segments=None, metadata=None):
    """Save transcription as structured JSON.

    Schema:
      {
        "metadata": { source_file, language, model, translated,
                      has_timestamps, exported_at },
        "text":     "<full plain transcript>",
        "segments": null  |  [ { id, start, end, start_hms, end_hms, text }, ... ]
      }
    """
    log = get_logger()
    log.info("--- SAVING: JSON ---")
    try:
        json_segments = None
        if segments:
            json_segments = [
                {
                    "id": seg.get("id", i),
                    "start": round(seg["start"], 3),
                    "end": round(seg["end"], 3),
                    "start_hms": seconds_to_hms(seg["start"]),
                    "end_hms": seconds_to_hms(seg["end"]),
                    "text": seg["text"].strip(),
                }
                for i, seg in enumerate(segments)
            ]

        raw_notes = (metadata or {}).get("notes")
        # Strip the "layout" key — it's an internal rendering hint, not output data
        export_notes = None
        if raw_notes:
            export_notes = {k: v for k, v in raw_notes.items() if k != "layout"}

        # Build metadata without the "notes" key (goes in its own top-level field)
        clean_meta = {k: v for k, v in (metadata or {}).items() if k != "notes"}

        payload = {
            "metadata": {
                **clean_meta,
                "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            },
            "notes":    export_notes,
            "text":     text,
            "segments": json_segments,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info(f"Status: Saved to {os.path.basename(output_path)}")
        log.debug(f"Output path: {output_path}")
    except OSError as e:
        raise ExportError(
            f"Could not write JSON file: {os.path.basename(output_path)}\n"
            f"Reason: {e.strerror}",
            details=str(e),
        ) from e


# ── SRT ──────────────────────────────────────────────────────────────────────

def save_to_srt(text, output_path, segments=None, metadata=None):
    """Save transcription as an SRT subtitle file.

    Requires Whisper segment timing data. If segments are absent the file is
    not written and the user is shown a friendly warning.
    """
    log = get_logger()
    log.info("--- SAVING: SRT Subtitles ---")
    if not segments:
        log.warning("SRT export requires segment timing data — skipping this format.")
        return
    try:
        from app.subtitles import generate_srt
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(generate_srt(segments))
        log.info(f"Status: Saved to {os.path.basename(output_path)}")
        log.debug(f"Output path: {output_path}")
    except OSError as e:
        raise ExportError(
            f"Could not write SRT file: {os.path.basename(output_path)}\n"
            f"Reason: {e.strerror}",
            details=str(e),
        ) from e


# ── VTT ──────────────────────────────────────────────────────────────────────

def save_to_vtt(text, output_path, segments=None, metadata=None):
    """Save transcription as a WebVTT subtitle file.

    Requires Whisper segment timing data. If segments are absent the file is
    not written and the user is shown a friendly warning.
    """
    log = get_logger()
    log.info("--- SAVING: VTT Subtitles ---")
    if not segments:
        log.warning("VTT export requires segment timing data — skipping this format.")
        return
    try:
        from app.subtitles import generate_vtt
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(generate_vtt(segments))
        log.info(f"Status: Saved to {os.path.basename(output_path)}")
        log.debug(f"Output path: {output_path}")
    except OSError as e:
        raise ExportError(
            f"Could not write VTT file: {os.path.basename(output_path)}\n"
            f"Reason: {e.strerror}",
            details=str(e),
        ) from e


# ── Dispatcher ────────────────────────────────────────────────────────────────

def save(text, output_path, fmt, segments=None, metadata=None):
    """Route to the correct save function based on format string."""
    dispatch = {
        "docx": save_to_word,
        "txt":  save_to_txt,
        "md":   save_to_md,
        "json": save_to_json,
        "srt":  save_to_srt,
        "vtt":  save_to_vtt,
    }
    if fmt not in dispatch:
        raise ConfigError(
            f"Unsupported output format: '{fmt}'\n"
            f"Valid choices: {', '.join(dispatch)}"
        )
    dispatch[fmt](text, output_path, segments, metadata)
