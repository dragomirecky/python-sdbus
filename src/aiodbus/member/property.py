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

from inspect import iscoroutinefunction
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Generator,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)
from weakref import ref as weak_ref

from _sdbus import SdBusInterface, SdBusMessage
from aiodbus.dbus_common_elements import (
    DbusBoundMember,
    DbusLocalMember,
    DbusMember,
    DbusPropertyCommon,
    DbusPropertyOverride,
    DbusProxyMember,
    DbusRemoteObjectMeta,
)

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusExportHandle, DbusInterfaceBase


T = TypeVar("T")


class DbusProperty(DbusMember, DbusPropertyCommon, Generic[T]):
    def __init__(
        self,
        property_name: Optional[str],
        property_signature: str,
        property_getter: Callable[[DbusInterfaceBase], T],
        property_setter: Optional[Callable[[DbusInterfaceBase, T], None]],
        flags: int,
    ) -> None:
        assert isinstance(property_getter, FunctionType)
        super().__init__(
            property_name,
            property_signature,
            flags,
            property_getter,
        )
        self.property_getter: Callable[[DbusInterfaceBase], T] = property_getter
        self.property_setter: Optional[Callable[[DbusInterfaceBase, T], None]] = property_setter
        self.property_setter_is_public: bool = True

        self.__doc__ = property_getter.__doc__

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterfaceBase],
    ) -> DbusProperty[T]: ...

    @overload
    def __get__(
        self,
        obj: DbusInterfaceBase,
        obj_class: Type[DbusInterfaceBase],
    ) -> DbusBoundPropertyBase[T]: ...

    def __get__(
        self,
        obj: Optional[DbusInterfaceBase],
        obj_class: Optional[Type[DbusInterfaceBase]] = None,
    ) -> Union[DbusBoundPropertyBase[T], DbusProperty[T]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxyProperty(self, dbus_meta)
            else:
                return DbusLocalProperty(self, obj)
        else:
            return self

    def setter(
        self,
        new_set_function: Callable[[Any, T], None],
    ) -> None:
        assert self.property_setter is None, "Setter already defined"
        assert not iscoroutinefunction(new_set_function), ("Property setter can't be coroutine",)
        self.property_setter = new_set_function

    def setter_private(
        self,
        new_set_function: Callable[[Any, T], None],
    ) -> None:
        assert self.property_setter is None, "Setter already defined"
        assert not iscoroutinefunction(new_set_function), ("Property setter can't be coroutine",)
        self.property_setter = new_set_function
        self.property_setter_is_public = False


class DbusBoundPropertyBase(DbusBoundMember, Awaitable[T]):
    def __init__(self, dbus_property: DbusProperty[T]) -> None:
        self.dbus_property = dbus_property

    @property
    def member(self) -> DbusMember:
        return self.dbus_property

    def __await__(self) -> Generator[Any, None, T]:
        return self.get().__await__()

    async def get(self) -> T:
        raise NotImplementedError

    async def set(self, complete_object: T) -> None:
        raise NotImplementedError


class DbusProxyProperty(
    DbusBoundPropertyBase[T],
    DbusProxyMember,
):
    def __init__(
        self,
        dbus_property: DbusProperty[T],
        proxy_meta: DbusRemoteObjectMeta,
    ):
        super().__init__(dbus_property)
        self.proxy_meta = proxy_meta

        self.__doc__ = dbus_property.__doc__

    async def get(self) -> T:
        bus = self.proxy_meta.attached_bus
        new_get_message = bus.new_property_get_message(
            self.proxy_meta.service_name,
            self.proxy_meta.object_path,
            self.dbus_property.interface_name,
            self.dbus_property.property_name,
        )
        reply_message = await bus.call_async(new_get_message)
        # Get method returns variant but we only need contents of variant
        return cast(T, reply_message.get_contents()[1])

    async def set(self, complete_object: T) -> None:
        bus = self.proxy_meta.attached_bus
        new_set_message = bus.new_property_set_message(
            self.proxy_meta.service_name,
            self.proxy_meta.object_path,
            self.dbus_property.interface_name,
            self.dbus_property.property_name,
        )
        new_set_message.append_data(
            "v",
            (self.dbus_property.property_signature, complete_object),
        )
        await bus.call_async(new_set_message)


class DbusLocalProperty(
    DbusBoundPropertyBase[T],
    DbusLocalMember,
):
    def __init__(
        self,
        dbus_property: DbusProperty[T],
        local_object: DbusInterfaceBase,
    ):
        super().__init__(dbus_property)
        self.local_object_ref = weak_ref(local_object)

        self.__doc__ = dbus_property.__doc__

    def _append_to_interface(
        self,
        interface: SdBusInterface,
        handle: DbusExportHandle,
    ) -> None:
        getter = self._dbus_reply_get
        dbus_property = self.dbus_property

        if dbus_property.property_setter is not None and dbus_property.property_setter_is_public:

            setter = self._dbus_reply_set
        else:
            setter = None

        interface.add_property(
            dbus_property.property_name,
            dbus_property.property_signature,
            getter,
            setter,
            dbus_property.flags,
        )

    async def get(self) -> T:
        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        return self.dbus_property.property_getter(local_object)

    async def set(self, complete_object: T) -> None:
        if self.dbus_property.property_setter is None:
            raise RuntimeError("Property has no setter")

        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        self.dbus_property.property_setter(
            local_object,
            complete_object,
        )

        try:
            properties_changed = getattr(
                local_object,
                "properties_changed",
            )
        except AttributeError:
            ...
        else:
            properties_changed.emit(
                (
                    self.dbus_property.interface_name,
                    {
                        self.dbus_property.property_name: (
                            self.dbus_property.property_signature,
                            complete_object,
                        ),
                    },
                    [],
                )
            )

    def _dbus_reply_get(self, message: SdBusMessage) -> None:
        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        reply_data: Any = self.dbus_property.property_getter(local_object)
        message.append_data(self.dbus_property.property_signature, reply_data)

    def _dbus_reply_set(self, message: SdBusMessage) -> None:
        local_object = self.local_object_ref()
        if local_object is None:
            raise RuntimeError("Local object no longer exists!")

        assert self.dbus_property.property_setter is not None
        data_to_set_to: Any = message.get_contents()

        self.dbus_property.property_setter(local_object, data_to_set_to)

        try:
            properties_changed = getattr(
                local_object,
                "properties_changed",
            )
        except AttributeError:
            ...
        else:
            properties_changed.emit(
                (
                    self.dbus_property.interface_name,
                    {
                        self.dbus_property.property_name: (
                            self.dbus_property.property_signature,
                            data_to_set_to,
                        ),
                    },
                    [],
                )
            )


def dbus_property(
    property_signature: str = "",
    flags: int = 0,
    property_name: Optional[str] = None,
) -> Callable[[Callable[[Any], T]], DbusProperty[T]]:

    assert not isinstance(property_signature, FunctionType), (
        "Passed function to decorator directly. " "Did you forget () round brackets?"
    )

    def property_decorator(function: Callable[..., Any]) -> DbusProperty[T]:

        assert not iscoroutinefunction(function), ("Property getter can't be coroutine",)

        new_wrapper: DbusProperty[T] = DbusProperty(
            property_name,
            property_signature,
            function,
            None,
            flags,
        )

        return new_wrapper

    return property_decorator


def dbus_property_async_override() -> Callable[[Callable[[Any], T]], DbusProperty[T]]:

    def new_decorator(new_property: Callable[[Any], T]) -> DbusProperty[T]:
        return cast(DbusProperty[T], DbusPropertyOverride(new_property))

    return new_decorator
