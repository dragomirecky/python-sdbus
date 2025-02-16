from __future__ import annotations

import logging
from functools import partial
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Iterable,
    Optional,
    Sequence,
    Tuple,
    Unpack,
    assert_never,
)

from _sdbus import (
    DbusDeprecatedFlag,
    DbusHiddenFlag,
    DbusNoReplyFlag,
    DbusPropertyConstFlag,
    DbusPropertyEmitsChangeFlag,
    DbusPropertyEmitsInvalidationFlag,
    DbusPropertyExplicitFlag,
    DbusUnprivilegedFlag,
    NameAllowReplacementFlag,
    NameQueueFlag,
    NameReplaceExistingFlag,
    SdBusError,
    SdBusInterface,
    SdBusMessage,
    _SdBus,
    sd_bus_open_system,
    sd_bus_open_system_remote,
    sd_bus_open_user,
)
from aiodbus.bus.any import (
    Dbus,
    DbusInterfaceBuilder,
    MemberFlags,
    MethodCallable,
    MethodFlags,
    PropertyFlags,
)
from aiodbus.bus.connection import DbusType
from aiodbus.bus.message import DbusMessage, _set_current_message
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


class SdBusInterfaceBuilder(DbusInterfaceBuilder):
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
                error.error_message or "",
            )

        reply.send()

    _property_flags_mask = (
        DbusPropertyConstFlag
        | DbusPropertyEmitsChangeFlag
        | DbusPropertyEmitsInvalidationFlag
        | DbusPropertyExplicitFlag
    )

    @staticmethod
    def _isolate_property_flags(flags: int) -> int:
        return flags & SdBusInterfaceBuilder._property_flags_mask

    _flag_to_sdbus: Dict[str, int] = {
        "deprecated": DbusDeprecatedFlag,
        "hidden": DbusHiddenFlag,
        "unprivileged": DbusUnprivilegedFlag,
        "no_reply": DbusNoReplyFlag,
        "explicit": DbusPropertyExplicitFlag,
        "emits_change": DbusPropertyEmitsChangeFlag,
        "emits_invalidation": DbusPropertyEmitsInvalidationFlag,
        "const": DbusPropertyConstFlag,
    }

    @staticmethod
    def _member_flags_to_int(flags) -> int:
        result = 0
        for flag_name, flag_value in flags.items():
            if flag_value:
                result |= SdBusInterfaceBuilder._flag_to_sdbus[flag_name]
        return result

    def add_method(
        self,
        name: str,
        signature: str,
        input_args_names: Sequence[str],
        result_signature: str,
        result_args_names: Sequence[str],
        callback: MethodCallable,
        **flags: Unpack[MethodFlags],
    ) -> None:
        flags_int = self._member_flags_to_int(flags)
        self._interface.add_method(
            name,
            signature,
            input_args_names,
            result_signature,
            result_args_names,
            flags_int,
            partial(self._method_handler, result_signature, callback),
        )

    @staticmethod
    def _is_property_flags_correct(flags: int) -> bool:
        num_of_flag_bits = SdBusInterfaceBuilder._isolate_property_flags(flags).bit_count()
        return 0 <= num_of_flag_bits <= 1

    def add_property(
        self,
        name: str,
        signature: str,
        get_function: Callable[[], DbusCompleteTypes],
        set_function: Optional[Callable[[DbusCompleteTypes], None]],
        **flags: Unpack[PropertyFlags],
    ) -> None:
        flags_int = self._member_flags_to_int(flags)
        assert self._is_property_flags_correct(flags_int), (
            "Incorrect number of Property flags. "
            "Only one of const, emits_change, emits_invalidation, explicit "
            "is allowed."
        )

        def getter(message: SdBusMessage):
            try:
                with _set_current_message(message):
                    data = get_function()
                    message.append_data(signature, data)
            except Exception as exc:
                if not isinstance(exc, MethodCallError):
                    logger.exception("Unhandled exception when handling a property get")
                raise

        def setter(message: SdBusMessage):
            try:
                assert set_function is not None
                with _set_current_message(message):
                    set_function(message.get_contents())
            except Exception as exc:
                if not isinstance(exc, MethodCallError):
                    logger.exception("Unhandled exception when handling a property set")
                raise

        self._interface.add_property(
            name, signature, getter, setter if set_function is not None else None, flags_int
        )

    def add_signal(
        self,
        name: str,
        signature: str,
        args_names: Sequence[str],
        **flags: Unpack[MemberFlags],
    ):
        flags_int = self._member_flags_to_int(flags)
        self._interface.add_signal(name, signature, args_names, flags_int)


class SdBus(Dbus):
    def __init__(self, bus: _SdBus) -> None:
        self._sdbus = bus

    @property
    def address(self) -> Optional[str]:
        return self._sdbus.address

    def create_interface(self) -> DbusInterfaceBuilder:
        return SdBusInterfaceBuilder(SdBusInterface())

    def export(self, path: str, name: str, interface: DbusInterfaceBuilder) -> Closeable:
        assert isinstance(interface, SdBusInterfaceBuilder)
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

    @staticmethod
    def _signal_handler(callback: Callable[[DbusMessage], None], message: DbusMessage) -> None:
        try:
            with _set_current_message(message):
                callback(message)
        except Exception:
            logger.exception("Unhandled exception when handling a signal")

    async def subscribe_signals(
        self,
        *,
        sender_filter: Optional[str] = None,
        path_filter: Optional[str] = None,
        interface_filter: Optional[str] = None,
        member_filter: Optional[str] = None,
        callback: Callable[[DbusMessage], None],
    ) -> Closeable:

        return await self._sdbus.match_signal_async(
            sender_filter,
            path_filter,
            interface_filter,
            member_filter,
            partial(self._signal_handler, callback),
        )

    def close(self) -> None:
        self._sdbus.close()

    def __enter__(self) -> "Dbus":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def sdbus_connect_local(address: DbusType):
    match address:
        case "session":
            return SdBus(sd_bus_open_user())
        case "system":
            return SdBus(sd_bus_open_system())
        case _:
            assert_never(address)


def sdbus_connect_remote(address: str):
    return SdBus(sd_bus_open_system_remote(address))
