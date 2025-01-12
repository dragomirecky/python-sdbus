from __future__ import annotations

from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Callable,
    Iterable,
    Literal,
    Optional,
    Protocol,
    Tuple,
    TypeAlias,
    Union,
)

from _sdbus import (
    NameAllowReplacementFlag,
    NameQueueFlag,
    NameReplaceExistingFlag,
    SdBus,
    SdBusError,
    SdBusMessage,
    sd_bus_open_system,
    sd_bus_open_user,
)
from aiodbus.exceptions import (
    AlreadyOwner,
    DbusError,
    MethodCallError,
    NameExistsError,
    NameInQueueError,
)
from aiodbus.handle import Closeable

if TYPE_CHECKING:
    from _sdbus import DbusCompleteTypes


class Message(Protocol):
    def get_contents(self) -> Tuple[DbusCompleteTypes, ...]: ...


class Interface(Protocol):
    def add_method(
        self,
        name: str,
        signature: str,
        input_args_names: Tuple[str, ...],
        result_signature: str,
        result_args_names: Tuple[str, ...],
        flags: int,
        callback: Callable[[Message], None],
    ) -> None: ...

    def add_property(
        self,
        name: str,
        signature: str,
        get_function: Callable[[Message], DbusCompleteTypes],
        set_function: Optional[Callable[[Message], None]],
        flags: int,
    ) -> None: ...

    def add_signal(
        self,
        name: str,
        signature: str,
        args_names: Tuple[str, ...],
        flags: int,
    ) -> None: ...


class Dbus:
    def __init__(self, bus: SdBus) -> None:
        self._sdbus = bus

    @property
    def address(self) -> Optional[str]:
        return self._sdbus.address

    def create_interface(self) -> Interface: ...

    def export(self, path: str, name: str, interface: Interface) -> None: ...

    def _raise_on_error(self, reply: SdBusMessage) -> None:
        if error := reply.get_error():
            name, message = error
            raise MethodCallError.create(name, message)

    async def call_method(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteTypes],
        no_reply: bool = False,
    ) -> Tuple[DbusCompleteTypes, ...]:
        message = self._sdbus.new_method_call_message(destination, path, interface, member)
        if args:
            message.append_data(signature, *args)
        if no_reply:
            message.expect_reply = False
            message.send()
            return ()
        else:
            reply = await self._sdbus.call_async(message)
            self._raise_on_error(reply)
            return reply.get_contents()

    async def get_property(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
    ) -> Tuple[DbusCompleteTypes, ...]:
        message = self._sdbus.new_property_get_message(destination, path, interface, member)
        reply = await self._sdbus.call_async(message)
        self._raise_on_error(reply)
        return reply.get_contents()

    async def set_property(
        self,
        *,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteTypes],
    ) -> None:
        message = self._sdbus.new_property_set_message(destination, path, interface, member)
        message.append_data("v", (signature, *args))
        response = await self._sdbus.call_async(message)
        self._raise_on_error(response)

    def emit_signal(
        self,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: Iterable[DbusCompleteTypes],
    ):
        message = self._sdbus.new_signal_message(path, interface, member)
        if not signature.startswith("(") and isinstance(args, tuple):
            message.append_data(signature, *args)
        elif signature == "" and args is None:
            ...
        else:
            message.append_data(signature, args)
        message.send()

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
            raise NameInQueueError()
        elif result == 3:
            raise NameExistsError()
        elif result == 4:
            raise AlreadyOwner()
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
