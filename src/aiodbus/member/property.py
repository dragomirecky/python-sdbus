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
from inspect import iscoroutinefunction
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    Unpack,
    cast,
    overload,
)

from aiodbus.bus import Interface, PropertyFlags
from aiodbus.member.base import (
    DbusBoundMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusRemoteObjectMeta

if TYPE_CHECKING:
    from _sdbus import DbusCompleteType
    from aiodbus.interface.base import DbusExportHandle, DbusInterface


T = TypeVar("T")


class DbusProperty[T](DbusMember):
    def __init__(
        self,
        name: Optional[str] = None,
        signature: str = "",
        getter: Optional[Callable[[DbusInterface], T]] = None,
        setter: Optional[Callable[[DbusInterface, T], None]] = None,
        **flags: Unpack[PropertyFlags],
    ) -> None:
        if name is None and getter:
            name = DbusMember.dbusify_name(getter.__name__)
        super().__init__(name)
        self.signature = signature
        self.property_getter = getter
        self.property_setter = setter
        self.flags = flags
        self.__doc__ = getter.__doc__

    @overload
    def __get__(
        self,
        obj: None,
        obj_class: Type[DbusInterface],
    ) -> DbusProperty[T]: ...

    @overload
    def __get__(
        self,
        obj: DbusInterface,
        obj_class: Type[DbusInterface],
    ) -> DbusBoundProperty[T]: ...

    def __get__(
        self,
        obj: Optional[DbusInterface],
        obj_class: Optional[Type[DbusInterface]] = None,
    ) -> Union[DbusBoundProperty[T], DbusProperty[T]]:
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


class DbusBoundProperty[T](DbusBoundMember, ABC):
    def __init__(self, dbus_property: DbusProperty[T], **kwargs) -> None:
        super().__init__(**kwargs)
        self.dbus_property = dbus_property

    @property
    def member(self) -> DbusMember:
        return self.dbus_property

    def __await__(self) -> Generator[Any, None, T]:
        return self.get().__await__()

    @abstractmethod
    async def get(self) -> T: ...

    @abstractmethod
    async def set(self, new_value: T) -> None: ...


class DbusProxyProperty(
    DbusBoundProperty[T],
    DbusProxyMember,
):
    def __init__(
        self,
        dbus_property: DbusProperty[T],
        proxy_meta: DbusRemoteObjectMeta,
        **kwargs,
    ):
        super().__init__(dbus_property=dbus_property, **kwargs)
        self.proxy_meta = proxy_meta

        self.__doc__ = dbus_property.__doc__

    async def get(self) -> T:
        bus = self.proxy_meta.attached_bus
        response = await bus.get_property(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.dbus_property.interface_name,
            member=self.dbus_property.name,
        )
        return cast(T, response[1])

    async def set(self, new_value: T) -> None:
        bus = self.proxy_meta.attached_bus
        await bus.set_property(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.dbus_property.interface_name,
            member=self.dbus_property.name,
            signature=self.dbus_property.signature,
            args=(new_value,),
        )


class DbusLocalProperty(
    DbusBoundProperty[T],
    DbusLocalMember,
):
    def __init__(self, dbus_property: DbusProperty[T], local_object: DbusInterface):
        super().__init__(dbus_property=dbus_property, local_object=local_object)
        self.__doc__ = dbus_property.__doc__

    def _append_to_interface(self, interface: Interface, handle: DbusExportHandle):
        getter = self._dbus_reply_get
        dbus_property = self.dbus_property

        if dbus_property.property_setter is not None:
            setter = self._dbus_reply_set
        else:
            setter = None

        interface.add_property(
            dbus_property.name,
            dbus_property.signature,
            get_function=getter,
            set_function=setter,
            **dbus_property.flags,
        )

    def _get_value(self) -> T:
        getter = self.dbus_property.property_getter
        if getter is None:
            raise RuntimeError("Property has no getter available")
        return getter(self.local_object)

    async def get(self) -> T:
        return self._get_value()

    async def set(self, new_value: T) -> None:
        if self.dbus_property.property_setter is None:
            raise RuntimeError("Property has no setter")

        local_object = self.local_object
        self.dbus_property.property_setter(local_object, new_value)
        self._emit_property_changed(local_object, new_value)

    def _dbus_reply_get(self) -> Tuple[DbusCompleteType, ...]:
        result = self._get_value()
        return cast(Tuple["DbusCompleteType", ...], result)

    def _dbus_reply_set(self, data_to_set_to: Tuple[DbusCompleteType, ...]) -> None:
        assert self.dbus_property.property_setter is not None

        local_object = self.local_object
        new_value = cast(T, data_to_set_to)
        self.dbus_property.property_setter(local_object, new_value)
        self._emit_property_changed(local_object, new_value)

    def _emit_property_changed(self, local_object: Any, new_value: T) -> None:
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
                        self.dbus_property.name: (
                            self.dbus_property.signature,
                            new_value,
                        ),
                    },
                    [],
                )
            )


def dbus_property[T](
    signature: str = "",
    name: Optional[str] = None,
    **flags: Unpack[PropertyFlags],
) -> Callable[[Callable[[Any], T]], DbusProperty[T]]:

    assert not isinstance(signature, FunctionType), (
        "Passed function to decorator directly. " "Did you forget () round brackets?"
    )

    def property_decorator(function: Callable[..., Any]) -> DbusProperty[T]:

        assert not iscoroutinefunction(function), ("Property getter can't be coroutine",)

        new_wrapper: DbusProperty[T] = DbusProperty(
            name=name,
            signature=signature,
            getter=function,
            **flags,
        )

        return new_wrapper

    return property_decorator
