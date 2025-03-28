from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class Closeable(Protocol):
    def close(self) -> None: ...


class CloseableFromCallback:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.close = callback

