"""Session recording in asciicast v2 format."""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from sandtrap.config import RecordingConfig

logger = logging.getLogger(__name__)


class SessionRecorder:
    """
    Records SSH session I/O to asciicast v2 .cast files.

    Writes are streamed to disk immediately (no full-session buffering).
    All public methods catch exceptions internally — recording failure
    never propagates to the caller.
    """

    def __init__(
        self,
        config: RecordingConfig,
        session_id: str,
        width: int = 80,
        height: int = 24,
        metadata: Optional[dict] = None,
    ) -> None:
        self._config = config
        self._session_id = session_id
        self._width = width
        self._height = height
        self._metadata = metadata or {}
        self._file = None
        self._start_time: float = 0.0
        self._event_count: int = 0

    @property
    def active(self) -> bool:
        """True when the recording file is open and accepting events."""
        return self._file is not None

    def start(self) -> None:
        """Open .cast file and write the asciicast v2 header. No-op if disabled."""
        if not self._config.enabled:
            return
        try:
            output_dir = Path(self._config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{self._session_id}.cast"
            self._file = open(path, "w", encoding="utf-8")
            self._start_time = time.monotonic()
            header = {
                "version": 2,
                "width": self._width,
                "height": self._height,
                "timestamp": int(time.time()),
            }
            if self._metadata:
                header["env"] = self._metadata
            self._file.write(json.dumps(header, separators=(",", ":")) + "\n")
            self._file.flush()
            logger.info("Recording started: %s", path)
        except Exception:
            logger.exception(
                "Failed to start recording for %s", self._session_id
            )
            self._file = None

    def record_output(self, data: bytes) -> None:
        """Record output event (container -> SSH client)."""
        self._record_event("o", data)

    def record_input(self, data: bytes) -> None:
        """Record input event (SSH client -> container)."""
        self._record_event("i", data)

    def record_resize(self, width: int, height: int) -> None:
        """Record terminal resize event."""
        if not self._file:
            return
        try:
            elapsed = time.monotonic() - self._start_time
            line = json.dumps(
                [round(elapsed, 6), "r", f"{width}x{height}"],
                separators=(",", ":"),
            )
            self._file.write(line + "\n")
            self._file.flush()
            self._event_count += 1
        except Exception:
            logger.warning(
                "Failed to record resize for %s",
                self._session_id,
                exc_info=True,
            )

    def stop(self) -> None:
        """Close recording file. Safe to call multiple times."""
        if self._file:
            try:
                self._file.close()
                logger.info(
                    "Recording stopped for %s: %d events",
                    self._session_id,
                    self._event_count,
                )
            except Exception:
                logger.warning(
                    "Error closing recording for %s",
                    self._session_id,
                    exc_info=True,
                )
            finally:
                self._file = None

    def write_metadata(self) -> None:
        """Write JSON metadata sidecar file."""
        if not self._config.enabled:
            return
        try:
            path = Path(self._config.output_dir) / f"{self._session_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, indent=2, default=str)
        except Exception:
            logger.warning(
                "Failed to write metadata for %s",
                self._session_id,
                exc_info=True,
            )

    def _record_event(self, event_type: str, data: bytes) -> None:
        """Write a single event line to the .cast file."""
        if not self._file:
            return
        try:
            elapsed = time.monotonic() - self._start_time
            text = data.decode("utf-8", errors="replace")
            line = json.dumps(
                [round(elapsed, 6), event_type, text],
                separators=(",", ":"),
            )
            self._file.write(line + "\n")
            self._file.flush()
            self._event_count += 1
        except Exception:
            logger.warning(
                "Failed to record %s event for %s",
                event_type,
                self._session_id,
                exc_info=True,
            )
