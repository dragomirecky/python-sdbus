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

from abc import ABC, abstractmethod
from asyncio import Queue
from contextlib import closing
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    Unpack,
    cast,
    overload,
)
from weakref import WeakSet

from aiodbus import Dbus, get_default_bus
from aiodbus.bus import Interface, MemberFlags
from aiodbus.bus.message import Message
from aiodbus.handle import Closeable
from aiodbus.member.base import (
    DbusBoundMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusLocalObjectMeta, DbusRemoteObjectMeta

if TYPE_CHECKING:
    from _sdbus import DbusCompleteTypes
    from aiodbus.interface.base import DbusExportHandle, DbusInterface


class DbusSignal[T](DbusMember):
    def __init__(
        self,
        signature: str = "",
        name: Optional[str] = None,
        args_names: Sequence[str] = (),
        **flags: Unpack[MemberFlags],
    ):
        super().__init__(name=name)
        self.signature = signature
        self.args_names = args_names
        self.flags = flags
        self.local_callbacks: WeakSet[Callable[[T], Any]] = WeakSet()

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterface],
    ) -> DbusSignal[T]: ...

    @overload
    def __get__(
        self,
        obj: DbusInterface,
        obj_class: Type[DbusInterface],
    ) -> DbusBoundSignal[T]: ...

    def __get__(
        self,
        obj: Optional[DbusInterface],
        obj_class: Optional[Type[DbusInterface]] = None,
    ) -> Union[DbusBoundSignal[T], DbusSignal[T]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxySignal(self, dbus_meta)
            else:
                return DbusLocalSignal(self, obj, dbus_meta)
        else:
            return self

    async def catch_anywhere(
        self,
        service_name: str,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        if bus is None:
            bus = get_default_bus()

        message_queue: Queue[Message] = Queue()

        match_slot = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.interface_name,
            member_filter=self.name,
            callback=message_queue.put_nowait,
        )

        with closing(match_slot):
            while True:
                message = await message_queue.get()
                signal_path = message.path
                assert signal_path is not None
                yield (signal_path, cast(T, message.get_contents()))


class DbusBoundSignal[T](DbusBoundMember, AsyncIterable[T], ABC):
    def __init__(self, dbus_signal: DbusSignal[T], **kwargs):
        super().__init__(**kwargs)
        self.dbus_signal = dbus_signal

    @property
    def member(self) -> DbusMember:
        return self.dbus_signal

    @abstractmethod
    def catch(self) -> AsyncIterator[T]: ...

    def __aiter__(self) -> AsyncIterator[T]:
        return self.catch()

    @abstractmethod
    def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]: ...

    @abstractmethod
    def emit(self, args: T) -> None: ...


class DbusProxySignal[T](DbusBoundSignal[T], DbusProxyMember):
    def __init__(
        self,
        dbus_signal: DbusSignal[T],
        proxy_meta: DbusRemoteObjectMeta,
        **kwargs,
    ):
        super().__init__(dbus_signal=dbus_signal, **kwargs)
        self.proxy_meta = proxy_meta
        self.__doc__ = dbus_signal.__doc__

    async def _register_match_slot(
        self,
        bus: Dbus,
        callback: Callable[[Message], Any],
    ) -> Closeable:
        return await bus.subscribe_signals(
            sender_filter=self.proxy_meta.service_name,
            path_filter=self.proxy_meta.object_path,
            interface_filter=self.dbus_signal.interface_name,
            member_filter=self.dbus_signal.name,
            callback=callback,
        )

    async def catch(self):
        message_queue: Queue[Message] = Queue()

        handle = await self._register_match_slot(
            self.proxy_meta.attached_bus,
            message_queue.put_nowait,
        )

        with closing(handle):
            while True:
                next_signal_message = await message_queue.get()
                yield cast(T, next_signal_message.get_contents())

    async def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        if bus is None:
            bus = self.proxy_meta.attached_bus

        if service_name is None:
            service_name = self.proxy_meta.service_name

        message_queue: Queue[Message] = Queue()

        handle = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.dbus_signal.interface_name,
            member_filter=self.dbus_signal.name,
            callback=message_queue.put_nowait,
        )

        with closing(handle):
            while True:
                next_signal_message = await message_queue.get()
                signal_path = next_signal_message.path
                assert signal_path is not None
                yield (signal_path, cast(T, next_signal_message.get_contents()))

    def emit(self, args: T):
        raise RuntimeError("Cannot emit signal from D-Bus proxy.")


class DbusLocalSignal[T](DbusBoundSignal[T], DbusLocalMember):
    def __init__(
        self,
        dbus_signal: DbusSignal[T],
        local_object: DbusInterface,
        local_meta: DbusLocalObjectMeta,
    ):
        super().__init__(dbus_signal=dbus_signal, local_object=local_object)
        self.local_meta = local_meta
        self.__doc__ = dbus_signal.__doc__

    def _append_to_interface(self, interface: Interface, handle: DbusExportHandle):
        interface.add_signal(
            self.dbus_signal.name,
            self.dbus_signal.signature,
            self.dbus_signal.args_names,
            **self.dbus_signal.flags,
        )

    async def catch(self):
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

    def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncIterable[Tuple[str, T]]:
        raise NotImplementedError()

    def _emit_dbus_signal(self, args: T) -> None:
        attached_bus = self.local_meta.attached_bus
        if attached_bus is None:
            return

        serving_object_path = self.local_meta.serving_object_path
        if serving_object_path is None:
            return

        attached_bus.emit_signal(
            path=serving_object_path,
            interface=self.dbus_signal.interface_name,
            member=self.dbus_signal.name,
            signature=self.dbus_signal.signature,
            args=args,  # type: ignore
        )

    def emit(self, args: T) -> None:
        self._emit_dbus_signal(args)

        for callback in self.dbus_signal.local_callbacks:
            callback(args)


def dbus_signal[T](
    signature: str = "",
    arg_names: Sequence[str] = (),
    name: Optional[str] = None,
    **flags: Unpack[MemberFlags],
) -> Callable[[Callable[[Any], T]], DbusSignal[T]]:
    assert not isinstance(signature, FunctionType), (
        "Passed function to decorator directly. " "Did you forget () round brackets?"
    )

    def signal_decorator(pseudo_function: Callable[[Any], T]) -> DbusSignal[T]:

        assert isinstance(pseudo_function, FunctionType)
        signal = DbusSignal(
            name=name,
            signature=signature,
            args_names=arg_names,
            **flags,
        )
        signal.__doc__ = pseudo_function.__doc__
        signal.__annotations__ = pseudo_function.__annotations__
        return signal

    return signal_decorator
