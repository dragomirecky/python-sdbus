from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional, Protocol


class DbusMessage[T](Protocol):
    @property
    def path(self) -> Optional[str]: ...

    @property
    def sender(self) -> Optional[str]: ...

    def get_contents(self) -> T: ...


_current_message: ContextVar[DbusMessage] = ContextVar("current_message")


@contextmanager
def _set_current_message(message: DbusMessage):
    token = _current_message.set(message)
    try:
        yield message
    finally:
        _current_message.reset(token)


def get_current_message() -> DbusMessage:
    return _current_message.get()
