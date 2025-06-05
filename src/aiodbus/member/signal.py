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
from contextlib import (
    AbstractAsyncContextManager,
    ExitStack,
    asynccontextmanager,
    closing,
)
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Optional,
    Sequence,
    Type,
    Union,
    Unpack,
    cast,
    overload,
)
from weakref import WeakSet

from aiodbus import Dbus, get_default_bus
from aiodbus.bus import DbusInterfaceBuilder, MemberFlags
from aiodbus.bus.message import DbusMessage
from aiodbus.closeable import Closeable
from aiodbus.member.base import (
    DbusBoundMember,
    DbusClassMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusLocalObjectMeta, DbusRemoteObjectMeta
from aiodbus.signature import NoGenericsTypingAvailable, SignalMapping

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusInterface


class DbusSignal[T](DbusMember):
    def __init__(
        self,
        signature: str | None = None,
        name: Optional[str] = None,
        args_names: Sequence[str] = (),
        **flags: Unpack[MemberFlags],
    ):
        super().__init__(name=name)

        if signature is not None:
            self._mapping = SignalMapping.from_manual_input(signature)
        else:
            # defered mapping initialization
            # we are gonna wait for the __set_name__ call
            pass

        self.args_names = args_names
        self.flags = flags
        self.local_callbacks: WeakSet[Callable[[T], Any]] = WeakSet()

    @property
    def signature(self) -> str:
        return self.mapping.conversion.signature

    @property
    def mapping(self) -> SignalMapping:
        try:
            return self._mapping
        except AttributeError:
            raise RuntimeError("Property not fully initialized yet")

    def __set_name__(self, owner: object, name: str) -> None:
        super().__set_name__(owner, name)
        if not hasattr(self, "_mapping"):
            try:
                self._mapping = SignalMapping.from_generics(self, argument_idx=0)
            except NoGenericsTypingAvailable:
                raise RuntimeError(
                    f"Signal {self} failed to initialize: has no signature source available"
                ) from None

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: None,
        obj_class: Type[I],
    ) -> DbusClassSignal[I, T]: ...

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: I,
        obj_class: Type[I],
    ) -> DbusBoundSignal[I, T]: ...

    def __get__[I: DbusInterface](
        self,
        obj: Optional[I],
        obj_class: Optional[Type[I]] = None,
    ) -> Union[DbusBoundSignal[I, T], DbusClassMember[I, DbusSignal[T]]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxySignal(member=self, local_object=obj, proxy_meta=dbus_meta)
            else:
                return DbusLocalSignal(member=self, local_object=obj, local_meta=dbus_meta)
        else:
            assert obj_class is not None
            return DbusClassSignal(local_object_cls=obj_class, member=self)


class Signals[T]:
    def __init__(self, queue: Queue[T]):
        self.queue = queue

    async def get(self) -> T:
        return await self.queue.get()

    async def __aiter__(self) -> AsyncIterator[T]:
        while True:
            yield await self.queue.get()


class DbusClassSignal[I: DbusInterface, T](DbusClassMember[I, DbusSignal[T]]):
    @asynccontextmanager
    async def catch_anywhere(
        self,
        service_name: str,
        bus: Optional[Dbus] = None,
    ) -> AsyncGenerator[Signals[tuple[DbusMessage, T]], None]:
        if bus is None:
            bus = get_default_bus()

        message_queue: Queue[tuple[DbusMessage, T]] = Queue()

        def on_signal(message: DbusMessage) -> None:
            value = self.member.mapping.conversion.from_dbus(message.get_contents())
            message_queue.put_nowait((message, value))

        match_slot = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.member.interface_name,
            member_filter=self.member.name,
            callback=on_signal,
        )

        with closing(match_slot):
            yield Signals(message_queue)


class DbusBoundSignal[I: DbusInterface, T](DbusBoundMember[I, DbusSignal[T]], ABC):
    @abstractmethod
    def catch(self) -> AbstractAsyncContextManager[Signals[T]]: ...

    @abstractmethod
    def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AbstractAsyncContextManager[Signals[tuple[DbusMessage, T]]]: ...

    @abstractmethod
    def emit(self, args: T) -> None: ...


class DbusProxySignal[I: DbusInterface, T](DbusBoundSignal[I, T], DbusProxyMember):
    def __init__(self, proxy_meta: DbusRemoteObjectMeta, **kwargs):
        super().__init__(**kwargs)
        self.proxy_meta = proxy_meta

    async def _register_match_slot(
        self,
        bus: Dbus,
        callback: Callable[[DbusMessage[T]], Any],
    ) -> Closeable:
        return await bus.subscribe_signals(
            sender_filter=self.proxy_meta.service_name,
            path_filter=self.proxy_meta.object_path,
            interface_filter=self.member.interface_name,
            member_filter=self.member.name,
            callback=callback,
        )

    @asynccontextmanager
    async def catch(self) -> AsyncGenerator[Signals[T], None]:
        message_queue: Queue[T] = Queue()

        handle = await self._register_match_slot(
            self.proxy_meta.attached_bus,
            lambda message: message_queue.put_nowait(cast(T, message.get_contents())),
        )

        with closing(handle):
            yield Signals(message_queue)

    @asynccontextmanager
    async def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncGenerator[Signals[tuple[DbusMessage, T]], None]:
        if bus is None:
            bus = self.proxy_meta.attached_bus

        if service_name is None:
            service_name = self.proxy_meta.service_name

        def on_signal(message: DbusMessage) -> None:
            value = self.member.mapping.conversion.from_dbus(message.get_contents())
            message_queue.put_nowait((message, value))

        message_queue: Queue[tuple[DbusMessage, T]] = Queue()

        handle = await bus.subscribe_signals(
            sender_filter=service_name,
            interface_filter=self.member.interface_name,
            member_filter=self.member.name,
            callback=on_signal,
        )

        with closing(handle):
            yield Signals[tuple[DbusMessage, T]](message_queue)

    def emit(self, args: T):
        raise RuntimeError("Cannot emit signal from D-Bus proxy.")


class DbusLocalSignal[I: DbusInterface, T](DbusBoundSignal[I, T], DbusLocalMember):
    def __init__(self, local_meta: DbusLocalObjectMeta, **kwargs):
        super().__init__(**kwargs)
        self.local_meta = local_meta

    def export_to_dbus(self, interface: DbusInterfaceBuilder, exit_stack: ExitStack):
        interface.add_signal(
            self.member.name,
            self.member.signature,
            self.member.args_names,
            **self.member.flags,
        )

    @asynccontextmanager
    async def catch(self) -> AsyncGenerator[Signals[T], None]:
        new_queue: Queue[T] = Queue()

        signal_callbacks = self.member.local_callbacks
        put_method = new_queue.put_nowait
        try:
            signal_callbacks.add(put_method)
            yield Signals(new_queue)
        finally:
            signal_callbacks.remove(put_method)

    @asynccontextmanager
    def catch_anywhere(
        self,
        service_name: Optional[str] = None,
        bus: Optional[Dbus] = None,
    ) -> AsyncGenerator[Signals[tuple[DbusMessage, T]], None]:
        raise NotImplementedError()

    def _emit_dbus_signal(self, args: T) -> None:
        attached_bus = self.local_meta.attached_bus
        if attached_bus is None:
            return

        serving_object_path = self.local_meta.serving_object_path
        if serving_object_path is None:
            return

        dbus_args = self.member.mapping.conversion.to_dbus(args)
        attached_bus.emit_signal(
            path=serving_object_path,
            interface=self.member.interface_name,
            member=self.member.name,
            signature=self.member.signature,
            args=dbus_args,
        )

    def emit(self, args: T) -> None:
        self._emit_dbus_signal(args)

        for callback in self.member.local_callbacks:
            callback(args)


def dbus_signal[T](
    signature: str | None = "",
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
