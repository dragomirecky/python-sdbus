from contextvars import ContextVar
from typing import Callable, Literal, Optional, TypeAlias, Union

from _sdbus import (
    NameAllowReplacementFlag,
    NameQueueFlag,
    NameReplaceExistingFlag,
    SdBus,
    SdBusError,
    SdBusMessage,
    SdBusSlot,
    sd_bus_open_system,
    sd_bus_open_user,
)
from aiodbus.exceptions import (
    DbusError,
    SdBusRequestNameAlreadyOwnerError,
    SdBusRequestNameExistsError,
    SdBusRequestNameInQueueError,
)
from aiodbus.handle import Closeable


class Dbus:
    def __init__(self, bus: SdBus) -> None:
        self._sdbus = bus

    @property
    def address(self) -> Optional[str]:
        return self._sdbus.address

    async def request_name(
        self,
        name: str,
        *,
        queue: bool = False,
        allow_replacement: bool = False,
        replace_existing: bool = False,
    ) -> None:
        try:
            flags = 0
            if queue:
                flags |= NameQueueFlag
            if allow_replacement:
                flags |= NameAllowReplacementFlag
            if replace_existing:
                flags |= NameReplaceExistingFlag
            response = await self._sdbus.request_name(name, flags)
        except SdBusError as e:
            raise DbusError(e) from e

        result = response.get_contents()
        if result == 1:  # Success
            return
        elif result == 2:  # Reply In Queue
            raise SdBusRequestNameInQueueError()
        elif result == 3:
            raise SdBusRequestNameExistsError()
        elif result == 4:
            raise SdBusRequestNameAlreadyOwnerError()
        else:
            raise DbusError(f"Unknown result code: {result}")

    async def subscribe_signals(
        self,
        *,
        sender_filter: Optional[str] = None,
        path_filter: Optional[str] = None,
        interface_filter: Optional[str] = None,
        member_filter: Optional[str] = None,
        callback: Callable[[SdBusMessage], None],
    ) -> Closeable:
        return await self._sdbus.match_signal_async(
            sender_filter, path_filter, interface_filter, member_filter, callback
        )

    def close(self) -> None:
        self._sdbus.close()

    def __enter__(self) -> "Dbus":
        return self

    def __exit__(self, *_) -> None:
        self.close()


DbusAddress: TypeAlias = Union[Literal["system"], Literal["session"], str]


def connect(address: DbusAddress, *, make_default: bool = True) -> Dbus:
    match address:
        case "session":
            bus = Dbus(sd_bus_open_user())
        case "system":
            bus = Dbus(sd_bus_open_system())
        case _:
            raise NotImplementedError("Only 'session' and 'system' are supported")

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
