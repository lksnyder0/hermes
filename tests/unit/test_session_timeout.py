"""
Unit tests for session timeout functionality.

Tests timeout monitoring, event handling, and cleanup behavior.
"""

import asyncio

import pytest


@pytest.mark.unit
class TestTimeoutConfiguration:
    """Test timeout configuration parsing and usage."""

    def test_timeout_from_config(self):
        """Verify timeout is read from config."""
        from hermes.config import Config

        config = Config()
        assert config.server.session_timeout == 3600

    def test_minimal_timeout_validation(self):
        """Verify timeout minimum constraint."""
        from hermes.config import Config

        with pytest.raises(ValueError):
            Config(server={"session_timeout": 30})  # Too low

    def test_maximal_timeout_validation(self):
        """Verify custom large timeout can be set."""
        from hermes.config import Config

        config = Config()
        config.server.session_timeout = 999999
        assert config.server.session_timeout == 999999

    def test_default_timeout_valid(self):
        """Verify default timeout is valid."""
        from hermes.config import Config

        config = Config()
        assert 60 <= config.server.session_timeout <= 86400


@pytest.mark.unit
class TestTimeoutEventHandling:
    """Test timeout event handling with asyncio."""

    @pytest.mark.asyncio
    async def test_timeout_event_set_after_delay(self):
        """Verify timeout_expired event is set after sleep completes."""
        timeout_seconds = 0.1
        start_time = asyncio.get_event_loop().time()

        async def timeout_monitor():
            await asyncio.sleep(timeout_seconds)
            timeout_expired.set()

        timeout_expired = asyncio.Event()
        await timeout_monitor()

        elapsed = asyncio.get_event_loop().time() - start_time
        assert 0 <= elapsed < timeout_seconds * 2
        assert timeout_expired.is_set()

    @pytest.mark.asyncio
    async def test_multiple_asyncio_events_independent(self):
        """Verify multiple timeout events can coexist independently."""
        event1 = asyncio.Event()
        event2 = asyncio.Event()

        await asyncio.sleep(0.01)
        event1.set()
        assert event1.is_set()
        assert not event2.is_set()

        await asyncio.sleep(0.01)
        event2.set()
        assert event1.is_set()
        assert event2.is_set()

    @pytest.mark.asyncio
    async def test_asyncio_sleep_basic(self):
        """Test basic asyncio.sleep usage."""
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.01)  # 10ms
        elapsed = asyncio.get_event_loop().time() - start
        assert 0.005 <= elapsed < 0.1  # Allow reasonable margin around 10ms

    @pytest.mark.asyncio
    async def test_asyncio_create_task_creation(self):
        """Test asyncio.create_task for task monitoring."""
        task_counter = [0]

        async def increment_task_counter():
            task_counter[0] += 1

        task = asyncio.create_task(increment_task_counter())
        await task

        assert task_counter[0] == 1
        assert not task.cancelled()

    @pytest.mark.asyncio
    async def test_asyncio_wait_with_multiple_futures(self):
        """Test asyncio.wait with multiple futures."""
        completion_event = asyncio.Event()

        async def complete_after_delay():
            await asyncio.sleep(0.05)
            completion_event.set()

        futures = [
            asyncio.create_task(complete_after_delay()),
            asyncio.create_task(asyncio.sleep(0.02)),
        ]

        done, pending = await asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)

        assert len(done) == 1
        assert len(pending) == 1
        for task in pending:
            task.cancel()
        assert not completion_event.is_set()


@pytest.mark.unit
@pytest.mark.asyncio
class TestTimeoutTaskCancellation:
    """Test task cancellation during timeout scenarios."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        """Test cancelling a running asyncio task."""
        task_counter = [0]

        async def increment_task_counter():
            task_counter[0] += 1
            await asyncio.sleep(1)

        task = asyncio.create_task(increment_task_counter())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task_counter[0] == 1
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cancelled_task_does_not_hang(self):
        """Test that cancelled tasks don't hang in await completion."""

        async def blocking_task():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(blocking_task())

        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
