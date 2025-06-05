from __future__ import annotations

import asyncio
import contextvars
import errno
import logging
from collections import defaultdict
from functools import partial, wraps
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Iterable,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Unpack,
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
    SdBusSlot,
    _SdBus,
    sd_bus_open_system,
    sd_bus_open_system_remote,
    sd_bus_open_user,
)
from aiodbus.basic_types import DbusCompleteType, DbusCompleteTypes
from aiodbus.bus.any import (
    Dbus,
    DbusInterfaceBuilder,
    MemberFlags,
    MethodCallable,
    MethodFlags,
    PropertyFlags,
)
from aiodbus.bus.connection import DbusType
from aiodbus.bus.message import DbusMessage, set_current_message
from aiodbus.closeable import Closeable, CloseableFromCallback
from aiodbus.exceptions import (
    AlreadyOwner,
    CallFailedError,
    DbusError,
    MethodCallError,
    NameExistsError,
    NameInQueueError,
)

logger = logging.getLogger(__name__)


class SdBusAnyServingInterface(Protocol):
    name: str
    path: str
    object_manager_advertised: bool

    def close(self): ...


def translate_sdbus_error[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except SdBusError as e:
            if len(e.args) > 1 and e.args[1] == errno.ESRCH:
                raise RuntimeError("No object manager found for this path.") from e
            else:
                raise DbusError(e) from e

    return wrapper


class SdBusServingInterface(DbusInterfaceBuilder):
    def __init__(self, interface: SdBusInterface, name: str, path: str) -> None:
        self._interface = interface
        self.name = name
        self.path = path
        self.object_manager_advertised = False

    @staticmethod
    async def _method_handler(
        result_signature: str, callback: MethodCallable, message: SdBusMessage
    ) -> None:
        try:

            async def wrapped():
                with set_current_message(message):
                    return await callback(*message.parse_to_tuple())

            ctx = contextvars.copy_context()
            task = asyncio.create_task(wrapped(), context=ctx)
            reply_data = await task

            if not message.expect_reply:
                return

            reply = message.create_reply()
            if isinstance(reply_data, tuple):
                if reply_data:
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

                logger.exception(
                    "Exception in method handler for %s.%s (%s)",
                    message.path,
                    message.member,
                    message.path,
                )
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
        return flags & SdBusServingInterface._property_flags_mask

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
                result |= SdBusServingInterface._flag_to_sdbus[flag_name]
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
        num_of_flag_bits = SdBusServingInterface._isolate_property_flags(flags).bit_count()
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
                with set_current_message(message):
                    data = get_function()
                    message.append_data(signature, data)
            except Exception as exc:
                if not isinstance(exc, MethodCallError):
                    logger.exception("Exception in getter %s (%s)", name, self.name)
                raise

        def setter(message: SdBusMessage):
            try:
                assert set_function is not None
                with set_current_message(message):
                    set_function(message.get_contents())
            except Exception as exc:
                if not isinstance(exc, MethodCallError):
                    logger.exception("Exception in setter %s (%s)", name, self.name)
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

    def close(self):
        if slot := self._interface.slot:
            slot.close()


class SdBusServiceObjectManagerInterface:
    def __init__(self, bus: _SdBus, path: str, slot: SdBusSlot) -> None:
        self.name = "org.freedesktop.DBus.ObjectManager"
        self.path = path
        self.object_manager_advertised = False
        self._bus = bus
        self._slot = slot

    def close(self) -> None:
        self._slot.close()


class SdBus(Dbus[SdBusServingInterface]):
    def __init__(self, bus: _SdBus) -> None:
        self._sdbus = bus
        self._exported: dict[str, dict[str, SdBusAnyServingInterface]] = defaultdict(dict)
        self._closed = False

    @property
    def address(self) -> Optional[str]:
        return self._sdbus.address

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
            return reply.parse_to_tuple()

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
    ) -> None:
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
        elif result == 3:  # Name exists
            raise NameExistsError()
        elif result == 4:  # Already an owner
            raise AlreadyOwner()
        else:
            raise DbusError(f"Unknown result code: {result}")

    @staticmethod
    def _signal_handler(callback: Callable[[DbusMessage], None], message: DbusMessage) -> None:
        try:
            with set_current_message(message):
                callback(message)
        except Exception:
            logger.exception("Failure in signal handler for path %s", message.path)

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

    def create_interface(self, name: str, path: str) -> SdBusServingInterface:
        return SdBusServingInterface(SdBusInterface(), name, path)

    def export_interface(self, interface: SdBusServingInterface) -> Closeable:
        assert (
            interface.name not in self._exported[interface.path]
        ), "interface %s at %s already exported" % (
            interface.name,
            interface.path,
        )
        self._sdbus.add_interface(interface._interface, interface.path, interface.name)
        closeable = CloseableFromCallback(partial(self._unexport_interface, interface))
        self._exported[interface.path][interface.name] = interface
        return closeable

    def _unexport_interface(self, interface: SdBusAnyServingInterface) -> None:
        interface.close()
        self._exported[interface.path].pop(interface.name)
        if not self._exported[interface.path]:
            self._exported.pop(interface.path)

    def export_object_manager(self, path: str) -> Closeable:
        slot = self._sdbus.add_object_manager(path)
        interface = SdBusServiceObjectManagerInterface(bus=self._sdbus, path=path, slot=slot)
        closeable = CloseableFromCallback(partial(self._unexport_interface, interface))
        self._exported[interface.path][interface.name] = interface
        return closeable

    @translate_sdbus_error
    def emit_interfaces_added(self, path: str, interfaces: list[str]) -> None:
        exported_interfaces = self._exported[path]
        any_interface_advertised = any(
            i.object_manager_advertised for i in exported_interfaces.values()
        )

        if not any_interface_advertised:
            self._sdbus.emit_object_added(path)
        else:
            self._sdbus.emit_interfaces_added(path, *interfaces)

        for interface in exported_interfaces.values():
            interface.object_manager_advertised = True

    @translate_sdbus_error
    def emit_interfaces_removed(self, path: str, interfaces: list[str]) -> None:
        exported_interfaces = self._exported[path]
        advertised_interfaces = set(i.name for i in exported_interfaces.values())
        to_be_removed_interfaces = set(interfaces)
        interfaces_that_will_remain = advertised_interfaces - to_be_removed_interfaces

        if interfaces_that_will_remain:
            self._sdbus.emit_interfaces_removed(path, *interfaces)
        else:
            self._sdbus.emit_object_removed(path)

        for interface in exported_interfaces.values():
            interface.object_manager_advertised = False

    @translate_sdbus_error
    def emit_properties_changed(self, path: str, interface: str, properties: list[str]) -> None:
        return self._sdbus.emit_properties_changed(path, interface, *properties)

    def _unexport_all_interfaces(self) -> None:
        while len(self._exported):
            path = next(iter(self._exported))
            interfaces = self._exported[path]
            name = next(iter(interfaces))
            interface = interfaces[name]
            self._unexport_interface(interface)

    def close(self) -> None:
        self._unexport_all_interfaces()
        self._sdbus.close()
        self._closed = True

    def __enter__(self) -> Dbus:
        return self

    def __exit__(self, *_) -> None:
        self.close()


def sdbus_connect_local(address: DbusType):
    match address:
        case "session":
            return SdBus(sd_bus_open_user())
        case "system":
            return SdBus(sd_bus_open_system())


def sdbus_connect_remote(address: str):
    return SdBus(sd_bus_open_system_remote(address))
