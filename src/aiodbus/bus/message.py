from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional, Protocol, Tuple

if TYPE_CHECKING:
    from _sdbus import DbusCompleteType


class Message(Protocol):
    @property
    def path(self) -> Optional[str]: ...

    @property
    def sender(self) -> Optional[str]: ...

    def get_contents(self) -> Tuple[DbusCompleteType, ...]: ...


_current_message: ContextVar[Message] = ContextVar("current_message")


@contextmanager
def _set_current_message(message: Message):
    token = _current_message.set(message)
    try:
        yield message
    finally:
        _current_message.reset(token)


def get_current_message() -> Message:
    return _current_message.get()
