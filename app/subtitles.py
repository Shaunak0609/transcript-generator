"""
SRT and WebVTT subtitle generation from Whisper segment data.

Both formats require per-segment start/end times, which Whisper always
provides in result["segments"]. The cli auto-enables segment collection
whenever srt or vtt is in the requested output formats.
"""


def _srt_ts(seconds):
    """Convert a float seconds value to SRT timestamp format: HH:MM:SS,mmm"""
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _vtt_ts(seconds):
    """Convert a float seconds value to WebVTT timestamp format: HH:MM:SS.mmm"""
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def generate_srt(segments):
    """Return a complete SRT string from a Whisper segment list.

    Format per cue:
      1
      00:00:00,000 --> 00:00:04,500
      Subtitle text
    """
    if not segments:
        return ""
    blocks = []
    counter = 1
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        start = _srt_ts(seg["start"])
        end   = _srt_ts(seg["end"])
        blocks.append(f"{counter}\n{start} --> {end}\n{text}")
        counter += 1
    return "\n\n".join(blocks) + "\n"


def generate_vtt(segments):
    """Return a complete WebVTT string from a Whisper segment list.

    Starts with the mandatory WEBVTT header, then one cue per segment:
      WEBVTT

      00:00:00.000 --> 00:00:04.500
      Subtitle text
    """
    if not segments:
        return "WEBVTT\n"
    blocks = ["WEBVTT"]
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        start = _vtt_ts(seg["start"])
        end   = _vtt_ts(seg["end"])
        blocks.append(f"{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + "\n"
