from app.config import DEFAULT_MODEL
from app.errors import DependencyError, TranscriptionError
from app.logger import get_logger


def run_whisper(audio_path, language_code, do_translate, model_name=DEFAULT_MODEL):
    """Load Whisper and transcribe or translate the given audio file.

    Returns the full Whisper result dict, including result["text"] and result["segments"].
    """
    log = get_logger()

    task = "translate" if do_translate else "transcribe"
    lang_display = language_code or "auto-detect"
    label = "Translation (to English)" if do_translate else f"Transcription ({lang_display})"

    log.info("--- 2. RUNNING WHISPER AI ---")
    log.info(f"Task:  {label}")
    log.info(f"Model: {model_name}")
    log.info("Note:  The AI model may take a minute to process...")

    try:
        import whisper
    except ImportError:
        raise DependencyError(
            "The 'openai-whisper' package is not installed.\n"
            "Activate your virtual environment, then run:\n"
            "  pip install openai-whisper"
        )

    try:
        model = whisper.load_model(model_name)
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load the '{model_name}' Whisper model.\n"
            "This can happen if the model download was interrupted.\n"
            "Delete the cached model file and try again — Whisper will re-download it.",
            details=str(e),
        ) from e

    try:
        result = model.transcribe(audio_path, language=language_code, task=task)
    except Exception as e:
        raise TranscriptionError(
            "Whisper failed to process the audio.\n"
            "The file may be silent, too short, or contain only non-speech sounds.\n"
            "Run with --debug for details.",
            details=str(e),
        ) from e

    if not result.get("text", "").strip():
        raise TranscriptionError(
            "Whisper returned an empty transcript.\n"
            "The audio may be silent, too short, or contain only non-speech sounds."
        )

    # Log metadata — not the transcript text itself
    word_count = len(result["text"].split())
    seg_count  = len(result.get("segments", []))
    log.debug(f"Transcript stats: {word_count} words, {seg_count} segments")

    return result
