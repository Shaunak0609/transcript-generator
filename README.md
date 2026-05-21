# AI Video Transcriber & Translator

A Python CLI that transcribes and translates video files into professional documents, powered by OpenAI Whisper. Supports Word, plain text, Markdown, JSON, SRT, and VTT output with optional timestamps, model selection, transcript cleaning, subtitle export, local summarization, and structured notes.

---

## Features

- **Multi-format export** — DOCX (with cover page), TXT, Markdown, JSON, SRT, VTT
- **90+ languages** — transcription in any language Whisper supports
- **Translation** — translate foreign-language audio directly to English
- **Timestamps** — per-segment `[HH:MM:SS – HH:MM:SS]` time ranges
- **Subtitle export** — SRT and VTT files from Whisper segment timing
- **Transcript cleaning** — remove filler words, fix whitespace, split paragraphs
- **Local summarization** — extractive summary and structured notes, no API required
- **Notes templates** — lecture, meeting, interview, podcast, default
- **Model selection** — tiny / base / small / medium / large
- **Professional DOCX** — cover page with metadata table, Calibri typography
- **Logging** — timestamped log files in `logs/`, quiet/verbose/debug modes
- **Friendly errors** — clear messages with fix hints; `--debug` for full tracebacks

---

## Project Structure

```
transcription_project/
├── app/
│   ├── audio.py          FFmpeg audio extraction
│   ├── cli.py            Argument parsing and pipeline orchestration
│   ├── config.py         Constants and defaults
│   ├── dependencies.py   Pre-flight dependency checks
│   ├── docx_builder.py   DOCX document assembly and styling
│   ├── errors.py         Custom exception hierarchy
│   ├── exporter.py       Save functions for all output formats
│   ├── formatter.py      Text cleaning and formatting utilities
│   ├── logger.py         Logging setup (file + console handlers)
│   ├── notes.py          Template-based note assembly
│   ├── subtitles.py      SRT and VTT generation
│   ├── summarizer.py     Extractive summarization engine
│   ├── transcriber.py    Whisper model loading and inference
│   └── utils.py          Path building, validation helpers
├── logs/                 Timestamped log files (auto-created)
├── outputs/              Default output directory
├── tests/
├── requirements.txt
└── transcribe_video.py   Entry point
```

---

## Mac Setup (One-Time)

```bash
brew install ffmpeg cmake llvm@15
```

---

## Getting Started

```bash
# Create virtual environment
python3.12 -m venv whisper_env
source whisper_env/bin/activate

# Install dependencies
export LLVM_CONFIG=$(brew --prefix llvm@15)/bin/llvm-config
pip install -r requirements.txt
```

Always activate the environment before running:

```bash
source whisper_env/bin/activate
```

---

## Usage

### Basic transcription

```bash
# Auto-detect language
python3 transcribe_video.py transcribe video.mp4

# Specify source language
python3 transcribe_video.py transcribe video.mp4 --language en
python3 transcribe_video.py transcribe video.mp4 --language ja
```

### Translation to English

```bash
python3 transcribe_video.py transcribe video.mp4 --language ja --translate
```

### Model selection

| Model  | Speed      | Accuracy | RAM    |
|--------|------------|----------|--------|
| tiny   | fastest    | lowest   | ~1 GB  |
| base   | fast *(default)* | good | ~1 GB |
| small  | moderate   | better   | ~2 GB  |
| medium | slow       | high     | ~5 GB  |
| large  | slowest    | highest  | ~10 GB |

```bash
python3 transcribe_video.py transcribe video.mp4 --model small
```

### Output formats

```bash
# Default: Word document
python3 transcribe_video.py transcribe video.mp4 --format docx

# Multiple formats at once
python3 transcribe_video.py transcribe video.mp4 --format docx txt md json

# Subtitle formats
python3 transcribe_video.py transcribe video.mp4 --format srt
python3 transcribe_video.py transcribe video.mp4 --format vtt
python3 transcribe_video.py transcribe video.mp4 --format docx srt vtt
```

### Subtitles (SRT / VTT)

SRT and VTT are generated from Whisper's per-segment timing. Segment collection is automatic — `--timestamps` is not required.

**SRT** — compatible with most video players:
```
1
00:00:00,000 --> 00:00:04,500
Hello, world.
```

**VTT** — WebVTT for HTML5 `<track>` elements:
```
WEBVTT

00:00:00.000 --> 00:00:04.500
Hello, world.
```

### Timestamps

```bash
python3 transcribe_video.py transcribe video.mp4 --timestamps
python3 transcribe_video.py transcribe video.mp4 --language ja --translate --timestamps
```

Timestamps appear as `[HH:MM:SS – HH:MM:SS]` labels. In DOCX each segment gets its own paragraph; in TXT one line per segment; in Markdown one block per segment; in JSON a structured `segments` array.

### Transcript cleaning

Three optional flags, combinable freely:

```bash
python3 transcribe_video.py transcribe video.mp4 --clean
python3 transcribe_video.py transcribe video.mp4 --remove-fillers
python3 transcribe_video.py transcribe video.mp4 --paragraphs

# All three at once
python3 transcribe_video.py transcribe video.mp4 --clean --remove-fillers --paragraphs
```

#### `--clean` — whitespace and punctuation

Collapses repeated spaces, normalises line endings, removes spaces before punctuation, inserts missing space after sentence-ending punctuation.

```
Before:  "And  I was thinking .  It seemed , you know ,  fine."
After:   "And I was thinking. It seemed, you know, fine."
```

#### `--remove-fillers` — filler word removal

Removes `um`, `uh`, `you know`, and filler `like` (only when flanked by commas).

```
Before:  "And, um, I was thinking, uh, that we should, like, go."
After:   "And, I was thinking, that we should, go."
```

```
Before:  "I like this idea. It was, like, really good."
After:   "I like this idea. It was, really good."
         ↑ "like" in "I like" preserved; filler ", like," removed
```

#### `--paragraphs` — readable paragraph breaks

Groups sentences into blocks (~4 each), inserting double-newline separators. Works best after `--clean`.

### Summary and notes (local, no API)

Extractive summarization using word-frequency scoring — no internet or paid API required.

```bash
# Short summary + key terms prepended to output
python3 transcribe_video.py transcribe video.mp4 --summary

# Structured notes using a template
python3 transcribe_video.py transcribe video.mp4 --notes --template lecture
python3 transcribe_video.py transcribe video.mp4 --notes --template meeting
python3 transcribe_video.py transcribe video.mp4 --notes --template interview
python3 transcribe_video.py transcribe video.mp4 --notes --template podcast
```

#### Template sections

| Template | Sections |
|----------|----------|
| `default` | Summary, Key Points, Key Terms |
| `lecture` | Summary, Key Concepts, Study Notes, Possible Study Questions, Key Terms |
| `meeting` | Summary, Key Points, Possible Action Items, Decisions Mentioned, Key Terms |
| `interview` | Summary, Themes, Notable Moments, Key Terms |
| `podcast` | Episode Summary, Highlights, Topics Discussed, Key Terms |

Notes and summary sections appear **before** the transcript in every output format.

#### Limitations of local summarization

- **Extractive only** — selects existing sentences, never generates new text
- **English stopwords** — scoring quality degrades for non-English transcripts
- **No semantic understanding** — relies on term frequency, not meaning
- **Heuristic action/decision detection** — pattern-based, expect false positives
- **Study questions are keyword prompts** — not intelligently generated

### Output directory

```bash
python3 transcribe_video.py transcribe video.mp4 --output-dir ./results
```

Default output directory: `outputs/`

### Output filenames

| Scenario | Example filename |
|----------|-----------------|
| Transcription, language specified | `video_transcript_en.docx` |
| Transcription, auto-detect | `video_transcript_auto.docx` |
| Translation to English | `video_translated_en.docx` |

The same stem is used for all formats: `.docx`, `.txt`, `.md`, `.json`, `.srt`, `.vtt`.

### Verbosity flags

```bash
# Suppress all progress output (silent run, errors still shown)
python3 transcribe_video.py transcribe video.mp4 --quiet

# Show extra detail: timing, word counts, output paths
python3 transcribe_video.py transcribe video.mp4 --verbose

# Show full exception details and stack trace on error
python3 transcribe_video.py transcribe video.mp4 --debug
```

All verbosity levels write the full DEBUG log to `logs/transcriber_YYYY-MM-DD_HH-MM-SS.log` regardless of what is shown in the terminal.

### Full example

```bash
python3 transcribe_video.py transcribe lecture.mp4 \
  --language en \
  --model small \
  --timestamps \
  --clean \
  --remove-fillers \
  --notes --template lecture \
  --format docx txt md json srt \
  --output-dir ./results \
  --verbose
```

### Old-style commands (still supported)

```bash
python3 transcribe_video.py "path/to/video.mp4" en
python3 transcribe_video.py "path/to/video.mp4" ja translate
```

---

## Error handling

All user-facing errors display a friendly message with a fix hint:

```
Error: FFmpeg was not found.
Install it on macOS with:
  brew install ffmpeg
```

```
Error: File not found: video.mp4
Check the path and try again.
```

```
Error: Unsupported file type: '.txt'
Supported video formats: .avi, .m4v, .mkv, .mov, .mp4, .webm
Supported audio formats: .flac, .m4a, .mp3, .ogg, .wav
```

```
Error: Invalid language code: 'EN123'
Use a 2- or 3-letter ISO 639-1 code, e.g. en ja fr de zh.
```

Add `--debug` to any command to see the full Python traceback and extra technical detail (e.g. FFmpeg stderr):

```bash
python3 transcribe_video.py transcribe video.mp4 --debug
```

---

## Logging

Every run creates a timestamped log file:

```
logs/transcriber_YYYY-MM-DD_HH-MM-SS.log
```

The log file always captures the full DEBUG stream (input file, model, task, formats, timing, errors) regardless of terminal verbosity flags. Transcript text is never written to the log.

---

## Notes

- The first run downloads the Whisper model (~150 MB for `base`).
- Accuracy is affected by background noise, technical jargon, and low-quality audio.
- `--remove-fillers` uses conservative regex — it does not use an LLM or NLP library.
- Translation always targets English (Whisper limitation).
- Cleaning flags affect the full transcript text. Individual segment texts in timestamped output are not modified.
- `--summary` and `--notes` use extractive summarization — results improve on clear, well-structured content.
