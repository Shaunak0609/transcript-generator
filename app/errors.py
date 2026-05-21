"""
Custom exception hierarchy for the AI Video Transcriber.

All expected user-facing errors inherit from TranscriberError so that the
top-level handler in cli.main() can catch them in one place, print a
friendly message, and optionally show the full traceback in --debug mode.

Hierarchy:
  TranscriberError
  ├── DependencyError   – missing package or external tool
  ├── FileError         – bad input file (missing, wrong type, empty)
  ├── ConfigError       – invalid CLI argument or configuration
  ├── AudioError        – FFmpeg extraction failure
  ├── TranscriptionError – Whisper model or inference failure
  └── ExportError       – could not write an output file
"""


class TranscriberError(Exception):
    """Base class for all expected application errors.

    The optional `details` attribute carries technical information (e.g.
    FFmpeg stderr) that is only printed when --debug is active.
    """

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details


class DependencyError(TranscriberError):
    """A required external tool or Python package is missing."""


class FileError(TranscriberError):
    """Problem with an input file (missing, wrong extension, empty/corrupt)."""


class ConfigError(TranscriberError):
    """Invalid user-supplied argument or configuration value."""


class AudioError(TranscriberError):
    """FFmpeg audio extraction failed."""


class TranscriptionError(TranscriberError):
    """Whisper model loading or inference failed."""


class ExportError(TranscriberError):
    """Could not write an output file or create the output directory."""
