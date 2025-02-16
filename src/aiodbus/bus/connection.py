from __future__ import annotations

from contextvars import ContextVar
from typing import Literal, overload

from aiodbus.bus.any import Dbus

type DbusType = Literal["system"] | Literal["session"]
type DbusAddress = str


@overload
def connect(bus_type: DbusType, /, *, make_default: bool = True) -> Dbus: ...


@overload
def connect(*, remote: str, make_default: bool = True) -> Dbus: ...


def connect(
    bus_type: DbusType | None = None,
    /,
    *,
    remote: DbusAddress | None = None,
    make_default: bool = True,
) -> Dbus:
    from aiodbus.bus.sdbus import sdbus_connect_local, sdbus_connect_remote

    if bus_type is None:
        if remote is None:
            raise ValueError("Either bus_type or remote must be specified")
        bus = sdbus_connect_remote(remote)
    else:
        bus = sdbus_connect_local(bus_type)

    if make_default:
        set_default_bus(bus)

    return bus


_default_bus: ContextVar[Dbus] = ContextVar("default_bus")


def get_default_bus() -> Dbus:
    try:
        return _default_bus.get()
    except LookupError:
        return connect("session", make_default=True)


def set_default_bus(new_default: Dbus) -> None:
    _default_bus.set(new_default)
