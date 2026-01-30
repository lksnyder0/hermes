"""
Unit tests for SessionRecorder (asciicast v2 format).
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermes.config import RecordingConfig
from hermes.session.recorder import SessionRecorder


@pytest.fixture
def recording_config(tmp_path: Path) -> RecordingConfig:
    """Recording config pointing at a tmp directory."""
    return RecordingConfig(
        enabled=True,
        output_dir=tmp_path / "recordings",
    )


@pytest.fixture
def disabled_config(tmp_path: Path) -> RecordingConfig:
    return RecordingConfig(
        enabled=False,
        output_dir=tmp_path / "recordings",
    )


@pytest.fixture
def metadata() -> dict:
    return {
        "username": "root",
        "source_ip": "192.168.1.100",
        "source_port": 54321,
        "container_id": "abc123def456",
    }


@pytest.fixture
def recorder(recording_config: RecordingConfig, metadata: dict) -> SessionRecorder:
    return SessionRecorder(
        config=recording_config,
        session_id="test-session-001",
        width=80,
        height=24,
        metadata=metadata,
    )


def _cast_path(recording_config: RecordingConfig) -> Path:
    return recording_config.output_dir / "test-session-001.cast"


def _parse_cast(path: Path) -> list:
    """Parse a .cast file into [header_dict, event1, event2, ...]."""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    result = [json.loads(lines[0])]  # header
    for line in lines[1:]:
        result.append(json.loads(line))
    return result


class TestSessionRecorderInit:
    """Tests for initialization and config handling."""

    def test_disabled_config_not_active(self, disabled_config: RecordingConfig):
        rec = SessionRecorder(
            config=disabled_config,
            session_id="s1",
            width=80,
            height=24,
        )
        rec.start()
        assert rec.active is False

    def test_disabled_config_no_file_created(
        self, disabled_config: RecordingConfig
    ):
        rec = SessionRecorder(
            config=disabled_config,
            session_id="s1",
            width=80,
            height=24,
        )
        rec.start()
        assert not disabled_config.output_dir.exists()

    def test_stores_parameters(self, recorder: SessionRecorder):
        assert recorder._session_id == "test-session-001"
        assert recorder._width == 80
        assert recorder._height == 24


class TestSessionRecorderStart:
    """Tests for start() — directory creation and header writing."""

    def test_creates_output_directory(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        assert recording_config.output_dir.is_dir()
        recorder.stop()

    def test_creates_cast_file(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        assert _cast_path(recording_config).exists()
        recorder.stop()

    def test_sets_active(self, recorder: SessionRecorder):
        recorder.start()
        assert recorder.active is True
        recorder.stop()

    def test_header_version(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.stop()
        header = _parse_cast(_cast_path(recording_config))[0]
        assert header["version"] == 2

    def test_header_dimensions(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.stop()
        header = _parse_cast(_cast_path(recording_config))[0]
        assert header["width"] == 80
        assert header["height"] == 24

    def test_header_timestamp_is_epoch(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        before = int(time.time())
        recorder.start()
        recorder.stop()
        after = int(time.time())
        header = _parse_cast(_cast_path(recording_config))[0]
        assert before <= header["timestamp"] <= after

    def test_header_contains_metadata(
        self,
        recorder: SessionRecorder,
        recording_config: RecordingConfig,
        metadata: dict,
    ):
        recorder.start()
        recorder.stop()
        header = _parse_cast(_cast_path(recording_config))[0]
        assert header["env"]["username"] == metadata["username"]
        assert header["env"]["source_ip"] == metadata["source_ip"]

    def test_permission_error_stays_inactive(self, metadata: dict):
        """If output_dir is unwritable, start() logs but doesn't raise."""
        config = RecordingConfig(enabled=True, output_dir=Path("/root/nope"))
        rec = SessionRecorder(
            config=config, session_id="s1", width=80, height=24, metadata=metadata
        )
        rec.start()  # should not raise
        assert rec.active is False


class TestSessionRecorderEvents:
    """Tests for recording I/O and resize events."""

    def test_record_output_format(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_output(b"Hello\r\n")
        recorder.stop()
        events = _parse_cast(_cast_path(recording_config))
        event = events[1]  # first event after header
        assert isinstance(event[0], float)
        assert event[0] >= 0.0
        assert event[1] == "o"
        assert event[2] == "Hello\r\n"

    def test_record_input_format(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_input(b"ls -la\n")
        recorder.stop()
        event = _parse_cast(_cast_path(recording_config))[1]
        assert event[1] == "i"
        assert event[2] == "ls -la\n"

    def test_record_resize_format(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_resize(120, 40)
        recorder.stop()
        event = _parse_cast(_cast_path(recording_config))[1]
        assert event[1] == "r"
        assert event[2] == "120x40"

    def test_elapsed_time_increases(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_output(b"first")
        time.sleep(0.02)
        recorder.record_output(b"second")
        recorder.stop()
        events = _parse_cast(_cast_path(recording_config))
        assert events[2][0] > events[1][0]

    def test_binary_data_decoded_with_replacement(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_output(b"\x80\xff hello")
        recorder.stop()
        event = _parse_cast(_cast_path(recording_config))[1]
        assert "\ufffd" in event[2]
        assert "hello" in event[2]

    def test_events_noop_when_not_started(self, recorder: SessionRecorder):
        """Events before start() should not raise or create files."""
        recorder.record_output(b"data")
        recorder.record_input(b"data")
        recorder.record_resize(80, 24)
        # no exception is success

    def test_events_noop_when_disabled(
        self, disabled_config: RecordingConfig
    ):
        rec = SessionRecorder(
            config=disabled_config, session_id="s1", width=80, height=24
        )
        rec.start()
        rec.record_output(b"data")  # should not raise
        rec.record_input(b"data")
        rec.stop()

    def test_event_count_tracked(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_output(b"a")
        recorder.record_input(b"b")
        recorder.record_resize(100, 50)
        assert recorder._event_count == 3
        recorder.stop()

    def test_write_error_does_not_raise(
        self, recorder: SessionRecorder
    ):
        """I/O error during write should be swallowed."""
        recorder.start()
        # Simulate write failure
        recorder._file.write = MagicMock(side_effect=OSError("disk full"))
        recorder.record_output(b"data")  # should not raise
        recorder.stop()


class TestSessionRecorderStop:
    """Tests for stop() and metadata writing."""

    def test_stop_sets_inactive(self, recorder: SessionRecorder):
        recorder.start()
        recorder.stop()
        assert recorder.active is False

    def test_stop_safe_to_call_twice(self, recorder: SessionRecorder):
        recorder.start()
        recorder.stop()
        recorder.stop()  # should not raise

    def test_stop_safe_when_never_started(self, recorder: SessionRecorder):
        recorder.stop()  # should not raise

    def test_write_metadata_creates_json(
        self,
        recorder: SessionRecorder,
        recording_config: RecordingConfig,
        metadata: dict,
    ):
        recorder.start()
        recorder.stop()
        recorder.write_metadata()
        json_path = recording_config.output_dir / "test-session-001.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["username"] == "root"
        assert data["source_ip"] == "192.168.1.100"
        assert data["container_id"] == "abc123def456"

    def test_write_metadata_noop_when_disabled(
        self, disabled_config: RecordingConfig
    ):
        rec = SessionRecorder(
            config=disabled_config, session_id="s1", width=80, height=24
        )
        rec.write_metadata()  # should not raise
        assert not disabled_config.output_dir.exists()


class TestSessionRecorderFullLifecycle:
    """End-to-end test parsing a complete .cast file."""

    def test_full_session_cast_file(
        self, recorder: SessionRecorder, recording_config: RecordingConfig
    ):
        recorder.start()
        recorder.record_output(b"$ ")
        recorder.record_input(b"whoami\n")
        recorder.record_output(b"root\r\n$ ")
        recorder.record_resize(120, 40)
        recorder.record_input(b"exit\n")
        recorder.stop()

        cast = _parse_cast(_cast_path(recording_config))

        # Header
        header = cast[0]
        assert header["version"] == 2
        assert header["width"] == 80
        assert header["height"] == 24
        assert isinstance(header["timestamp"], int)
        assert "env" in header

        # 5 events
        assert len(cast) == 6  # 1 header + 5 events

        # Event types in order
        assert cast[1][1] == "o"
        assert cast[1][2] == "$ "

        assert cast[2][1] == "i"
        assert cast[2][2] == "whoami\n"

        assert cast[3][1] == "o"
        assert cast[3][2] == "root\r\n$ "

        assert cast[4][1] == "r"
        assert cast[4][2] == "120x40"

        assert cast[5][1] == "i"
        assert cast[5][2] == "exit\n"

        # All elapsed times are non-negative floats, monotonically non-decreasing
        elapsed_times = [e[0] for e in cast[1:]]
        assert all(isinstance(t, float) for t in elapsed_times)
        assert all(t >= 0.0 for t in elapsed_times)
        for i in range(1, len(elapsed_times)):
            assert elapsed_times[i] >= elapsed_times[i - 1]

    def test_full_lifecycle_with_metadata(
        self,
        recorder: SessionRecorder,
        recording_config: RecordingConfig,
        metadata: dict,
    ):
        recorder.start()
        recorder.record_output(b"hello")
        recorder.stop()
        recorder.write_metadata()

        # Both files exist
        assert _cast_path(recording_config).exists()
        json_path = recording_config.output_dir / "test-session-001.json"
        assert json_path.exists()

        # Metadata matches
        data = json.loads(json_path.read_text())
        assert data == metadata
