from __future__ import annotations

import logging
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Iterable,
    Literal,
    Optional,
    Protocol,
    Sequence,
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
    SdBusInterface,
    SdBusMessage,
    sd_bus_open_system,
    sd_bus_open_user,
)
from aiodbus.exceptions import (
    AlreadyOwner,
    CallFailedError,
    DbusError,
    MethodCallError,
    NameExistsError,
    NameInQueueError,
)
from aiodbus.handle import Closeable

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from _sdbus import DbusCompleteType, DbusCompleteTypes


class Message(Protocol):
    def get_contents(self) -> Tuple[DbusCompleteType, ...]: ...


class MethodCallable(Protocol):
    async def __call__(self, *args: DbusCompleteType) -> Any: ...


class Interface(Protocol):
    def add_method(
        self,
        name: str,
        signature: str,
        input_args_names: Sequence[str],
        result_signature: str,
        result_args_names: Sequence[str],
        flags: int,
        callback: MethodCallable,
    ) -> None: ...

    def add_property(
        self,
        name: str,
        signature: str,
        get_function: Callable[[], DbusCompleteTypes],
        set_function: Optional[Callable[[DbusCompleteTypes], None]],
        flags: int,
    ) -> None: ...

    def add_signal(
        self,
        name: str,
        signature: str,
        args_names: Tuple[str, ...],
        flags: int,
    ) -> None: ...


_current_message: ContextVar[SdBusMessage] = ContextVar("current_message")


@contextmanager
def _set_current_message(message: SdBusMessage):
    token = _current_message.set(message)
    try:
        yield message
    finally:
        _current_message.reset(token)


def get_current_message() -> Message:
    return _current_message.get()


class SdBusInterfaceWrapper(Interface):
    def __init__(self, interface: SdBusInterface) -> None:
        self._interface = interface

    @staticmethod
    async def _method_handler(
        result_signature: str, callback: MethodCallable, message: SdBusMessage
    ) -> None:
        try:
            with _set_current_message(message):
                reply_data = await callback(*message.parse_to_tuple())

            if not message.expect_reply:
                return

            reply = message.create_reply()
            if isinstance(reply_data, tuple):
                try:
                    reply.append_data(result_signature, *reply_data)
                except TypeError:
                    # In case of single struct result type
                    # We can't figure out if return is multiple values
                    # or a tuple
                    reply.append_data(result_signature, reply_data)
            elif reply_data is not None:
                reply.append_data(result_signature, reply_data)
        except Exception as exc:
            if isinstance(exc, MethodCallError):
                error = exc
            else:
                logger.exception("Unhandled exception when handling a method call")
                error = CallFailedError()

            if not message.expect_reply:
                return

            reply = message.create_error_reply(
                error.error_name,
                str(error.args[0]) if error.args else "",
            )

        reply.send()

    def add_method(
        self,
        name: str,
        signature: str,
        input_args_names: Sequence[str],
        result_signature: str,
        result_args_names: Sequence[str],
        flags: int,
        callback: MethodCallable,
    ) -> None:
        self._interface.add_method(
            name,
            signature,
            input_args_names,
            result_signature,
            result_args_names,
            flags,
            partial(self._method_handler, result_signature, callback),
        )

    def add_property(
        self,
        name: str,
        signature: str,
        get_function: Callable[[], DbusCompleteTypes],
        set_function: Optional[Callable[[DbusCompleteTypes], None]],
        flags: int,
    ) -> None:

        def getter(message: SdBusMessage):
            with _set_current_message(message):
                data = get_function()
                message.append_data(signature, data)

        def setter(message: SdBusMessage):
            assert set_function is not None
            with _set_current_message(message):
                set_function(message.get_contents())

        self._interface.add_property(
            name, signature, getter, setter if set_function is not None else None, flags
        )

    def add_signal(
        self,
        name: str,
        signature: str,
        args_names: Tuple[str, ...],
        flags: int,
    ):
        self._interface.add_signal(name, signature, args_names, flags)


class Dbus:
    def __init__(self, bus: SdBus) -> None:
        self._sdbus = bus

    @property
    def address(self) -> Optional[str]:
        return self._sdbus.address

    def create_interface(self) -> Interface:
        return SdBusInterfaceWrapper(SdBusInterface())

    def export(self, path: str, name: str, interface: Interface) -> Closeable:
        assert isinstance(interface, SdBusInterfaceWrapper)
        self._sdbus.add_interface(interface._interface, path, name)
        assert interface._interface.slot is not None
        return interface._interface.slot

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
        args: Iterable[DbusCompleteType],
        no_reply: bool = False,
    ) -> Tuple[DbusCompleteType, ...]:
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
    ) -> Tuple[DbusCompleteType, ...]:
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
        args: Iterable[DbusCompleteType],
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
        args: Iterable[DbusCompleteType],
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
