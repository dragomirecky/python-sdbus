# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020-2022 igo95862
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

from collections import OrderedDict
from inspect import getmembers
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Self,
    Tuple,
    Type,
    Union,
)

from _sdbus import is_interface_name_valid
from aiodbus.bus import Dbus, get_default_bus
from aiodbus.handle import CloseableFromCallback, DbusExportHandle
from aiodbus.member.base import DbusLocalMember, DbusMember
from aiodbus.meta import DbusClassMeta, DbusLocalObjectMeta, DbusRemoteObjectMeta

if TYPE_CHECKING:
    from aiodbus.interface.object_manager import DbusObjectManagerInterface


class DbusInterfaceMeta(type):

    dbus_interfaces: OrderedDict[str, DbusInterfaceMeta] = OrderedDict()

    dbus_meta: DbusClassMeta | None = None

    @staticmethod
    def _check_interface_name(interface_name: str):
        try:
            assert is_interface_name_valid(interface_name), (
                f'Invalid interface name: "{interface_name}"; '
                "Interface names must be composed of 2 or more elements "
                "separated by a dot '.' character. All elements must "
                "contain at least one character, consist of ASCII "
                "characters, first character must not be digit and "
                "length must not exceed 255 characters."
            )
        except NotImplementedError:
            ...

    def __new__(
        cls,
        name: str,
        bases: Tuple[type, ...],
        namespace: Dict[str, Any],
        interface_name: Optional[str] = None,
        serving_enabled: bool = True,
    ) -> DbusInterfaceMeta:
        # get parent interfaces
        parent_interfaces: OrderedDict[str, DbusInterfaceMeta] = OrderedDict(
            {
                c.dbus_meta.interface_name: c
                for c in chain.from_iterable((c.__mro__ for c in bases))
                if (type(c) is DbusInterfaceMeta) and c.dbus_meta
            }
        )

        # get members of this new interface
        new_members = {
            attr: member for attr, member in namespace.items() if isinstance(member, DbusMember)
        }

        # check for collisions
        used_attrs = set(new_members.keys())

        for parent_interface in parent_interfaces.values():
            assert parent_interface.dbus_meta is not None
            other_members = parent_interface.dbus_meta.members
            if not used_attrs.isdisjoint(other_members.keys()):
                raise AssertionError(
                    f"Attribute collision {used_attrs & other_members.keys()!r} "
                    f"in interface {parent_interface.dbus_meta.interface_name!r}"
                )
            used_attrs |= set(other_members.keys())

        # create new class
        new_cls = super().__new__(cls, name, bases, namespace)

        if interface_name is not None:
            cls._check_interface_name(interface_name)

            # init members
            for member in new_members.values():
                member.interface_name = interface_name
                member.serving_enabled = serving_enabled

            meta = DbusClassMeta(interface_name, serving_enabled, new_members)
            meta.attr_to_member = {attr: member.name for attr, member in new_members.items()}
            meta.member_to_attr = {member.name: attr for attr, member in new_members.items()}
            new_cls.dbus_meta = meta
            dbus_interfaces = parent_interfaces.copy()
            dbus_interfaces[interface_name] = new_cls
            new_cls.dbus_interfaces = dbus_interfaces
        else:
            if len(new_members) > 0:
                raise TypeError(
                    f"Defined D-Bus element {new_members.keys()!r} without "
                    f"interface_name= in the class {name!r}."
                )

        return new_cls


class DbusInterface(metaclass=DbusInterfaceMeta):
    def __init__(self) -> None:
        self._dbus: Union[DbusRemoteObjectMeta, DbusLocalObjectMeta] = DbusLocalObjectMeta()

    def export_to_dbus(
        self,
        object_path: str,
        bus: Optional[Dbus] = None,
        manager: Optional[DbusObjectManagerInterface] = None,
    ) -> DbusExportHandle:
        local_object_meta = self._dbus
        if isinstance(local_object_meta, DbusRemoteObjectMeta):
            raise RuntimeError("Cannot export D-Bus proxies.")

        if local_object_meta.attached_bus is not None:
            raise RuntimeError("Object already exported.")

        if bus is None:
            bus = get_default_bus()

        local_object_meta.attached_bus = bus
        local_object_meta.serving_object_path = object_path
        interface_map: Dict[str, List[DbusLocalMember]] = {}

        for _, value in getmembers(self):
            assert not isinstance(value, DbusMember)

            if isinstance(value, DbusLocalMember) and value.member.serving_enabled:
                interface_name = value.member.interface_name
            else:
                continue

            try:
                interface_member_list = interface_map[interface_name]
            except KeyError:
                interface_member_list = []
                interface_map[interface_name] = interface_member_list

            interface_member_list.append(value)

        export_handle = DbusExportHandle()
        export_handle.append(CloseableFromCallback(lambda: self)) # just store reference to exported interface, to avoid garbage collection
        exported_interfaces = list[str]()

        for interface_name, member_list in interface_map.items():
            new_interface = bus.create_interface(interface_name, object_path)
            for dbus_something in member_list:
                dbus_something.export_to_dbus(new_interface, export_handle)
            handle = bus.export_interface(new_interface)
            local_object_meta.activated_interfaces.append(new_interface)
            export_handle.append(handle)
            exported_interfaces.append(interface_name)

        if manager is not None:
            bus.emit_interfaces_added(object_path, exported_interfaces)
            export_handle.prepend(
                CloseableFromCallback(
                    lambda: bus.emit_interfaces_removed(object_path, exported_interfaces)
                )
            )

        return export_handle

    def _connect(self, service_name: str, object_path: str, bus: Optional[Dbus] = None) -> None:
        self._proxify(service_name, object_path, bus)

    def _proxify(self, service_name: str, object_path: str, bus: Optional[Dbus] = None) -> None:
        self._dbus = DbusRemoteObjectMeta(service_name, object_path, bus)

    @classmethod
    def new_proxy(
        cls: Type[Self],
        service_name: str,
        object_path: str,
        bus: Optional[Dbus] = None,
    ) -> Self:
        new_object = cls.__new__(cls)
        new_object._proxify(service_name, object_path, bus)
        return new_object