from __future__ import annotations

from typing import Protocol

from _sdbus import SdBusError
from aiodbus.exceptions import DbusError


class Closeable(Protocol):
    def close(self) -> None: ...


class DbusExportHandle:
    def __init__(self, *items: Closeable) -> None:
        self._items = list(items)

    def append(self, item: Closeable) -> None:
        self._items.append(item)

    def close(self) -> None:
        try:
            while self._items:
                self._items.pop().close()
        except SdBusError as e:
            raise DbusError(str(e)) from e

    async def __aenter__(self) -> DbusExportHandle:
        return self

    def __enter__(self) -> DbusExportHandle:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    async def __aexit__(self, *_) -> None:
        self.close()
