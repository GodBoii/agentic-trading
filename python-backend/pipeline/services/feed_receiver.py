"""Keep the SDK event loop running while the consumer ranks and records ticks."""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class ReceivedPacket:
    packet: dict
    received_at: datetime
    received_monotonic: float


class FeedReceiver:
    def __init__(self, feed: Any, now: Callable[[], datetime], capacity: int = 8192):
        if capacity < 1:
            raise ValueError("feed queue capacity must be positive")
        self.feed = feed
        self.now = now
        self.queue: Queue[ReceivedPacket] = Queue(maxsize=capacity)
        self.high_water = 0
        self.full_waits = 0
        self.error: BaseException | None = None
        self.finished = Event()
        self.ready = Event()
        self.task: asyncio.Task | None = None
        self.pending: ReceivedPacket | None = None
        self.thread = Thread(target=self._run, name="intra-feed-receiver", daemon=True)

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("feed receiver did not start")

    def _run(self) -> None:
        asyncio.set_event_loop(self.feed.loop)
        self.task = self.feed.loop.create_task(self._receive())
        self.ready.set()
        try:
            self.feed.loop.run_until_complete(self.task)
        except asyncio.CancelledError:
            pass
        except BaseException as exc:
            self.error = exc
        finally:
            self.finished.set()

    async def _receive(self) -> None:
        while True:
            packet = await self.feed.get_instrument_data()
            if not isinstance(packet, dict):
                continue
            item = ReceivedPacket(packet, self.now(), time.monotonic())
            self.pending = item
            while True:
                try:
                    self.queue.put_nowait(item)
                    self.pending = None
                    self.high_water = max(self.high_water, self.queue.qsize())
                    break
                except Full:
                    self.full_waits += 1
                    # Keep ping/pong and close tasks runnable under backpressure.
                    await asyncio.sleep(0.001)

    def get(self, timeout: float) -> ReceivedPacket:
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.queue.get(timeout=min(0.1, max(0, deadline - time.monotonic())))
            except Empty:
                if self.finished.is_set():
                    if self.error is not None:
                        raise RuntimeError("feed receiver failed") from self.error
                    raise RuntimeError("feed receiver stopped")
                if time.monotonic() >= deadline:
                    raise TimeoutError("feed receiver idle")

    def stop(self) -> None:
        if self.thread.is_alive():
            if self.task is not None:
                self.feed.loop.call_soon_threadsafe(self.task.cancel)
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("feed receiver did not stop")

    def drain(self) -> Iterator[ReceivedPacket]:
        """After stop, include the decoded packet held behind a full queue."""
        if self.thread.is_alive():
            raise RuntimeError("stop the feed receiver before draining")
        while True:
            try:
                yield self.queue.get_nowait()
            except Empty:
                break
        if self.pending is not None:
            item, self.pending = self.pending, None
            yield item
