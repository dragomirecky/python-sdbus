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

from inspect import getmembers
from itertools import chain
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Self,
    Set,
    Tuple,
    Type,
    Union,
)
from weakref import WeakKeyDictionary, WeakValueDictionary

from _sdbus import is_interface_name_valid
from aiodbus.bus import Dbus, get_default_bus
from aiodbus.handle import DbusExportHandle
from aiodbus.member.base import DbusLocalMember, DbusMember
from aiodbus.meta import DbusClassMeta, DbusLocalObjectMeta, DbusRemoteObjectMeta

DBUS_CLASS_TO_META: WeakKeyDictionary[type, DbusClassMeta] = WeakKeyDictionary()
DBUS_INTERFACE_NAME_TO_CLASS: WeakValueDictionary[str, DbusInterfaceMeta] = WeakValueDictionary()


class DbusInterfaceMeta(type):
    @classmethod
    def _check_collisions(
        cls,
        new_class_name: str,
        namespace: Dict[str, Any],
        mro_dbus_members: Dict[str, DbusMember],
    ) -> None:

        possible_collisions = namespace.keys() & mro_dbus_members.keys()

        if possible_collisions:
            raise ValueError(
                f"Interface {new_class_name!r} redefines reserved "
                f"D-Bus attribute names: {possible_collisions!r}"
            )

    @staticmethod
    def _extract_dbus_members(
        dbus_class: type,
        dbus_meta: DbusClassMeta,
    ) -> Dict[str, DbusMember]:
        dbus_members_map: Dict[str, DbusMember] = {}

        for attr_name in dbus_meta.python_attr_to_dbus_member.keys():
            dbus_member = dbus_class.__dict__.get(attr_name)
            if not isinstance(dbus_member, DbusMember):
                raise TypeError(
                    f"Expected D-Bus member, got {dbus_member!r} " f"in class {dbus_class!r}"
                )

            dbus_members_map[attr_name] = dbus_member

        return dbus_members_map

    @classmethod
    def _map_mro_dbus_members(
        cls,
        new_class_name: str,
        base_classes: Iterable[type],
    ) -> Dict[str, DbusMember]:
        all_python_dbus_map: Dict[str, DbusMember] = {}
        possible_collisions: Set[str] = set()

        for c in base_classes:
            dbus_meta = DBUS_CLASS_TO_META.get(c)
            if dbus_meta is None:
                continue

            base_dbus_members = cls._extract_dbus_members(c, dbus_meta)

            possible_collisions.update(base_dbus_members.keys() & all_python_dbus_map.keys())

            all_python_dbus_map.update(base_dbus_members)

        if possible_collisions:
            raise ValueError(
                f"Interface {new_class_name!r} has a reserved D-Bus "
                f"attribute name collision: {possible_collisions!r}"
            )

        return all_python_dbus_map

    @staticmethod
    def _map_dbus_members(
        attr_name: str,
        attr: Any,
        meta: DbusClassMeta,
        interface_name: str,
    ) -> None:
        if not isinstance(attr, DbusMember):
            return

        if attr.interface_name != interface_name:
            return

        if isinstance(attr, DbusMember):
            meta.dbus_member_to_python_attr[attr.name] = attr_name
            meta.python_attr_to_dbus_member[attr_name] = attr.name
        else:
            raise TypeError(f"Unknown D-Bus element: {attr!r}")

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

    @staticmethod
    def _init_members(
        name: str,
        namespace: Dict[str, Any],
        interface_name: Optional[str],
        serving_enabled: bool,
    ) -> None:
        for attr_name, attr in namespace.items():
            if not isinstance(attr, DbusMember):
                continue

            # TODO: Fix async metaclass copying all methods
            if hasattr(attr, "interface_name"):
                continue

            if interface_name is None:
                raise TypeError(
                    f"Defined D-Bus element {attr_name!r} without "
                    f"interface name in the class {name!r}."
                )

            attr.interface_name = interface_name
            attr.serving_enabled = serving_enabled

    def __new__(
        cls,
        name: str,
        bases: Tuple[type, ...],
        namespace: Dict[str, Any],
        interface_name: Optional[str] = None,
        serving_enabled: bool = True,
    ) -> DbusInterfaceMeta:

        if interface_name in DBUS_INTERFACE_NAME_TO_CLASS:
            raise ValueError(
                f"D-Bus interface of the name {interface_name!r} was " "already created."
            )

        all_mro_bases: Set[Type[Any]] = set(chain.from_iterable((c.__mro__ for c in bases)))
        reserved_dbus_map = cls._map_mro_dbus_members(
            name,
            all_mro_bases,
        )
        cls._check_collisions(name, namespace, reserved_dbus_map)

        if interface_name is not None:
            cls._check_interface_name(interface_name)

        cls._init_members(name, namespace, interface_name, serving_enabled)

        new_cls = super().__new__(cls, name, bases, namespace)

        if interface_name is not None:
            dbus_class_meta = DbusClassMeta(interface_name, serving_enabled)
            DBUS_CLASS_TO_META[new_cls] = dbus_class_meta
            DBUS_INTERFACE_NAME_TO_CLASS[interface_name] = new_cls

            for attr_name, attr in namespace.items():
                cls._map_dbus_members(
                    attr_name,
                    attr,
                    dbus_class_meta,
                    interface_name,
                )

        return new_cls


class DbusInterface(metaclass=DbusInterfaceMeta):
    def __init__(self) -> None:
        self._dbus: Union[DbusRemoteObjectMeta, DbusLocalObjectMeta] = DbusLocalObjectMeta()

    @classmethod
    def _dbus_iter_interfaces_meta(cls) -> Iterator[Tuple[str, DbusClassMeta]]:
        for base in cls.__mro__:
            meta = DBUS_CLASS_TO_META.get(base)
            if meta is None:
                continue

            yield meta.interface_name, meta

    def export_to_dbus(self, object_path: str, bus: Optional[Dbus] = None) -> DbusExportHandle:
        local_object_meta = self._dbus
        if isinstance(local_object_meta, DbusRemoteObjectMeta):
            raise RuntimeError("Cannot export D-Bus proxies.")

        if local_object_meta.attached_bus is not None:
            raise RuntimeError("Object already exported.")

        if bus is None:
            bus = get_default_bus()

        local_object_meta.attached_bus = bus
        local_object_meta.serving_object_path = object_path
        # TODO: can be optimized with a single loop
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

        for interface_name, member_list in interface_map.items():
            new_interface = bus.create_interface()
            for dbus_something in member_list:
                dbus_something._append_to_interface(new_interface, export_handle)
            handle = bus.export(path=object_path, interface=new_interface, name=interface_name)
            local_object_meta.activated_interfaces.append(new_interface)
            export_handle.append(handle)

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
