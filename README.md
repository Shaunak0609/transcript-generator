# TranscribeFlow

**Local AI transcription and translation for video and audio — no cloud required.**

TranscribeFlow turns video and audio files into polished documents using OpenAI Whisper,
running entirely on your machine. Export to Word, Markdown, plain text, JSON, SRT, or VTT.
Process a single file, a YouTube URL, or an entire folder in one command.

---

## Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [CLI Usage](#cli-usage)
- [Streamlit UI](#streamlit-ui)
- [Examples](#examples)
- [Supported Formats](#supported-formats)
- [Output Examples](#output-examples)
- [Configuration](#configuration)
- [Privacy](#privacy)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## Features

**Transcription & Translation**
- Transcribe speech in 90+ languages using OpenAI Whisper
- Translate any language directly to English in one pass
- Five Whisper model sizes — trade speed for accuracy
- Per-segment timestamps in every output format
- Auto-detect language or specify it explicitly

**Input Sources**
- Local video files — MP4, MOV, MKV, AVI, WebM, M4V
- Local audio files — MP3, WAV, M4A, FLAC, OGG
- YouTube URLs — audio downloaded via yt-dlp, no video stored *(optional)*

**Export**
- Word document (DOCX) with cover page and metadata table
- Plain text, Markdown, JSON, SRT subtitles, WebVTT subtitles
- Export multiple formats in one run

**Transcript Cleaning**
- Collapse repeated spaces and fix punctuation spacing
- Remove filler words — *um*, *uh*, *you know*, filler *like*
- Group sentences into readable paragraphs

**Local Summarization** *(no API required)*
- Extractive summary and key terms prepended to any output
- Five structured note templates: default, lecture, meeting, interview, podcast

**Batch Processing**
- Transcribe an entire folder with one command
- Recursive directory scan, per-file error reporting, summary at the end

**Browser UI** *(Streamlit)*
- Full-featured web interface — no command line needed
- Editable transcript with word count, reading time, and search
- One-click download for all output formats
- Regenerate exports from an edited transcript

---

## Quick Start

```bash
# 1 — Install system dependencies (macOS)
brew install ffmpeg

# 2 — Create environment and install
python3.12 -m venv whisper_env
source whisper_env/bin/activate
pip install -e .

# 3 — Transcribe your first file (command line)
transcribeflow transcribe lecture.mp4

# 4 — ...or launch the browser UI instead
streamlit run streamlit_app.py
```

Command-line output lands in `outputs/lecture_transcript_auto.docx`.
The browser UI opens at `http://localhost:8501` — see [Streamlit UI](#streamlit-ui) below.

> **Apple Silicon (M1/M2/M3/M4) note:** if `pip install -e .` fails trying to
> build `llvmlite` from source (a Whisper dependency) — usually a `cmake`/`LLVM`
> error — your virtual environment was created with an x86_64 (Intel/Rosetta)
> Python instead of a native arm64 one. Fix it by recreating the venv with an
> arm64 Homebrew Python:
> ```bash
> brew install python@3.12          # installs the arm64 build under /opt/homebrew
> rm -rf whisper_env
> /opt/homebrew/bin/python3.12 -m venv whisper_env
> source whisper_env/bin/activate
> pip install -e .
> ```
> With the correct architecture, `pip install -e .` downloads a prebuilt
> `llvmlite` wheel directly — no `cmake` or `llvm` install needed.

---

## Installation

### Prerequisites

macOS with [Homebrew](https://brew.sh). Python 3.10 or later.

### Step 1 — Install system tools

```bash
brew install ffmpeg
```

| Tool | Purpose |
|------|---------|
| `ffmpeg` | Audio extraction from video files and YouTube downloads |

### Step 2 — Create a Python virtual environment

```bash
python3.12 -m venv whisper_env
source whisper_env/bin/activate
```

> Always activate the environment before running TranscribeFlow:
> `source whisper_env/bin/activate`
>
> **Apple Silicon (M1/M2/M3/M4):** make sure `python3.12` resolves to a native
> arm64 Python, not an x86_64 (Intel/Rosetta) one — otherwise `pip install -e .`
> in the next step will fail trying to build `llvmlite` from source. If you hit
> that, recreate the venv explicitly with the arm64 Homebrew Python:
> ```bash
> brew install python@3.12   # installs the arm64 build under /opt/homebrew
> rm -rf whisper_env
> /opt/homebrew/bin/python3.12 -m venv whisper_env
> source whisper_env/bin/activate
> ```

### Step 3 — Install TranscribeFlow

```bash
pip install -e .
```

This reads `pyproject.toml`, installs all dependencies, and registers the
`transcribeflow` command in your active environment.

### First run note

The first time you run a transcription, Whisper downloads the model weights:

| Model | Download size |
|-------|--------------|
| tiny  | ~75 MB |
| base  | ~150 MB |
| small | ~480 MB |
| medium | ~1.5 GB |
| large | ~3 GB |

Models are cached in `~/.cache/whisper` and reused on subsequent runs.

---

## CLI Usage

Both `transcribeflow` (installed command) and `python3 transcribe_video.py`
accept the same subcommands and flags.

### Commands

```
transcribeflow transcribe <file-or-url>   Transcribe or translate a single file
transcribeflow batch <directory>          Process all media files in a directory
```

### `transcribe` options

| Flag | Default | Description |
|------|---------|-------------|
| `--language CODE` | auto | Source language code — `en`, `ja`, `es`, `fr`, `de`, `zh`, … |
| `--translate` | off | Translate to English instead of transcribing in source language |
| `--model MODEL` | `base` | Whisper model: `tiny` `base` `small` `medium` `large` |
| `--format FORMAT…` | `docx` | One or more output formats — see [Supported Formats](#supported-formats) |
| `--output-dir DIR` | `outputs/` | Directory for output files (created if it doesn't exist) |
| `--timestamps` | off | Include `[HH:MM:SS – HH:MM:SS]` labels per segment |
| `--clean` | off | Fix whitespace and punctuation spacing |
| `--remove-fillers` | off | Remove *um*, *uh*, *you know*, filler *like* |
| `--paragraphs` | off | Group sentences into paragraph blocks |
| `--summary` | off | Prepend extractive summary and key terms |
| `--notes` | off | Prepend structured notes (use with `--template`) |
| `--template NAME` | `default` | Notes template: `default` `lecture` `meeting` `interview` `podcast` |
| `--save-temp` | off | Keep the extracted/downloaded audio file after processing |
| `--quiet` / `-q` | off | Suppress progress output; show only errors |
| `--verbose` | off | Show timing, word counts, and output paths |
| `--debug` | off | Print full Python traceback on error |

### `batch` options

All `transcribe` options apply, plus:

| Flag | Description |
|------|-------------|
| `--recursive` / `-r` | Scan subdirectories for media files |
| `--fail-fast` | Stop immediately if any file fails |

### Model reference

| Model | Speed | Quality | RAM needed |
|-------|-------|---------|-----------|
| `tiny` | fastest | basic | ~1 GB |
| `base` *(default)* | fast | good | ~1 GB |
| `small` | moderate | better | ~2 GB |
| `medium` | slow | high | ~5 GB |
| `large` | slowest | highest | ~10 GB |

---

## Streamlit UI

A browser-based interface that exposes every feature — no command line needed.

```bash
streamlit run streamlit_app.py
```

Open the URL shown in the terminal (default: `http://localhost:8501`).

**What you can do:**
- Upload a local file or paste a YouTube URL
- Choose task, language, model, formats, and all processing options in the sidebar
- Watch live status updates as each pipeline step runs
- Edit the transcript in a full-screen text area before exporting
- See word count, estimated reading time, and search within the transcript
- Copy the transcript to clipboard with one click
- Download all output files individually
- Regenerate DOCX / TXT / MD / JSON exports from your edited transcript

> SRT and VTT files are always based on the original Whisper timing and are
> not affected by transcript edits.

---

## Examples

### Transcribe a video

```bash
transcribeflow transcribe lecture.mp4
# → outputs/lecture_transcript_auto.docx

transcribeflow transcribe lecture.mp4 --language en --model small --format docx txt md
# → outputs/lecture_transcript_en.docx
# → outputs/lecture_transcript_en.txt
# → outputs/lecture_transcript_en.md
```

### Translate Japanese audio to English

```bash
transcribeflow transcribe interview.mp4 --language ja --translate --format docx
# → outputs/interview_translated_en.docx

# With timestamps and subtitles
transcribeflow transcribe interview.mp4 --language ja --translate \
  --format docx srt vtt --timestamps
```

### Export DOCX and subtitles together

```bash
transcribeflow transcribe talk.mp4 --format docx srt vtt
# → outputs/talk_transcript_auto.docx
# → outputs/talk_transcript_auto.srt   (SRT subtitles)
# → outputs/talk_transcript_auto.vtt   (WebVTT subtitles)
```

SRT and VTT generation is automatic — `--timestamps` is not required.

### Batch process a folder

```bash
# Process everything in ./recordings
transcribeflow batch ./recordings --format docx --model small

# Recursive scan, multiple formats, structured notes
transcribeflow batch ./lectures --recursive \
  --model small \
  --notes --template lecture \
  --format docx md \
  --output-dir ./transcripts

# Translate a folder of Japanese recordings
transcribeflow batch ./japanese_files --language ja --translate --format docx
```

Progress is printed per file. A summary is shown at the end:

```
  [1/4] lecture_01.mp4  OK
  [2/4] lecture_02.mp4  OK
  [3/4] corrupted.mp4   FAILED
  [4/4] lecture_04.mp4  OK

──────────────────────────────────────────────────
Batch complete: 3/4 succeeded
Failed:
  corrupted.mp4: FFmpeg failed to extract audio
```

### Generate lecture notes

```bash
transcribeflow transcribe class.mp4 \
  --model small \
  --language en \
  --notes --template lecture \
  --clean --remove-fillers \
  --format docx md \
  --output-dir ./notes
```

The lecture template produces: **Summary**, **Key Concepts**, **Study Notes**,
**Possible Study Questions**, and **Key Terms** — all prepended to the transcript.

### YouTube URL

```bash
# Transcribe a public YouTube video
transcribeflow transcribe "https://youtube.com/watch?v=VIDEO_ID" --format docx md

# Translate Japanese YouTube video to English
transcribeflow transcribe "https://youtu.be/VIDEO_ID" --language ja --translate --format docx

# Full pipeline
transcribeflow transcribe "https://youtube.com/watch?v=VIDEO_ID" \
  --model small --notes --template lecture \
  --format docx txt md json \
  --output-dir ./results
```

> Only process content you have the rights or explicit permission to transcribe.
> yt-dlp must be installed: `pip install yt-dlp`

---

## Supported Formats

### Input

| Format | Extension |
|--------|-----------|
| Video | `.mp4` `.mov` `.mkv` `.avi` `.webm` `.m4v` |
| Audio | `.mp3` `.wav` `.m4a` `.flac` `.ogg` |
| YouTube | `https://youtube.com/…` `https://youtu.be/…` *(requires yt-dlp)* |

### Output

| Format | Extension | Description |
|--------|-----------|-------------|
| Word | `.docx` | Professional document with cover page, metadata table, Calibri typography |
| Plain text | `.txt` | Clean plain text, one segment per line when timestamps are on |
| Markdown | `.md` | Metadata header, notes sections, formatted transcript body |
| JSON | `.json` | Structured data with metadata, notes, full text, and segment array |
| SRT | `.srt` | Standard subtitle file — compatible with VLC, QuickTime, most players |
| VTT | `.vtt` | WebVTT subtitle file — for HTML5 `<video>` and streaming players |

---

## Output Examples

### Filename patterns

| Scenario | Example filename |
|----------|-----------------|
| Transcription, language specified | `lecture_transcript_en.docx` |
| Transcription, language auto-detected | `lecture_transcript_auto.docx` |
| Translation to English | `lecture_translated_en.docx` |
| YouTube video | `My_Video_Title_transcript_auto.docx` |

The same stem is used across all formats in a run:
`lecture_transcript_en.docx`, `lecture_transcript_en.srt`, `lecture_transcript_en.json`, …

### SRT subtitle format

```
1
00:00:00,000 --> 00:00:04,520
Welcome to today's lecture on machine learning.

2
00:00:04,520 --> 00:00:09,100
We'll start by reviewing the basics of gradient descent.
```

### VTT subtitle format

```
WEBVTT

00:00:00.000 --> 00:00:04.520
Welcome to today's lecture on machine learning.

00:00:04.520 --> 00:00:09.100
We'll start by reviewing the basics of gradient descent.
```

### Timestamped text output

```
[00:00:00 – 00:00:04] Welcome to today's lecture on machine learning.
[00:00:04 – 00:00:09] We'll start by reviewing the basics of gradient descent.
```

### Log file

Every run writes a timestamped log to `logs/`:

```
logs/transcriber_2026-05-22_14-30-00.log
```

The log captures input file, model, task, formats, timing, and errors.
Transcript text is never written to the log.

---

## Configuration

TranscribeFlow has no configuration file — all settings are passed as CLI flags
or chosen in the Streamlit sidebar. Defaults are defined in `app/config.py`:

| Setting | Default | Change with |
|---------|---------|-------------|
| Whisper model | `base` | `--model` |
| Output directory | `outputs/` | `--output-dir` |
| Output format | `docx` | `--format` |
| Language | auto-detect | `--language` |

To change the default model or output directory permanently, edit `app/config.py`:

```python
# app/config.py
DEFAULT_MODEL      = "small"       # change default model
DEFAULT_OUTPUT_DIR = "transcripts" # change default output folder
```

---

## Privacy

**TranscribeFlow processes everything locally on your machine.**

- Audio and video files are never sent to any server.
- Whisper runs as a local Python process — no internet connection is needed after
  the model weights are downloaded once.
- The Streamlit UI runs on `localhost` — your files are not uploaded anywhere.
- YouTube downloads fetch only the audio stream via yt-dlp, which contacts
  YouTube's servers directly from your machine (no proxy or third party).
- Log files in `logs/` contain file paths and metadata only — transcript text
  is never logged.

---

## Troubleshooting

### `FFmpeg was not found`

```bash
brew install ffmpeg
```

Verify it is on your PATH:

```bash
ffmpeg -version
```

### `openai-whisper is not installed`

```bash
source whisper_env/bin/activate
pip install openai-whisper
```

### `yt-dlp is not installed`

```bash
pip install yt-dlp
```

### Model download fails or is slow

Whisper downloads models from Hugging Face on first use. If it hangs, check your
internet connection and try again — partial downloads are resumable.

### Empty transcript

- The audio may be silent, too short, or contain non-speech sounds only.
- Try a larger model: `--model small` or `--model medium`.
- If the file has heavy background noise, accuracy will be reduced.

### `pip install -e .` fails building `llvmlite` (Apple Silicon)

This means your virtual environment was created with an x86_64 (Intel/Rosetta)
Python instead of a native arm64 one:

```bash
brew install python@3.12
rm -rf whisper_env
/opt/homebrew/bin/python3.12 -m venv whisper_env
source whisper_env/bin/activate
pip install -e .
```

With the correct architecture, `llvmlite` installs from a prebuilt wheel —
no `cmake` or `llvm` needed.

### Wrong language detected

Pass the language code explicitly:

```bash
transcribeflow transcribe video.mp4 --language ja
```

### Getting more detail on any error

```bash
transcribeflow transcribe video.mp4 --debug
```

This prints the full Python traceback and any FFmpeg stderr output.

---

## Project Structure

```
transcription_project/
├── app/
│   ├── __init__.py
│   ├── audio.py          FFmpeg audio extraction
│   ├── cli.py            Argument parsing, subcommands, pipeline orchestration
│   ├── config.py         Defaults and constants
│   ├── dependencies.py   Pre-flight dependency checks (FFmpeg, Whisper, yt-dlp)
│   ├── docx_builder.py   Word document assembly and styling
│   ├── errors.py         Custom exception hierarchy
│   ├── exporter.py       Save functions for all output formats
│   ├── formatter.py      Transcript cleaning utilities
│   ├── logger.py         Logging setup — file + console handlers
│   ├── notes.py          Template-based note assembly
│   ├── subtitles.py      SRT and VTT generation
│   ├── summarizer.py     Extractive summarization engine
│   ├── transcriber.py    Whisper model loading and inference
│   ├── utils.py          Path building and validation helpers
│   └── youtube.py        YouTube audio download via yt-dlp
├── logs/                 Timestamped log files (auto-created)
├── outputs/              Default output directory (auto-created)
├── tests/
├── pyproject.toml        Package metadata, dependencies, and `transcribeflow` entry point
├── streamlit_app.py      Browser UI
└── transcribe_video.py   Legacy entry point (calls app.cli:main)
```

---
