import re


# ── Basic cleanup (always applied) ───────────────────────────────────────────

def clean_text(text):
    """Strip leading/trailing whitespace from raw Whisper output."""
    return text.strip()


# ── --clean ───────────────────────────────────────────────────────────────────

def clean_whitespace(text):
    """Light whitespace and punctuation-spacing cleanup.

    Transforms applied (in order):
      - Normalise CRLF / CR → LF
      - Collapse runs of spaces/tabs → single space
      - Collapse 3+ consecutive newlines → double newline
      - Remove spaces immediately before , . : ; ! ?
      - Insert a space between a sentence-ending punctuation and the next
        capital letter when none exists (e.g. "word.Next" → "word. Next").
        Only fires when the character before the punctuation is lowercase,
        so abbreviations like "U.S.A." are left alone.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +([,.:;!?])", r"\1", text)
    text = re.sub(r"([a-z][.!?])([A-Z])", r"\1 \2", text)
    return text.strip()


# ── --remove-fillers ──────────────────────────────────────────────────────────

def remove_fillers(text):
    """Remove common speech filler words conservatively.

    Rules per word:
      um / uh  — always removed; pure vocal disfluencies.
      you know — removed when used as a filler phrase (flanked by commas,
                 after sentence end, or trailing before end of sentence).
      like     — ONLY removed when flanked by commas on both sides
                 (", like," → ",").  "I like this" and "feel like" are
                 never touched.

    After each removal pass, double-commas, double-spaces, spaces before
    punctuation, and stray leading commas are cleaned up.
    """
    for filler in ("um", "uh"):
        p = rf"\b{filler}\b"
        # ", filler," → ","
        text = re.sub(rf",\s*{p}\s*,",             ",",  text, flags=re.IGNORECASE)
        # ", filler." → "."
        text = re.sub(rf",\s*{p}\s*\.",            ".",  text, flags=re.IGNORECASE)
        # ", filler" (no trailing comma) → ","
        text = re.sub(rf",\s*{p}(?=[\s,]|$)",      ",",  text, flags=re.IGNORECASE)
        # "filler," preceded by whitespace → ","
        text = re.sub(rf"(?<=\s){p}\s*,",          ",",  text, flags=re.IGNORECASE)
        # After sentence end: ". Filler, " → ". "
        text = re.sub(rf"(?<=[.!?])\s+{p},?\s*",  " ",  text, flags=re.IGNORECASE)
        # At very start of text: "Filler, …" → "…"
        text = re.sub(rf"^{p},?\s*",               "",   text, flags=re.IGNORECASE)
        # Standalone between / before words (catch-all)
        text = re.sub(rf"\s+{p}(?=[\s.,!?]|$)",   "",   text, flags=re.IGNORECASE)

    # "you know"
    text = re.sub(r",\s*\byou know\b\s*,",             ",", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*\byou know\b\s*\.",            ".", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*\byou know\b(?=[\s,]|$)",      "",  text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[.!?])\s+\byou know\b,?\s*",  " ", text, flags=re.IGNORECASE)

    # "like" — only when flanked by commas
    text = re.sub(r",\s*\blike\b\s*,", ",", text, flags=re.IGNORECASE)

    # Cleanup artifacts left by the removals above
    text = re.sub(r",\s*,",   ",",    text)   # double commas
    text = re.sub(r" {2,}",   " ",    text)   # double spaces
    text = re.sub(r" ([,.])", r"\1",  text)   # space before punctuation
    text = re.sub(r"^,\s*",   "",     text)   # stray leading comma

    return text.strip()


# ── --paragraphs ──────────────────────────────────────────────────────────────

def split_paragraphs(text, sentences_per_para=4):
    """Group sentences into readable paragraph blocks.

    Splits at sentence-ending punctuation followed by whitespace and a
    capital letter, then groups every `sentences_per_para` sentences into
    one paragraph.  Returns a single string with double-newline (\\n\\n)
    paragraph separators, which all exporters handle naturally.

    Falls back to returning the text unchanged when no split boundaries
    are found (e.g. a single sentence, or non-Latin script).
    """
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    if len(sentences) <= 1:
        return text.strip()
    paras = []
    for i in range(0, len(sentences), sentences_per_para):
        chunk = " ".join(s.strip() for s in sentences[i:i + sentences_per_para] if s.strip())
        if chunk:
            paras.append(chunk)
    return "\n\n".join(paras)


# ── Composite entry point ─────────────────────────────────────────────────────

def apply_cleaning(text, do_clean=False, do_remove_fillers=False, do_paragraphs=False):
    """Apply optional cleaning passes in the correct order.

    Always starts with the basic strip (clean_text).  Then applies each
    enabled pass:
      1. clean_whitespace   (--clean)
      2. remove_fillers     (--remove-fillers)
      3. split_paragraphs   (--paragraphs)

    Order matters: whitespace is normalised before filler removal so that
    regex patterns can rely on consistent spacing; paragraph splitting runs
    last so it sees the already-cleaned sentence boundaries.
    """
    text = clean_text(text)
    if do_clean:
        text = clean_whitespace(text)
    if do_remove_fillers:
        text = remove_fillers(text)
    if do_paragraphs:
        text = split_paragraphs(text)
    return text


# ── Timestamp helpers (used by exporter and docx_builder) ────────────────────

def seconds_to_hms(seconds):
    """Convert a float seconds value to a zero-padded HH:MM:SS string."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_segments(segments):
    """Convert Whisper segment dicts into '[HH:MM:SS - HH:MM:SS] text' strings."""
    lines = []
    for seg in segments:
        start = seconds_to_hms(seg["start"])
        end   = seconds_to_hms(seg["end"])
        text  = seg["text"].strip()
        lines.append(f"[{start} - {end}] {text}")
    return lines
