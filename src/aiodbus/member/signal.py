# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2023 igo95862
# Copyright (C) 2025, Alan Dragomirecký

# This file is part of aiodbus, a fork of python-sdbus.

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
from __future__ import annotations

from asyncio import Queue
from contextlib import closing
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Generic,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)
from weakref import WeakSet

from _sdbus import SdBus, SdBusInterface, SdBusMessage
from aiodbus import Dbus, get_default_bus
from aiodbus.dbus_common_elements import (
    DbusBoundMember,
    DbusLocalMember,
    DbusLocalObjectMeta,
    DbusMember,
    DbusProxyMember,
    DbusRemoteObjectMeta,
    DbusSignalCommon,
)
from aiodbus.handle import Closeable

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusExportHandle, DbusInterfaceBase


T = TypeVar("T")


class DbusSignal(DbusMember, DbusSignalCommon, Generic[T]):

    def __init__(
        self,
        signal_name: Optional[str],
        signal_signature: str,
        args_names: Sequence[str],
        flags: int,
        original_method: FunctionType,
    ):
        super().__init__(
            signal_name,
            signal_signature,
            args_names,
            flags,
            original_method,
        )

        self.local_callbacks: WeakSet[Callable[[T], Any]] = WeakSet()

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterfaceBase],
    ) -> DbusSignal[T]: ...

    @overload
    def __get__(
        self,
        obj: DbusInterfaceBase,
        obj_class: Type[DbusInterfaceBase],
    ) -> DbusBoundSignalBase[T]: ...

    def __get__(
        self,
        obj: Optional[DbusInterfaceBase],
        obj_class: Optional[Type[DbusInterfaceBase]] = None,
    ) -> Union[DbusBoundSignalBase[T], DbusSignal[T]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxySignal(self, dbus_meta)
            else:
                return DbusLocalSignal(self, dbus_meta)
        else:
            return self

    async def catch_anywhere(
        self,
        service_name: str,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        if bus is None:
            bus = get_default_bus()

        message_queue: Queue[SdBusMessage] = Queue()

        match_slot = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.interface_name,
            member_filter=self.signal_name,
            callback=message_queue.put_nowait,
        )

        with closing(match_slot):
            while True:
                next_signal_message = await message_queue.get()
                signal_path = next_signal_message.path
                assert signal_path is not None
                yield (signal_path, cast(T, next_signal_message.get_contents()))


class DbusBoundSignalBase(DbusBoundMember, AsyncIterable[T], Generic[T]):
    def __init__(self, dbus_signal: DbusSignal[T]) -> None:
        self.dbus_signal = dbus_signal

    @property
    def member(self) -> DbusMember:
        return self.dbus_signal

    async def catch(self) -> AsyncIterator[T]:
        raise NotImplementedError
        yield cast(T, None)

    __aiter__ = catch

    async def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        raise NotImplementedError
        yield "", cast(T, None)

    def emit(self, args: T) -> None:
        raise NotImplementedError


class DbusProxySignal(DbusBoundSignalBase[T], DbusProxyMember):
    def __init__(
        self,
        dbus_signal: DbusSignal[T],
        proxy_meta: DbusRemoteObjectMeta,
    ):
        super().__init__(dbus_signal)
        self.proxy_meta = proxy_meta

        self.__doc__ = dbus_signal.__doc__

    async def _register_match_slot(
        self,
        bus: Dbus,
        callback: Callable[[SdBusMessage], Any],
    ) -> Closeable:
        return await bus.subscribe_signals(
            sender_filter=self.proxy_meta.service_name,
            path_filter=self.proxy_meta.object_path,
            interface_filter=self.dbus_signal.interface_name,
            member_filter=self.dbus_signal.signal_name,
            callback=callback,
        )

    async def catch(self) -> AsyncIterator[T]:
        message_queue: Queue[SdBusMessage] = Queue()

        handle = await self._register_match_slot(
            self.proxy_meta.attached_bus,
            message_queue.put_nowait,
        )

        with closing(handle):
            while True:
                next_signal_message = await message_queue.get()
                yield cast(T, next_signal_message.get_contents())

    __aiter__ = catch

    async def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        if bus is None:
            bus = self.proxy_meta.attached_bus

        if service_name is None:
            service_name = self.proxy_meta.service_name

        message_queue: Queue[SdBusMessage] = Queue()

        handle = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.dbus_signal.interface_name,
            member_filter=self.dbus_signal.signal_name,
            callback=message_queue.put_nowait,
        )

        with closing(handle):
            while True:
                next_signal_message = await message_queue.get()
                signal_path = next_signal_message.path
                assert signal_path is not None
                yield (signal_path, cast(T, next_signal_message.get_contents()))

    def emit(self, args: T) -> None:
        raise RuntimeError("Cannot emit signal from D-Bus proxy.")


class DbusLocalSignal(DbusBoundSignalBase[T], DbusLocalMember):
    def __init__(
        self,
        dbus_signal: DbusSignal[T],
        local_meta: DbusLocalObjectMeta,
    ):
        super().__init__(dbus_signal)
        self.local_meta = local_meta

        self.__doc__ = dbus_signal.__doc__

    def _append_to_interface(
        self,
        interface: SdBusInterface,
        handle: DbusExportHandle,
    ) -> None:
        interface.add_signal(
            self.dbus_signal.signal_name,
            self.dbus_signal.signal_signature,
            self.dbus_signal.args_names,
            self.dbus_signal.flags,
        )

    async def catch(self) -> AsyncIterator[T]:
        new_queue: Queue[T] = Queue()

        signal_callbacks = self.dbus_signal.local_callbacks
        put_method = new_queue.put_nowait
        try:
            signal_callbacks.add(put_method)
            while True:
                next_data = await new_queue.get()
                yield next_data
        finally:
            signal_callbacks.remove(put_method)

    __aiter__ = catch

    async def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        raise NotImplementedError("TODO")
        yield

    def _emit_dbus_signal(self, args: T) -> None:
        attached_bus = self.local_meta.attached_bus
        if attached_bus is None:
            return

        serving_object_path = self.local_meta.serving_object_path
        if serving_object_path is None:
            return

        signal_message = attached_bus._sdbus.new_signal_message(
            serving_object_path,
            self.dbus_signal.interface_name,
            self.dbus_signal.signal_name,
        )

        if (not self.dbus_signal.signal_signature.startswith("(")) and isinstance(args, tuple):
            signal_message.append_data(self.dbus_signal.signal_signature, *args)
        elif self.dbus_signal.signal_signature == "" and args is None:
            ...
        else:
            signal_message.append_data(self.dbus_signal.signal_signature, args)

        signal_message.send()

    def emit(self, args: T) -> None:
        self._emit_dbus_signal(args)

        for callback in self.dbus_signal.local_callbacks:
            callback(args)


def dbus_signal(
    signal_signature: str = "",
    signal_args_names: Sequence[str] = (),
    flags: int = 0,
    signal_name: Optional[str] = None,
) -> Callable[[Callable[[Any], T]], DbusSignal[T]]:
    assert not isinstance(signal_signature, FunctionType), (
        "Passed function to decorator directly. " "Did you forget () round brackets?"
    )

    def signal_decorator(pseudo_function: Callable[[Any], T]) -> DbusSignal[T]:

        assert isinstance(pseudo_function, FunctionType)
        return DbusSignal(
            signal_name,
            signal_signature,
            signal_args_names,
            flags,
            pseudo_function,
        )

    return signal_decorator
