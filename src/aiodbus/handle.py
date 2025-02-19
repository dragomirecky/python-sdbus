from __future__ import annotations

from typing import Callable, Protocol

from _sdbus import SdBusError
from aiodbus.exceptions import DbusError


class Closeable(Protocol):
    def close(self) -> None: ...


class CloseableFromCallback:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.close = callback


class DbusExportHandle:
    def __init__(self, *items: Closeable) -> None:
        self._items = list(items)

    def prepend(self, item: Closeable) -> None:
        self._items.insert(0, item)

    def append(self, item: Closeable) -> None:
        self._items.append(item)

    def close(self) -> None:
        excs = []
        while self._items:
            try:
                try:
                    self._items.pop(0).close()
                except SdBusError as e:
                    raise DbusError(str(e)) from e
            except Exception as e:
                excs.append(e)
        if not excs:
            return
        elif len(excs) == 1:
            raise excs[0]
        else:
            raise ExceptionGroup("Multiple exceptions happend when closing handle", excs)

    async def __aenter__(self) -> DbusExportHandle:
        return self

    def __enter__(self) -> DbusExportHandle:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    async def __aexit__(self, *_) -> None:
        self.close()
