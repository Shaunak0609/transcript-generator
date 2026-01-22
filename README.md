**AI Video Transcriber & Translator**

A high-performance Python pipeline that transforms video files into professionally formatted Microsoft Word documents. Powered by OpenAI Whisper, it handles multi-language transcription and direct-to-English translation with a single command.

**Features include-**

Smart Extraction: Automatically strips audio from video using FFmpeg.

Whisper AI Integration: High-accuracy speech recognition (90+ languages).

English Translation: Translate foreign language audio (Japanese, Spanish, etc.) directly into English text.

Word Export: Outputs clean, editable .docx files.

Drag-and-Drop Friendly: Optimized for macOS/ZSH terminal usage.

**Mac Setup (One-Time)-**

Because this project uses AI models and media processing, you need two system tools installed via Homebrew:

# Install Media engine and Build tools
brew install ffmpeg cmake llvm@15


**Getting Started-**

1. Environment Setup

Clone this repo and set up your local virtual environment:

# Create the environment (using Python 3.12 for stability as 3.14 is a newer, less stable version)
python3.12 -m venv whisper_env
source whisper_env/bin/activate

# Install dependencies
export LLVM_CONFIG=$(brew --prefix llvm@15)/bin/llvm-config
pip install --prefer-binary openai-whisper python-docx


2. Usage

Always ensure your environment is active (source whisper_env/bin/activate) before running.

Standard Transcription:

python3 transcribe_video.py "path/to/video.mp4" en


Translate to English:

python3 transcribe_video.py "path/to/video.mp4" ja translate


Replace ja with the language code of your choice (es, fr, de, etc.).

**Note**

This tool uses machine learning models. While highly accurate, transcription and translation can be affected by:

High background noise or overlapping speech.

Technical jargon or rare dialects.

Low-quality audio sources.

Note: The first time you run the script, it will download the Whisper "base" model (~150MB).

📂 Project Structure

transcribe_video.py: Main execution script.

.gitignore: Prevents heavy AI models and environments from cluttering your Git repo.