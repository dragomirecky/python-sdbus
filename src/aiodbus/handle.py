from __future__ import annotations

from typing import Any, Protocol


class Closeable(Protocol):
    def close(self) -> None: ...


class DbusExportHandle:
    def __init__(self, *items: Closeable) -> None:
        self._items = list(items)

    def append(self, item: Closeable) -> None:
        self._items.append(item)

    def close(self) -> None:
        while self._items:
            self._items.pop().close()

    stop = close  # for backwards compatibility

    async def __aenter__(self) -> DbusExportHandle:
        return self

    def __enter__(self) -> DbusExportHandle:
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()
