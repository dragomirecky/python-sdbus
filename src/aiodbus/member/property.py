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
from contextlib import ExitStack
from inspect import iscoroutinefunction
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    Optional,
    Type,
    TypeVar,
    Union,
    Unpack,
    overload,
    override,
)

from aiodbus.bus import DbusInterfaceBuilder, PropertyFlags
from aiodbus.member.base import (
    DbusBoundMember,
    DbusClassMember,
    DbusLocalMember,
    DbusMember,
    DbusProxyMember,
)
from aiodbus.meta import DbusRemoteObjectMeta
from aiodbus.signature import NoGenericsTypingAvailable, PropertyMapping

if TYPE_CHECKING:
    from aiodbus.interface.base import DbusInterface
    from aiodbus.interface.properties import BoundPropertiesChangedSignal


T = TypeVar("T")


class DbusProperty[T](DbusMember):
    def __init__(
        self,
        name: Optional[str] = None,
        signature: str | None = None,
        getter: Optional[Callable[[DbusInterface], T]] = None,
        setter: Optional[Callable[[DbusInterface, T], None]] = None,
        **flags: Unpack[PropertyFlags],
    ) -> None:
        if name is None and getter:
            name = DbusMember.dbusify_name(getter.__name__)
        super().__init__(name)

        if signature is None and getter:
            self.mapping = PropertyMapping.from_getter(getter)
        elif signature is not None:
            self.mapping = PropertyMapping.from_manual_input(signature)
        else:
            # defered mapping initialization to __set_name__
            pass

        self.property_getter = getter
        self.property_setter = setter
        self.flags = flags
        self.emits_on_property_change = flags.get(
            "emits_invalidation", False
        ) or flags.get("emits_change", False)
        self.__doc__ = getter.__doc__

    @property
    def signature(self) -> str:
        return self.mapping.conversion.signature

    def finalize_mapping(self):
        if not hasattr(self, "mapping"):
            try:
                self.mapping = PropertyMapping.from_generics(self, argument_idx=0)
            except NoGenericsTypingAvailable:
                raise RuntimeError(
                    f"Property {self} failed to initialize: has no signature source available"
                ) from None

    def __set_name__(self, owner: object, name: str) -> None:
        super().__set_name__(owner, name)
        self.finalize_mapping()

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: None,
        obj_class: Type[I],
    ) -> DbusClassMember[I, DbusProperty[T]]: ...

    @overload
    def __get__[I: DbusInterface](
        self,
        obj: I,
        obj_class: Type[I],
    ) -> DbusBoundProperty[I, T]: ...

    def __get__[I: DbusInterface](
        self,
        obj: Optional[I],
        obj_class: Optional[Type[I]] = None,
    ) -> Union[DbusBoundProperty[I, T], DbusClassMember[I, DbusProperty[T]]]:
        if obj is not None:
            dbus_meta = obj._dbus
            if isinstance(dbus_meta, DbusRemoteObjectMeta):
                return DbusProxyProperty[I, T](
                    member=self, local_object=obj, proxy_meta=dbus_meta
                )
            else:
                return DbusLocalProperty[I, T](member=self, local_object=obj)
        else:
            assert obj_class is not None
            return DbusClassMember[I, DbusProperty[T]](
                local_object_cls=obj_class, member=self
            )

    def setter(
        self,
        new_set_function: Callable[[Any, T], None],
    ) -> None:
        assert self.property_setter is None, "Setter already defined"
        assert not iscoroutinefunction(new_set_function), (
            "Property setter can't be coroutine",
        )
        self.property_setter = new_set_function


class DbusBoundProperty[I: DbusInterface, T](DbusBoundMember[I, DbusProperty[T]], ABC):
    def __await__(self) -> Generator[Any, None, T]:
        return self.get().__await__()

    @abstractmethod
    async def get(self) -> T: ...

    @abstractmethod
    async def set(self, new_value: T) -> None: ...


class DbusProxyProperty[I: DbusInterface, T](
    DbusBoundProperty[I, T], DbusProxyMember[I, DbusProperty[T]]
):
    def __init__(self, proxy_meta: DbusRemoteObjectMeta, **kwargs):
        super().__init__(**kwargs)
        self.proxy_meta = proxy_meta

    async def get(self) -> T:
        bus = self.proxy_meta.attached_bus
        response = await bus.get_property(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.member.interface_name,
            member=self.member.name,
        )
        return self.member.mapping.conversion.from_dbus(response[1])

    async def set(self, new_value: T) -> None:
        bus = self.proxy_meta.attached_bus
        dbus_new_value = self.member.mapping.conversion.to_dbus(new_value)
        await bus.set_property(
            destination=self.proxy_meta.service_name,
            path=self.proxy_meta.object_path,
            interface=self.member.interface_name,
            member=self.member.name,
            signature=self.member.signature,
            args=(dbus_new_value,),
        )


class DbusLocalProperty[I: DbusInterface, T](
    DbusBoundProperty[I, T], DbusLocalMember[I, DbusProperty[T]]
):
    @override
    def export_to_dbus(self, interface: DbusInterfaceBuilder, exit_stack: ExitStack):
        getter = self._dbus_reply_get
        dbus_property = self.member

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
        getter = self.member.property_getter
        if getter is None:
            raise RuntimeError("Property has no getter available")
        value = getter(self.local_object)
        return value

    async def get(self) -> T:
        return self._get_value()

    async def set(self, new_value: T) -> None:
        if self.member.property_setter is None:
            raise RuntimeError("Property has no setter")

        local_object = self.local_object
        self.member.property_setter(local_object, new_value)
        self._emit_property_changed(local_object)

    def _dbus_reply_get(self):
        result = self._get_value()
        return self.member.mapping.conversion.to_dbus(result)

    def _dbus_reply_set(self, data_to_set_to) -> None:
        assert self.member.property_setter is not None

        local_object = self.local_object
        new_value = self.member.mapping.conversion.from_dbus(data_to_set_to)
        self.member.property_setter(local_object, new_value)
        self._emit_property_changed(local_object)

    def _emit_property_changed(self, local_object: Any) -> None:
        if not self.member.emits_on_property_change:
            return
        try:
            properties_changed: BoundPropertiesChangedSignal = getattr(
                local_object,
                "properties_changed",
            )
        except AttributeError:
            ...
        else:
            properties_changed.emit_property_changed(self)


def dbus_property[T](
    signature: str | None = None,
    name: Optional[str] = None,
    **flags: Unpack[PropertyFlags],
) -> Callable[[Callable[[Any], T]], DbusProperty[T]]:
    assert not isinstance(signature, FunctionType), (
        "Passed function to decorator directly. Did you forget () round brackets?"
    )

    def property_decorator(function: Callable[..., Any]) -> DbusProperty[T]:
        assert not iscoroutinefunction(function), (
            "Property getter can't be coroutine",
        )

        new_wrapper: DbusProperty[T] = DbusProperty(
            name=name,
            signature=signature,
            getter=function,
            **flags,
        )

        return new_wrapper

    return property_decorator
